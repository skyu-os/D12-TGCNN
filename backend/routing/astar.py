"""
A* 路径规划算法
基于路网图的启发式最短路径搜索
"""

import heapq
import math
from typing import List, Tuple, Optional


class AStarRouter:
    """A* 路径规划器"""

    def __init__(self, graph):
        """
        Args:
            graph: RoadGraph 实例
        """
        self.G = graph.G
        self.graph = graph

    def _haversine(self, lat1: float, lon1: float, lat2: float, lon2: float) -> float:
        """计算两点间球面距离（米）- 作为 A* 启发函数"""
        R = 6371000  # 地球半径（米）
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
        """启发函数：当前节点到终点的直线距离"""
        node_data = self.G.nodes[node]
        goal_data = self.G.nodes[goal]
        return self._haversine(
            node_data.get("y", 0),
            node_data.get("x", 0),
            goal_data.get("y", 0),
            goal_data.get("x", 0),
        )

    def find_path(
        self, start_node: int, end_node: int, weight_type: str = "time"
    ) -> Optional[dict]:
        """
        A* 搜索最短路径

        Args:
            start_node: 起点节点 ID
            end_node: 终点节点 ID
            weight_type: 'time' | 'distance'

        Returns:
            {
                'path': [node_ids],
                'coords': [(lat, lon), ...],
                'distance_m': float,
                'time_s': float,
            } 或 None（不可达）
        """
        if start_node not in self.G or end_node not in self.G:
            return None

        # A* 核心
        open_set = [(0, start_node)]  # (f_score, node)
        came_from = {}
        g_score = {start_node: 0}
        f_score = {start_node: self._heuristic(start_node, end_node)}

        while open_set:
            current_f, current = heapq.heappop(open_set)

            if current == end_node:
                return self._reconstruct_path(came_from, current)

            for neighbor in self.G.neighbors(current):
                # 获取边权重（可能有平行边，取最小的）
                best_key = None
                best_weight = None
                for key in self.G[current][neighbor]:
                    edge_weight = self.graph.get_edge_weight(current, neighbor, key, weight_type)
                    if best_weight is None or edge_weight < best_weight:
                        best_weight = edge_weight
                        best_key = key
                if best_weight is None:
                    continue

                tentative_g = g_score[current] + best_weight

                if tentative_g < g_score.get(neighbor, float("inf")):
                    came_from[neighbor] = (current, best_key)
                    g_score[neighbor] = tentative_g
                    f = tentative_g + self._heuristic(neighbor, end_node)
                    f_score[neighbor] = f
                    heapq.heappush(open_set, (f, neighbor))

        return None  # 不可达

    def _reconstruct_path(self, came_from: dict, current: int) -> dict:
        """重建路径并计算统计信息"""
        path = [current]
        edge_path = []
        while current in came_from:
            previous, key = came_from[current]
            edge_path.append((previous, current, key))
            current = previous
            path.append(current)
        path.reverse()
        edge_path.reverse()

        # 计算距离和时间
        total_distance = 0
        total_time = 0
        for u, v, key in edge_path:
            total_distance += self.graph.get_edge_length(u, v, key)
            total_time += self.graph.get_edge_weight(u, v, key, "time")

        coords = self.graph.get_path_edge_coords(edge_path)

        return {
            "path": path,
            "coords": coords,
            "distance_m": round(total_distance, 1),
            "distance_km": round(total_distance / 1000, 2),
            "time_s": round(total_time, 1),
            "time_min": round(total_time / 60, 1),
        }
