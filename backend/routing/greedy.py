"""
贪心路径规划算法
基于启发式的贪心搜索算法
"""

import heapq
import math
from typing import Optional


class GreedyRouter:
    """贪心路径规划器"""

    def __init__(self, graph):
        """
        Args:
            graph: RoadGraph 实例
        """
        self.G = graph.G
        self.graph = graph

    def _haversine(self, lat1: float, lon1: float, lat2: float, lon2: float) -> float:
        """计算两点间球面距离（米）"""
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
        贪心搜索路径

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

        # 贪心算法核心
        # 只使用启发函数（到终点的直线距离）来选择下一个节点
        current = start_node
        path = [current]
        visited = {current}

        max_iterations = 10000  # 防止无限循环
        iterations = 0

        while current != end_node and iterations < max_iterations:
            iterations += 1

            # 找到所有未访问的邻居
            neighbors = [
                n for n in self.G.neighbors(current) 
                if n not in visited
            ]

            if not neighbors:
                # 没有未访问的邻居，回溯
                if len(path) > 1:
                    path.pop()
                    current = path[-1]
                    continue
                else:
                    return None  # 无法到达

            # 选择距离终点最近的邻居（贪心策略）
            best_neighbor = None
            best_distance = float("inf")

            for neighbor in neighbors:
                distance = self._heuristic(neighbor, end_node)
                if distance < best_distance:
                    best_distance = distance
                    best_neighbor = neighbor

            if best_neighbor is None:
                return None  # 无法找到路径

            # 移动到最佳邻居
            current = best_neighbor
            path.append(current)
            visited.add(current)

        # 检查是否找到终点
        if current != end_node:
            return None  # 超过最大迭代次数，未找到路径

        # 计算距离和时间
        total_distance = 0
        total_time = 0
        for i in range(len(path) - 1):
            u, v = path[i], path[i + 1]
            # 取最短边
            min_length = float("inf")
            min_time = float("inf")
            for key in self.G[u][v]:
                length = self.graph.get_edge_length(u, v, key)
                time = self.graph.get_edge_weight(u, v, key, "time")
                if length < min_length:
                    min_length = length
                    min_time = time
            total_distance += min_length
            total_time += min_time

        coords = self.graph.get_path_coords(path)

        return {
            "path": path,
            "coords": coords,
            "distance_m": round(total_distance, 1),
            "distance_km": round(total_distance / 1000, 2),
            "time_s": round(total_time, 1),
            "time_min": round(total_time / 60, 1),
        }
