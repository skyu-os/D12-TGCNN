"""
预测驱动重规划服务

将 TGCN 预测的传感器速度通过空间插值映射到道路边，
并基于预测速度进行路径重规划，输出拥堵路段与路线对比结果。
"""

import math
import threading
from typing import Dict, Any, List, Tuple

import numpy as np

from backend.graph.road_graph import RoadGraph
from backend.prediction.traffic_prediction_service import TrafficPredictionService


class PredictiveRouteService:
    """预测拥堵驱动的路径重规划服务（单例）。"""

    REROUTE_CONGESTION_PERCENTILE = 15.0  # 速度最低的 15% 视为拥堵
    REROUTE_CONGESTION_MIN_KMH = 25.0     # 但速度必须低于此绝对值才算真正拥堵
    SENSOR_TRUST_RADIUS_KM = 1.5
    LOW_CONFIDENCE_TIME_PENALTY = 1.35
    BLEND_ALPHA = 0.3  # 预测速度权重（0.3预测 + 0.7静态），保守降低噪声

    _instance = None
    _instance_lock = threading.Lock()

    @classmethod
    def get_instance(cls):
        with cls._instance_lock:
            if cls._instance is None:
                cls._instance = cls()
            return cls._instance

    def __init__(self):
        self._lock = threading.Lock()
        self._road_graph = RoadGraph.build_from_osm()
        self._prediction_service = TrafficPredictionService.get_instance()

    @staticmethod
    def _haversine(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
        """球面距离（米）。"""
        R = 6371000.0
        dlat = math.radians(lat2 - lat1)
        dlon = math.radians(lon2 - lon1)
        a = (
            math.sin(dlat / 2) ** 2
            + math.cos(math.radians(lat1))
            * math.cos(math.radians(lat2))
            * math.sin(dlon / 2) ** 2
        )
        return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))

    def _heuristic(self, node: int, goal: int) -> float:
        node_data = self._road_graph.G.nodes[node]
        goal_data = self._road_graph.G.nodes[goal]
        return self._haversine(
            node_data.get("y", 0),
            node_data.get("x", 0),
            goal_data.get("y", 0),
            goal_data.get("x", 0),
        )

    @staticmethod
    def _congestion_level(speed_kmh: float, max_speed_kmh: float = 60.0) -> str:
        max_speed_kmh = max(1.0, float(max_speed_kmh or 60.0))
        ratio = speed_kmh / max_speed_kmh
        if ratio < 0.3:
            return "severe"
        if ratio < 0.6:
            return "heavy"
        if ratio < 0.8:
            return "moderate"
        return "smooth"

    def _build_sensor_context(self, prediction: Dict[str, Any]) -> Dict[str, Any]:
        items = []
        for x in prediction.get("sensor_predictions", []):
            lat = x.get("latitude")
            lon = x.get("longitude")
            speed = x.get("pred_speed_kmh")
            if isinstance(lat, (int, float)) and isinstance(lon, (int, float)) and isinstance(speed, (int, float)):
                items.append((float(lat), float(lon), float(speed)))

        if not items:
            return {"coords": np.empty((0, 2), dtype=np.float32), "speeds": np.empty((0,), dtype=np.float32)}

        arr = np.array(items, dtype=np.float32)
        return {
            "coords": arr[:, :2],
            "speeds": arr[:, 2],
        }

    def _get_congestion_threshold(self, speeds: np.ndarray) -> float:
        """基于百分位动态计算拥堵阈值：速度最低的 N% 且不超过绝对值上限。"""
        pct_speed = float(np.percentile(speeds, self.REROUTE_CONGESTION_PERCENTILE))
        return min(pct_speed, self.REROUTE_CONGESTION_MIN_KMH)

    def _has_predicted_congestion(self, sensor_ctx: Dict[str, Any]) -> bool:
        speeds = sensor_ctx.get("speeds")
        if speeds is None or speeds.shape[0] == 0:
            return False
        threshold = self._get_congestion_threshold(speeds)
        # 至少要有 3% 的传感器低于阈值，才认为存在值得重规划的拥堵
        congested_count = int(np.sum(speeds < threshold))
        min_congested = max(5, int(len(speeds) * 0.03))
        return congested_count >= min_congested

    def _interpolate_edge_speed(
        self,
        u: int,
        v: int,
        key: int,
        sensor_ctx: Dict[str, Any],
        edge_speed_cache: Dict[Tuple[int, int, int], Dict[str, float]],
        k_neighbors: int = 6,
        blend_alpha: float = None,
    ) -> Dict[str, float]:
        if blend_alpha is None:
            blend_alpha = self.BLEND_ALPHA

        edge_id = (u, v, key)
        if edge_id in edge_speed_cache:
            return edge_speed_cache[edge_id]

        static_speed = max(5.0, min(130.0, float(self._road_graph.get_edge_speed(u, v, key))))
        coords = sensor_ctx["coords"]
        speeds = sensor_ctx["speeds"]

        if coords.shape[0] == 0:
            result = {"speed_kmh": static_speed, "confidence": 0.0, "nearest_sensor_km": float("inf")}
            edge_speed_cache[edge_id] = result
            return result

        u_data = self._road_graph.G.nodes[u]
        v_data = self._road_graph.G.nodes[v]
        mid_lat = (u_data.get("y", 0) + v_data.get("y", 0)) / 2.0
        mid_lon = (u_data.get("x", 0) + v_data.get("x", 0)) / 2.0

        d2 = (coords[:, 0] - mid_lat) ** 2 + (coords[:, 1] - mid_lon) ** 2
        k = min(k_neighbors, d2.shape[0])

        if k == d2.shape[0]:
            idx = np.arange(d2.shape[0])
        else:
            idx = np.argpartition(d2, k - 1)[:k]

        dist_km = np.sqrt(d2[idx]) * 111.0
        weights = 1.0 / (dist_km + 0.08)
        pred_speed = float(np.sum(weights * speeds[idx]) / np.sum(weights))
        nearest_sensor_km = float(np.min(dist_km))
        confidence = max(0.0, min(1.0, 1.0 - nearest_sensor_km / self.SENSOR_TRUST_RADIUS_KM))

        # 如果预测和静态限速差不到 15%，直接用静态（避免噪声误导路径搜索）
        if abs(pred_speed - static_speed) / max(static_speed, 1.0) < 0.15:
            result = {"speed_kmh": static_speed, "confidence": 1.0, "nearest_sensor_km": nearest_sensor_km}
            edge_speed_cache[edge_id] = result
            return result

        fused = blend_alpha * pred_speed + (1.0 - blend_alpha) * static_speed
        fused = max(5.0, min(static_speed, float(fused)))
        result = {
            "speed_kmh": fused,
            "confidence": confidence,
            "nearest_sensor_km": nearest_sensor_km,
        }
        edge_speed_cache[edge_id] = result
        return result

    def _find_path(
        self,
        start_node: int,
        end_node: int,
        weight_type: str = "time",
        sensor_ctx: Dict[str, Any] = None,
    ) -> Tuple[Dict[str, Any], Dict[Tuple[int, int, int], float]]:
        import heapq

        G = self._road_graph.G
        if start_node not in G or end_node not in G:
            return None, {}

        use_predictive = sensor_ctx is not None
        edge_speed_cache: Dict[Tuple[int, int, int], Dict[str, float]] = {}

        open_set = [(0.0, start_node)]
        came_from: Dict[int, Tuple[int, Dict[str, Any]]] = {}
        g_score = {start_node: 0.0}

        while open_set:
            _, current = heapq.heappop(open_set)
            if current == end_node:
                break

            current_g = g_score.get(current, float("inf"))

            for neighbor in G.neighbors(current):
                best = None

                for key in G[current][neighbor]:
                    length = float(self._road_graph.get_edge_length(current, neighbor, key))
                    if length <= 0:
                        continue

                    if use_predictive:
                        speed_info = self._interpolate_edge_speed(
                            current, neighbor, key, sensor_ctx, edge_speed_cache
                        )
                        speed = speed_info["speed_kmh"]
                        confidence = speed_info["confidence"]
                        nearest_sensor_km = speed_info["nearest_sensor_km"]
                    else:
                        speed = float(self._road_graph.get_edge_speed(current, neighbor, key))
                        speed = max(5.0, min(130.0, speed))
                        confidence = 1.0
                        nearest_sensor_km = 0.0

                    speed_ms = speed * 1000.0 / 3600.0
                    edge_time = length / speed_ms if speed_ms > 0 else float("inf")
                    if use_predictive and confidence <= 0.0:
                        edge_time *= self.LOW_CONFIDENCE_TIME_PENALTY
                    edge_cost = length if weight_type == "distance" else edge_time

                    if best is None or edge_cost < best["edge_cost"]:
                        best = {
                            "key": key,
                            "length_m": length,
                            "time_s": edge_time,
                            "speed_kmh": speed,
                            "prediction_confidence": confidence,
                            "nearest_sensor_km": nearest_sensor_km,
                            "edge_cost": edge_cost,
                        }

                if best is None:
                    continue

                tentative_g = current_g + best["edge_cost"]
                if tentative_g < g_score.get(neighbor, float("inf")):
                    came_from[neighbor] = (current, best)
                    g_score[neighbor] = tentative_g
                    f_score = tentative_g + self._heuristic(neighbor, end_node)
                    heapq.heappush(open_set, (f_score, neighbor))

        if end_node not in came_from and start_node != end_node:
            return None, edge_speed_cache

        # reconstruct
        path_nodes = [end_node]
        edge_path = []
        segments = []
        cur = end_node
        while cur != start_node:
            prev, info = came_from[cur]
            edge_path.append((prev, cur, info["key"]))
            edge_coords = self._road_graph.get_edge_coords(prev, cur, info["key"])
            segments.append(
                {
                    "u": prev,
                    "v": cur,
                    "key": info["key"],
                    "length_m": round(info["length_m"], 1),
                    "time_s": round(info["time_s"], 2),
                    "speed_kmh": round(info["speed_kmh"], 3),
                    "prediction_confidence": round(info.get("prediction_confidence", 1.0), 3),
                    "nearest_sensor_km": round(info.get("nearest_sensor_km", 0.0), 3),
                            "max_speed_kmh": round(
                                float(self._road_graph.get_edge_speed(prev, cur, info["key"])), 3
                            ),
                            "speed_ratio": round(
                                info["speed_kmh"] / max(1.0, float(self._road_graph.get_edge_speed(prev, cur, info["key"]))),
                                4,
                            ),
                    "congestion_level": self._congestion_level(
                        info["speed_kmh"],
                        float(self._road_graph.get_edge_speed(prev, cur, info["key"])),
                    ),
                    "coords": edge_coords,
                }
            )
            path_nodes.append(prev)
            cur = prev

        path_nodes.reverse()
        edge_path.reverse()
        segments.reverse()

        total_distance = float(sum(s["length_m"] for s in segments))
        total_time = float(sum(s["time_s"] for s in segments))
        avg_speed = (total_distance / 1000.0) / (total_time / 3600.0) if total_time > 0 else 0.0

        route = {
            "path": path_nodes,
            "coords": self._road_graph.get_path_edge_coords(edge_path),
            "distance_m": round(total_distance, 1),
            "distance_km": round(total_distance / 1000.0, 2),
            "time_s": round(total_time, 1),
            "time_min": round(total_time / 60.0, 1),
            "avg_speed_kmh": round(avg_speed, 2),
            "segments": segments,
        }
        return route, edge_speed_cache

    def _build_congestion_segments(
        self,
        edge_speed_cache: Dict[Tuple[int, int, int], Dict[str, float]],
        top_n: int = 350,
    ) -> Dict[str, Any]:
        if top_n <= 0:
            top_n = 1
        top_n = min(top_n, 1200)

        if not edge_speed_cache:
            return {
                "segments": [],
                "stats": {
                    "evaluated_edges": 0,
                },
            }

        speeds = np.array([item["speed_kmh"] for item in edge_speed_cache.values()], dtype=np.float32)

        if speeds.size == 0:
            return {"segments": [], "stats": {"evaluated_edges": 0}}
        threshold = self._get_congestion_threshold(speeds)
        congested_items = [
            item for item in edge_speed_cache.items()
            if item[1]["speed_kmh"] < threshold
        ]
        sorted_items = sorted(congested_items, key=lambda x: x[1]["speed_kmh"])
        picked = sorted_items[: min(top_n, len(sorted_items))]

        segments = []
        for (u, v, key), speed_info in picked:
            speed = speed_info["speed_kmh"]
            u_data = self._road_graph.G.nodes[u]
            v_data = self._road_graph.G.nodes[v]
            length = self._road_graph.get_edge_length(u, v, key)
            segments.append(
                {
                    "u": u,
                    "v": v,
                    "key": key,
                    "speed_kmh": round(float(speed), 3),
                    "length_m": round(float(length), 1),
                    "max_speed_kmh": round(float(self._road_graph.get_edge_speed(u, v, key)), 3),
                    "speed_ratio": round(
                        float(speed) / max(1.0, float(self._road_graph.get_edge_speed(u, v, key))), 4
                    ),
                    "prediction_confidence": round(speed_info.get("confidence", 0.0), 3),
                    "nearest_sensor_km": round(speed_info.get("nearest_sensor_km", 0.0), 3),
                    "congestion_level": self._congestion_level(
                        float(speed), float(self._road_graph.get_edge_speed(u, v, key))
                    ),
                    "coords": [
                        [u_data.get("y", 0), u_data.get("x", 0)],
                        [v_data.get("y", 0), v_data.get("x", 0)],
                    ],
                }
            )

        stats = {
            "evaluated_edges": int(len(edge_speed_cache)),
            "min_speed_kmh": round(float(np.min(speeds)), 3),
            "max_speed_kmh": round(float(np.max(speeds)), 3),
            "avg_speed_kmh": round(float(np.mean(speeds)), 3),
            "p10_speed_kmh": round(float(np.percentile(speeds, 10)), 3),
            "severe_count": int(np.sum(speeds < 35)),
            "heavy_count": int(np.sum((speeds >= 35) & (speeds < 50))),
            "moderate_count": int(np.sum((speeds >= 50) & (speeds < 65))),
            "smooth_count": int(np.sum(speeds >= 65)),
            "reroute_threshold_kmh": round(float(threshold), 3),
            "reroute_congested_count": int(np.sum(speeds < threshold)),
            "reroute_percentile": self.REROUTE_CONGESTION_PERCENTILE,
        }

        return {
            "segments": segments,
            "stats": stats,
        }

    def plan_route(
        self,
        start_lat: float,
        start_lon: float,
        end_lat: float,
        end_lon: float,
        step: int = 1,
        weight_type: str = "time",
        congestion_top_n: int = 350,
    ) -> Dict[str, Any]:
        if weight_type not in ("time", "distance"):
            raise ValueError("weight_type 必须是 time 或 distance")

        with self._lock:
            prediction = self._prediction_service.predict(step=step, top_k=200)
            sensor_ctx = self._build_sensor_context(prediction)
            has_congestion = self._has_predicted_congestion(sensor_ctx)

            start_node = self._road_graph.get_nearest_node(start_lat, start_lon)
            end_node = self._road_graph.get_nearest_node(end_lat, end_lon)

            baseline_route, _ = self._find_path(
                start_node, end_node, weight_type=weight_type, sensor_ctx=None
            )
            if baseline_route is None:
                raise RuntimeError("基线路径不可达")

            if has_congestion:
                predictive_route, evaluated_edge_speeds = self._find_path(
                    start_node, end_node, weight_type=weight_type, sensor_ctx=sensor_ctx
                )
                if predictive_route is None:
                    raise RuntimeError("预测重规划路径不可达")
                reroute_reason = "predicted_congestion"
            else:
                predictive_route = baseline_route
                evaluated_edge_speeds = {}
                reroute_reason = "no_predicted_congestion"

            comparison = {
                "baseline_time_s": baseline_route["time_s"],
                "predictive_time_s": predictive_route["time_s"],
                "time_change_s": round(predictive_route["time_s"] - baseline_route["time_s"], 1),
                "time_change_percent": round(
                    ((predictive_route["time_s"] - baseline_route["time_s"]) / baseline_route["time_s"] * 100.0)
                    if baseline_route["time_s"] > 0 else 0.0,
                    2,
                ),
                "baseline_distance_km": baseline_route["distance_km"],
                "predictive_distance_km": predictive_route["distance_km"],
                "distance_change_km": round(predictive_route["distance_km"] - baseline_route["distance_km"], 3),
                "predictive_better": predictive_route["time_s"] < baseline_route["time_s"],
                "reroute_enabled": has_congestion,
                "reroute_reason": reroute_reason,
                "reroute_threshold_kmh": round(float(self._get_congestion_threshold(sensor_ctx["speeds"])), 3) if sensor_ctx.get("speeds") is not None and sensor_ctx["speeds"].size > 0 else self.REROUTE_CONGESTION_MIN_KMH,
            }

            congestion = self._build_congestion_segments(
                evaluated_edge_speeds,
                top_n=congestion_top_n,
            )

            return {
                "weight_type": weight_type,
                "prediction": {
                    "selected_step": prediction.get("selected_step"),
                    "selected_horizon_minutes": prediction.get("selected_horizon_minutes"),
                    "summary": prediction.get("summary", {}),
                },
                "baseline_route": baseline_route,
                "predictive_route": predictive_route,
                "comparison": comparison,
                "congestion": congestion,
            }
