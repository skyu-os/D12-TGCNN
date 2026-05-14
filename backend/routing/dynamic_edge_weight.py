"""
时变动态边权管理器

根据 TGCN 多步预测速度和到达时间，计算每条边的动态行驶时间。
"""

import math
import numpy as np
from typing import Dict, Tuple, Optional


class DynamicEdgeWeightManager:
    """时变边权计算：根据到达边的时间查不同预测步的速度。"""

    def __init__(
        self,
        road_graph,
        predictions: np.ndarray,
        sensor_coords: np.ndarray,
        step_interval_seconds: int = 300,
        k_neighbors: int = 6,
    ):
        """
        Args:
            road_graph: RoadGraph 实例
            predictions: (pre_len, num_sensors) 方差恢复后的预测速度 (km/h)
            sensor_coords: (num_sensors, 2) 传感器 [lat, lon]
            step_interval_seconds: 预测步间隔（秒），默认 300s=5min
            k_neighbors: 空间插值近邻数
        """
        self.road_graph = road_graph
        self.predictions = predictions
        self.sensor_coords = sensor_coords
        self.step_interval = step_interval_seconds
        self.k_neighbors = k_neighbors
        self.pre_len = predictions.shape[0]

        self._default_speeds = {
            "motorway": 100.0, "trunk": 80.0, "primary": 60.0,
            "secondary": 50.0, "tertiary": 40.0, "residential": 30.0,
        }

        self._edge_cache: Dict[Tuple[int, int, int, int], float] = {}

    def _get_default_speed(self, u: int, v: int, key: int) -> float:
        edge_data = self.road_graph.G.edges[u, v, key]
        highway = edge_data.get("highway", "primary")
        if isinstance(highway, list):
            highway = highway[0]
        return self._default_speeds.get(highway, 40.0)

    def _interpolate_speed(self, u: int, v: int, key: int, step_speeds: np.ndarray) -> float:
        if self.sensor_coords.shape[0] == 0:
            return self._get_default_speed(u, v, key)

        u_data = self.road_graph.G.nodes[u]
        v_data = self.road_graph.G.nodes[v]
        mid_lat = (u_data.get("y", 0) + v_data.get("y", 0)) / 2.0
        mid_lon = (u_data.get("x", 0) + v_data.get("x", 0)) / 2.0

        d2 = (self.sensor_coords[:, 0] - mid_lat) ** 2 + (self.sensor_coords[:, 1] - mid_lon) ** 2
        k = min(self.k_neighbors, d2.shape[0])

        if k == d2.shape[0]:
            idx = np.arange(d2.shape[0])
        else:
            idx = np.argpartition(d2, k - 1)[:k]

        dist_km = np.sqrt(d2[idx]) * 111.0
        weights = 1.0 / (dist_km + 0.08)
        pred_speed = float(np.sum(weights * step_speeds[idx]) / np.sum(weights))
        return max(5.0, min(130.0, pred_speed))

    def _get_step_speeds(self, elapsed_seconds: float) -> np.ndarray:
        if self.pre_len == 1 or elapsed_seconds <= 0:
            return self.predictions[0]

        step_float = elapsed_seconds / self.step_interval
        step_idx = int(step_float)

        if step_idx >= self.pre_len - 1:
            return self.predictions[-1]

        alpha = step_float - step_idx
        return (1.0 - alpha) * self.predictions[step_idx] + alpha * self.predictions[step_idx + 1]

    def calculate_edge_weight(
        self, u: int, v: int, key: int, elapsed_seconds: float
    ) -> float:
        """
        计算边 (u,v,key) 在出发后 elapsed_seconds 时的行驶时间（秒）。

        Args:
            u, v, key: 边标识
            elapsed_seconds: 从出发时刻起的秒数
        """
        quantized = int(elapsed_seconds // 30) * 30
        cache_key = (u, v, key, quantized)
        if cache_key in self._edge_cache:
            return self._edge_cache[cache_key]

        length = self.road_graph.get_edge_length(u, v, key)
        if length <= 0:
            self._edge_cache[cache_key] = 0.0
            return 0.0

        step_speeds = self._get_step_speeds(elapsed_seconds)
        speed_kmh = self._interpolate_speed(u, v, key, step_speeds)

        speed_ms = speed_kmh * 1000.0 / 3600.0
        travel_time = length / speed_ms if speed_ms > 0 else float("inf")

        self._edge_cache[cache_key] = travel_time
        return travel_time

    def clear_cache(self):
        self._edge_cache.clear()
