"""
时变 A* 路径规划算法

核心特点：跟踪每个节点的到达时间，用不同时刻的预测速度计算边权。
g_score 存储的是到达时间（秒），而非静态代价。
"""

import heapq
import math
from typing import Optional, Dict, List, Tuple

from backend.routing.dynamic_edge_weight import DynamicEdgeWeightManager
from backend.routing.intersection_constraints import (
    IntersectionConstraints,
    EdgeBearingCalculator,
    create_default_constraints,
)


class TimeDependentAStar:
    """时变 A*：边权随到达时间变化。"""

    def __init__(
        self,
        road_graph,
        weight_manager: DynamicEdgeWeightManager,
        constraints: Optional[IntersectionConstraints] = None,
    ):
        self.G = road_graph.G
        self.graph = road_graph
        self.weight_manager = weight_manager
        self.constraints = constraints or create_default_constraints()
        self.bearing_calc = EdgeBearingCalculator()

    def _haversine(self, lat1, lon1, lat2, lon2) -> float:
        R = 6371000.0
        dlat = math.radians(lat2 - lat1)
        dlon = math.radians(lon2 - lon1)
        a = (
            math.sin(dlat / 2) ** 2
            + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon / 2) ** 2
        )
        return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))

    def _heuristic(self, node: int, goal: int) -> float:
        """启发函数：直线距离 / 最高可能速度（乐观估计，秒）。"""
        nd = self.G.nodes[node]
        gd = self.G.nodes[goal]
        dist = self._haversine(nd.get("y", 0), nd.get("x", 0), gd.get("y", 0), gd.get("x", 0))
        return dist / (100.0 / 3.6)

    def _intersection_delay(self, u: int, v: int, prev_node, time_of_day: str) -> float:
        if prev_node is None:
            return 0.0

        in_bearing = self.bearing_calc.calculate_edge_bearing(self.G, prev_node, u)
        out_bearing = self.bearing_calc.calculate_edge_bearing(self.G, u, v)

        from backend.routing.intersection_constraints import TurnType
        turn_type = self.constraints.detect_turn_type(in_bearing, out_bearing)
        turn_penalty = self.constraints.get_turn_penalty(turn_type)

        node_degree = self.G.degree(u)
        road_types = []
        for nb in self.G.neighbors(u):
            for k in self.G[u][nb]:
                ht = self.G.edges[u, nb, k].get("highway", "primary")
                if isinstance(ht, list):
                    ht = ht[0]
                road_types.append(ht)
                break

        from backend.routing.intersection_constraints import IntersectionType
        itype = self.constraints.estimate_intersection_type(node_degree, road_types)
        signal_wait = self.constraints.get_signal_wait_time(itype, time_of_day)
        if turn_type == TurnType.THROUGH:
            # 直行 = 绿波通过
            signal_wait = 0.0
            startup = 0.0
        else:
            startup = self.constraints.get_startup_time(itype)

        return turn_penalty + signal_wait + startup

    def find_path(
        self,
        start_node: int,
        end_node: int,
        departure_time: int,
        vehicle_type: str = "gasoline",
        time_of_day: str = "normal",
    ) -> Optional[Dict]:
        """
        时变 A* 搜索。

        Args:
            start_node: 起点
            end_node: 终点
            departure_time: 出发时间（Unix 时间戳，仅用于计算 elapsed）
            vehicle_type: 车辆类型
            time_of_day: 时段

        Returns:
            路径信息字典 或 None
        """
        if start_node not in self.G or end_node not in self.G:
            return None

        self.weight_manager.clear_cache()

        # (f_score, counter, arrival_elapsed, node, prev_node)
        counter = 0
        open_set = [(0.0, counter, 0.0, start_node, None)]
        came_from: Dict[int, Tuple[int, int, int, float, float]] = {}
        # node -> (arrival_elapsed, f_score)
        best_elapsed = {start_node: 0.0}

        while open_set:
            f, _, elapsed, current, prev_node = heapq.heappop(open_set)

            if current == end_node:
                return self._reconstruct(came_from, current, departure_time)

            if elapsed > best_elapsed.get(current, float("inf")) + 0.1:
                continue

            for neighbor in self.G.neighbors(current):
                best_edge_time = float("inf")
                best_key = 0

                for key in self.G[current][neighbor]:
                    edge_time = self.weight_manager.calculate_edge_weight(
                        current, neighbor, key, elapsed
                    )
                    if edge_time < best_edge_time:
                        best_edge_time = edge_time
                        best_key = key

                if best_edge_time >= float("inf"):
                    continue

                delay = self._intersection_delay(current, neighbor, prev_node, time_of_day)
                new_elapsed = elapsed + best_edge_time + delay

                if new_elapsed < best_elapsed.get(neighbor, float("inf")):
                    best_elapsed[neighbor] = new_elapsed
                    came_from[neighbor] = (current, best_key, elapsed, best_edge_time, delay)

                    h = self._heuristic(neighbor, end_node)
                    f_new = new_elapsed + h
                    counter += 1
                    heapq.heappush(open_set, (f_new, counter, new_elapsed, neighbor, current))

        return None

    def _reconstruct(
        self,
        came_from: Dict,
        end_node: int,
        departure_time: int,
    ) -> Dict:
        path = [end_node]
        edges = []
        cur = end_node

        while cur in came_from:
            prev, key, dep_elapsed, edge_time, delay = came_from[cur]
            path.append(prev)
            edges.append((prev, cur, key, dep_elapsed, edge_time, delay))
            cur = prev

        path.reverse()
        edges.reverse()

        total_distance = 0.0
        total_time = 0.0
        total_delay = 0.0
        segments = []

        for u, v, key, dep_e, e_time, delay in edges:
            length = self.graph.get_edge_length(u, v, key)
            speed = (length / e_time * 3.6) if e_time > 0 else 0.0

            total_distance += length
            total_time += e_time + delay
            total_delay += delay

            u_data = self.G.nodes[u]
            v_data = self.G.nodes[v]
            segments.append({
                "u": u, "v": v, "key": key,
                "length_m": round(length, 1),
                "time_s": round(e_time, 2),
                "delay_s": round(delay, 2),
                "speed_kmh": round(speed, 2),
                "elapsed_s": round(dep_e, 1),
                "coords": [
                    [u_data.get("y", 0), u_data.get("x", 0)],
                    [v_data.get("y", 0), v_data.get("x", 0)],
                ],
            })

        coords = self.graph.get_path_coords(path)
        avg_speed = (total_distance / 1000.0) / (total_time / 3600.0) if total_time > 0 else 0.0

        return {
            "path": path,
            "coords": coords,
            "distance_m": round(total_distance, 1),
            "distance_km": round(total_distance / 1000.0, 2),
            "time_s": round(total_time, 1),
            "time_min": round(total_time / 60.0, 1),
            "avg_speed_kmh": round(avg_speed, 2),
            "total_intersection_delay_s": round(total_delay, 1),
            "segments": segments,
            "departure_time": departure_time,
        }
