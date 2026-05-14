"""
动态路由服务 — 时变 A* + TGCN 预测

对外提供统一接口，内部协调：
  TrafficPredictionService → 方差恢复后的多步预测
  DynamicEdgeWeightManager → 时变边权
  TimeDependentAStar       → 时变 A* 搜索
"""

import time as _time
import math
import threading
import numpy as np
from typing import Dict, Any, Optional

from backend.graph.road_graph import RoadGraph
from backend.prediction.traffic_prediction_service import TrafficPredictionService
from backend.routing.dynamic_edge_weight import DynamicEdgeWeightManager
from backend.routing.time_dependent_astar import TimeDependentAStar


class DynamicRouterService:
    """时变动态路径规划服务（单例）。"""

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

    def find_dynamic_route(
        self,
        start_lat: float,
        start_lon: float,
        end_lat: float,
        end_lon: float,
        departure_time: Optional[int] = None,
        vehicle_type: str = "gasoline",
        time_of_day: str = "normal",
    ) -> Dict[str, Any]:
        """
        时变动态路径规划。

        Args:
            start_lat, start_lon: 起点经纬度
            end_lat, end_lon: 终点经纬度
            departure_time: 出发 Unix 时间戳，None 表示当前时间
            vehicle_type: 车辆类型
            time_of_day: 时段 (normal / morning_peak / evening_peak / night)
        """
        if departure_time is None:
            departure_time = int(_time.time())

        with self._lock:
            # 1. 获取多步预测
            predictions, station_ids, sensor_meta = self._prediction_service.predict_all_steps()
            # predictions: (pre_len, num_sensors)

            # 2. 构建传感器坐标矩阵
            coords_list = []
            for sid in station_ids:
                meta = sensor_meta.get(sid, {})
                coords_list.append([meta.get("latitude", 0.0), meta.get("longitude", 0.0)])
            sensor_coords = np.array(coords_list, dtype=np.float32)

            # 3. 创建动态边权管理器
            weight_mgr = DynamicEdgeWeightManager(
                road_graph=self._road_graph,
                predictions=predictions,
                sensor_coords=sensor_coords,
            )

            # 4. 创建时变 A* 并搜索
            astar = TimeDependentAStar(self._road_graph, weight_mgr)

            start_node = self._road_graph.get_nearest_node(start_lat, start_lon)
            end_node = self._road_graph.get_nearest_node(end_lat, end_lon)

            t0 = _time.time()
            result = astar.find_path(
                start_node, end_node,
                departure_time=departure_time,
                vehicle_type=vehicle_type,
                time_of_day=time_of_day,
            )
            compute_ms = (_time.time() - t0) * 1000.0

            if result is None:
                return {"success": False, "error": "路径不可达"}

            # 5. 同时计算静态基线（用 OSM 默认速度）
            baseline = self._compute_baseline(start_node, end_node)

            comparison = {}
            if baseline:
                comparison = {
                    "baseline_time_s": baseline["time_s"],
                    "dynamic_time_s": result["time_s"],
                    "time_change_s": round(result["time_s"] - baseline["time_s"], 1),
                    "time_change_percent": round(
                        (result["time_s"] - baseline["time_s"]) / baseline["time_s"] * 100
                        if baseline["time_s"] > 0 else 0.0, 2
                    ),
                    "baseline_distance_km": baseline["distance_km"],
                    "dynamic_distance_km": result["distance_km"],
                }

            return {
                "success": True,
                "route": result,
                "baseline": baseline,
                "comparison": comparison,
                "prediction_info": {
                    "steps": predictions.shape[0],
                    "horizon_minutes": predictions.shape[0] * 5,
                    "step_stats": [
                        {
                            "step": i + 1,
                            "horizon_minutes": (i + 1) * 5,
                            "avg_speed_kmh": round(float(predictions[i].mean()), 2),
                            "min_speed_kmh": round(float(predictions[i].min()), 2),
                            "max_speed_kmh": round(float(predictions[i].max()), 2),
                        }
                        for i in range(predictions.shape[0])
                    ],
                },
                "compute_ms": round(compute_ms, 1),
            }

    def _compute_baseline(self, start_node: int, end_node: int) -> Optional[Dict]:
        """用 OSM 静态速度计算基线路径。"""
        import heapq

        G = self._road_graph.G
        if start_node not in G or end_node not in G:
            return None

        def h(n, goal):
            nd = G.nodes[n]
            gd = G.nodes[goal]
            return self._haversine(nd.get("y", 0), nd.get("x", 0), gd.get("y", 0), gd.get("x", 0))

        open_set = [(0.0, start_node)]
        came_from = {}
        g = {start_node: 0.0}

        while open_set:
            _, cur = heapq.heappop(open_set)
            if cur == end_node:
                break
            for nb in G.neighbors(cur):
                best_cost = float("inf")
                for key in G[cur][nb]:
                    t = self._road_graph.get_edge_weight(cur, nb, key, "time")
                    if t < best_cost:
                        best_cost = t
                if best_cost >= float("inf"):
                    continue
                tentative = g.get(cur, float("inf")) + best_cost
                if tentative < g.get(nb, float("inf")):
                    came_from[nb] = cur
                    g[nb] = tentative
                    heapq.heappush(open_set, (tentative + h(nb, end_node), nb))

        if end_node not in came_from and start_node != end_node:
            return None

        path = [end_node]
        c = end_node
        while c in came_from:
            c = came_from[c]
            path.append(c)
        path.reverse()

        total_dist = 0.0
        total_t = 0.0
        for i in range(len(path) - 1):
            u, v = path[i], path[i + 1]
            best_t = float("inf")
            best_l = 0.0
            for key in G[u][v]:
                l = self._road_graph.get_edge_length(u, v, key)
                t = self._road_graph.get_edge_weight(u, v, key, "time")
                if t < best_t:
                    best_t = t
                    best_l = l
            total_dist += best_l
            total_t += best_t

        avg_spd = (total_dist / 1000.0) / (total_t / 3600.0) if total_t > 0 else 0.0
        return {
            "path": path,
            "coords": self._road_graph.get_path_coords(path),
            "distance_m": round(total_dist, 1),
            "distance_km": round(total_dist / 1000.0, 2),
            "time_s": round(total_t, 1),
            "time_min": round(total_t / 60.0, 1),
            "avg_speed_kmh": round(avg_spd, 2),
        }

    @staticmethod
    def _haversine(lat1, lon1, lat2, lon2) -> float:
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
