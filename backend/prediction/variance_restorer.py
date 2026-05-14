"""
TGCN 预测方差恢复器

解决模型均值回归问题：TGCN 全局归一化导致预测速度空间差异被压缩。
通过 per-sensor Z-score 变换，利用历史统计恢复空间变异性。
"""

import os
import threading
import numpy as np
import pandas as pd
from typing import Dict, Tuple, Optional


class VarianceRestorer:
    """基于 per-sensor 历史统计的方差恢复。"""

    _instance = None
    _lock = threading.Lock()

    @classmethod
    def get_instance(cls, speed_csv_path: str = None):
        with cls._lock:
            if cls._instance is None:
                cls._instance = cls(speed_csv_path)
            return cls._instance

    def __init__(self, speed_csv_path: str = None):
        if speed_csv_path is None:
            project_root = os.path.dirname(
                os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            )
            speed_csv_path = os.path.join(
                project_root,
                "TGCN", "tgcn_pytorch", "data", "recommended_real", "d12_speed.csv",
            )
        self._sensor_mean: Optional[np.ndarray] = None
        self._sensor_std: Optional[np.ndarray] = None
        self._speed_csv_path = speed_csv_path
        self._num_sensors = 0
        self._compute_stats()

    def _compute_stats(self):
        data = np.array(pd.read_csv(self._speed_csv_path), dtype=np.float32)
        self._sensor_mean = data.mean(axis=0)
        self._sensor_std = data.std(axis=0)
        self._num_sensors = data.shape[1]

    def restore(self, predictions: np.ndarray) -> np.ndarray:
        """
        对 TGCN 原始预测应用 Z-score 方差恢复。

        Args:
            predictions: shape=(pre_len, num_sensors) 的原始预测速度

        Returns:
            恢复后的预测速度，shape 不变
        """
        restored = np.empty_like(predictions)
        for t in range(predictions.shape[0]):
            frame = predictions[t]
            frame_mean = frame.mean()
            frame_std = frame.std()

            if frame_std < 1e-6:
                restored[t] = self._sensor_mean[: len(frame)]
                continue

            z = (frame - frame_mean) / frame_std
            restored[t] = z * self._sensor_std[: len(frame)] + self._sensor_mean[: len(frame)]

            restored[t] = np.clip(restored[t], 5.0, 130.0)

        return restored

    @property
    def num_sensors(self) -> int:
        return self._num_sensors

    @property
    def sensor_mean(self) -> np.ndarray:
        return self._sensor_mean

    @property
    def sensor_std(self) -> np.ndarray:
        return self._sensor_std
