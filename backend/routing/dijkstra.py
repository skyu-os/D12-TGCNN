"""
Dijkstra 路径规划算法
经典的最短路径搜索算法
"""

import heapq
from typing import Optional


class DijkstraRouter:
    """Dijkstra 路径规划器"""

    def __init__(self, graph):
        """
        Args:
            graph: RoadGraph 实例
        """
        self.G = graph.G
        self.graph = graph

    def find_path(
        self, start_node: int, end_node: int, weight_type: str = "time"
    ) -> Optional[dict]:
        """
        Dijkstra 搜索最短路径

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

        # Dijkstra 核心
        # 使用优先队列 (distance, node)
        open_set = [(0, start_node)]
        came_from = {}
        cost_so_far = {start_node: 0}

        while open_set:
            current_cost, current = heapq.heappop(open_set)

            # 如果找到终点，重建路径
            if current == end_node:
                return self._reconstruct_path(came_from, current)

            # 如果当前节点已经被更优的路径访问过，跳过
            if current_cost > cost_so_far.get(current, float("inf")):
                continue

            # 遍历邻居节点
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

                new_cost = cost_so_far[current] + best_weight

                # 如果找到更短的路径
                if new_cost < cost_so_far.get(neighbor, float("inf")):
                    cost_so_far[neighbor] = new_cost
                    came_from[neighbor] = (current, best_key)
                    heapq.heappush(open_set, (new_cost, neighbor))

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
