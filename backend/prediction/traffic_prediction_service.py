"""
交通预测服务（TGCN 推理）。

职责：
1. 懒加载已训练模型（recommended 配置）
2. 读取真实速度矩阵（recommended_real）
3. 输出可直接给前端渲染的预测摘要与传感器明细
"""

import os
import sys
import csv
import time
import threading
from datetime import datetime
from typing import Dict, List, Any, Optional, Tuple

import numpy as np
import pandas as pd

from backend.graph.sensor_parser import parse_sensors
from backend.prediction.variance_restorer import VarianceRestorer


def _idw_extend_sensor_predictions(
    base_predictions: np.ndarray,
    base_sensor_ids: List[int],
    all_sensors: List[Dict[str, Any]],
    n_neighbors: int = 6,
) -> List[Dict[str, Any]]:
    """
    用反距离加权（IDW）将 TGCN 的 base_predictions 扩展到全部传感器。

    Args:
        base_predictions: shape=(pre_len, num_base) 已知预测速度
        base_sensor_ids: 对应的传感器 ID 列表
        all_sensors: 全部传感器列表，每个包含 id/latitude/longitude
        n_neighbors: 最近邻数量

    Returns:
        全部传感器的预测列表，每项包含 pred_speed_kmh / is_interpolated 等
    """
    base_id_set = set(base_sensor_ids)
    base_idx = {sid: i for i, sid in enumerate(base_sensor_ids)}

    base_coords = np.array(
        [[s["latitude"], s["longitude"]] for s in all_sensors if s["id"] in base_id_set],
        dtype=np.float64,
    )
    base_sids_ordered = [s["id"] for s in all_sensors if s["id"] in base_id_set]

    if base_coords.size == 0:
        return []

    pre_len = base_predictions.shape[0]
    results: List[Dict[str, Any]] = []

    for sensor in all_sensors:
        sid = sensor["id"]
        lat, lon = sensor.get("latitude"), sensor.get("longitude")
        if lat is None or lon is None:
            continue

        if sid in base_idx:
            col = base_idx[sid]
            speed = float(base_predictions[0, col]) if base_predictions.ndim == 2 else float(base_predictions[col])
            results.append(
                {
                    "sensor_id": sid,
                    "pred_speed_kmh": round(speed, 3),
                    "fwy": sensor.get("fwy"),
                    "dir": sensor.get("dir"),
                    "name": sensor.get("name"),
                    "latitude": lat,
                    "longitude": lon,
                    "is_interpolated": False,
                }
            )
            continue

        dists = np.sqrt(
            (base_coords[:, 0] - lat) ** 2 + (base_coords[:, 1] - lon) ** 2
        )
        k = min(n_neighbors, len(dists))
        nearest = np.argpartition(dists, k)[:k]
        nearest_dists = dists[nearest]

        mask = nearest_dists < 1e-8
        if mask.any():
            idx = nearest[mask][0]
            mapped_sid = base_sids_ordered[idx]
            col = base_idx[mapped_sid]
            speed = float(base_predictions[0, col]) if base_predictions.ndim == 2 else float(base_predictions[col])
        else:
            weights = 1.0 / (nearest_dists + 1e-9)
            weights /= weights.sum()
            cols = [base_idx[base_sids_ordered[i]] for i in nearest]
            if base_predictions.ndim == 2:
                speeds = base_predictions[0, cols].astype(np.float64)
            else:
                speeds = base_predictions[cols].astype(np.float64)
            speed = float(np.dot(weights, speeds))

        results.append(
            {
                "sensor_id": sid,
                "pred_speed_kmh": round(speed, 3),
                "fwy": sensor.get("fwy"),
                "dir": sensor.get("dir"),
                "name": sensor.get("name"),
                "latitude": lat,
                "longitude": lon,
                "is_interpolated": True,
            }
        )

    return results


class TrafficPredictionService:
    """基于已训练 TGCN 模型的交通预测单例服务。"""

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
        self._predictor = None
        self._station_ids: List[int] = []
        self._speed_cache = None
        self._speed_cache_mtime = None
        self._restorer: Optional[VarianceRestorer] = None

        self._project_root = os.path.dirname(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        )
        self._tgcn_root = os.path.join(self._project_root, "TGCN")
        self._tgcn_pytorch_dir = os.path.join(self._tgcn_root, "tgcn_pytorch")

        # 检查实际的模型文件位置
        recommended_model = os.path.join(
            self._tgcn_root, "save-model", "recommended", "TGCN_best.pth"
        )
        root_model = os.path.join(
            self._tgcn_root, "save-model", "TGCN_best.pth"
        )

        # 检查站点列表文件
        top200_stations = os.path.join(
            self._tgcn_root, "data", "d12_data", "top200_stations.txt"
        )
        top500_stations = os.path.join(
            self._tgcn_root, "data", "d12_data", "top500_stations.txt"
        )

        # 设置默认配置（推荐配置）
        if os.path.exists(recommended_model):
            self._model_path = recommended_model
            self._speed_path = os.path.join(self._tgcn_root, "tgcn_pytorch", "data", "recommended_real", "d12_speed.csv")
            self._station_list_path = top200_stations if os.path.exists(top200_stations) else top500_stations
            self._model_profile = "recommended"
        elif os.path.exists(root_model):
            self._model_path = root_model
            self._speed_path = os.path.join(self._tgcn_root, "data", "d12_speed.csv")
            self._station_list_path = top500_stations if os.path.exists(top500_stations) else top200_stations
            self._model_profile = "all_sensors"
        else:
            # 默认值，稍后会报错
            self._model_path = recommended_model
            self._speed_path = os.path.join(self._tgcn_root, "tgcn_pytorch", "data", "recommended_real", "d12_speed.csv")
            self._station_list_path = top200_stations if os.path.exists(top200_stations) else top500_stations
            self._model_profile = "recommended"

        self._meta_path_candidates = [
            os.path.join(
                self._tgcn_root,
                "data",
                "d12_data",
                "data",
                "d12_text_meta_2023_12_05.txt",
            ),
            os.path.join(
                self._project_root,
                "data",
                "osm",
                "d12_text_meta_2023_12_05.txt",
            ),
        ]

        self._sensor_by_id = self._load_sensor_metadata_by_id()
        if not self._sensor_by_id:
            self._sensor_by_id = {s["id"]: s for s in parse_sensors()}

        self._all_sensors: List[Dict[str, Any]] = list(self._sensor_by_id.values())
        self._tgcn_station_set: Optional[set] = None

        try:
            self._restorer = VarianceRestorer.get_instance(self._speed_path)
        except Exception:
            self._restorer = None

    def _project_rel(self, abs_path: str) -> str:
        return os.path.relpath(abs_path, self._project_root).replace("\\", "/")

    def _resolve_meta_path(self):
        for p in self._meta_path_candidates:
            if os.path.exists(p):
                return p
        return None

    def _load_sensor_metadata_by_id(self) -> Dict[int, Dict[str, Any]]:
        meta_path = self._resolve_meta_path()
        if not meta_path:
            return {}

        sensor_by_id: Dict[int, Dict[str, Any]] = {}
        with open(meta_path, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f, delimiter="\t")
            for row in reader:
                try:
                    sensor_id = int(row.get("ID", "").strip())
                    lat = float(row.get("Latitude", "").strip())
                    lon = float(row.get("Longitude", "").strip())
                except (ValueError, TypeError):
                    continue

                sensor_by_id[sensor_id] = {
                    "id": sensor_id,
                    "fwy": row.get("Fwy", "").strip(),
                    "dir": row.get("Dir", "").strip(),
                    "name": row.get("Name", "").strip(),
                    "latitude": lat,
                    "longitude": lon,
                }

        return sensor_by_id

    def _ensure_paths(self):
        missing = []
        for p in (self._model_path, self._speed_path, self._station_list_path):
            if not os.path.exists(p):
                missing.append(self._project_rel(p))
        if missing:
            raise FileNotFoundError(f"缺少预测文件: {', '.join(missing)}")

    def _load_station_ids(self, expected_nodes: int) -> List[int]:
        ids = []
        with open(self._station_list_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    ids.append(int(line))

        if len(ids) < expected_nodes:
            raise ValueError(
                f"站点列表数量不足: {len(ids)} < 模型节点数 {expected_nodes}"
            )
        return ids[:expected_nodes]

    def _load_predictor_locked(self):
        if self._predictor is not None:
            return

        if self._tgcn_pytorch_dir not in sys.path:
            sys.path.insert(0, self._tgcn_pytorch_dir)

        from predict import TGCNPredictor

        self._predictor = TGCNPredictor(self._model_path)
        self._station_ids = self._load_station_ids(self._predictor.num_nodes)
        self._tgcn_station_set = set(self._station_ids)

    def _load_speed_data_locked(self) -> np.ndarray:
        mtime = os.path.getmtime(self._speed_path)
        if self._speed_cache is not None and self._speed_cache_mtime == mtime:
            return self._speed_cache

        data = np.array(pd.read_csv(self._speed_path), dtype=np.float32)
        self._speed_cache = data
        self._speed_cache_mtime = mtime
        return data

    def predict(self, step: int = 1, top_k: int = 12) -> Dict[str, Any]:
        """
        返回结构化预测结果（含 APN-IDW 扩展到全部传感器）。

        参数:
          step: 选择第几步预测（1-based）
          top_k: 返回最拥堵（速度最低）的前 K 个站点
        """
        if top_k <= 0:
            raise ValueError("top_k 必须 > 0")
        if top_k > 500:
            top_k = 500

        with self._lock:
            self._ensure_paths()
            self._load_predictor_locked()
            speed_data = self._load_speed_data_locked()

            t0 = time.time()
            raw_predictions = self._predictor.predict(speed_data)  # (pre_len, num_nodes)
            infer_ms = (time.time() - t0) * 1000.0

            if self._restorer is not None and raw_predictions.shape[1] == self._restorer.num_sensors:
                predictions = self._restorer.restore(raw_predictions)
            else:
                predictions = raw_predictions

            pre_len = int(predictions.shape[0])
            if step < 1 or step > pre_len:
                raise ValueError(f"step 必须在 1~{pre_len} 之间")

            selected_idx = step - 1
            selected = predictions[selected_idx]
            node_count = len(self._station_ids)

            t_ext0 = time.time()
            sensor_predictions = _idw_extend_sensor_predictions(
                predictions, self._station_ids, self._all_sensors, n_neighbors=6
            )
            ext_ms = (time.time() - t_ext0) * 1000.0

            tgcn_count = sum(1 for p in sensor_predictions if not p.get("is_interpolated"))
            interp_count = sum(1 for p in sensor_predictions if p.get("is_interpolated"))

            top_congested = sorted(
                sensor_predictions, key=lambda x: x["pred_speed_kmh"]
            )[: min(top_k, len(sensor_predictions))]

            all_speeds = [p["pred_speed_kmh"] for p in sensor_predictions]
            step_stats = []
            for i in range(pre_len):
                arr = predictions[i]
                step_stats.append(
                    {
                        "step": i + 1,
                        "horizon_minutes": (i + 1) * 5,
                        "avg_speed_kmh": round(float(np.mean(arr)), 3),
                        "min_speed_kmh": round(float(np.min(arr)), 3),
                        "max_speed_kmh": round(float(np.max(arr)), 3),
                    }
                )

            low_speed_threshold = 50.0
            low_speed_count = sum(1 for s in all_speeds if s < low_speed_threshold)
            total_count = max(len(all_speeds), 1)

            return {
                "model": "TGCN+IDW",
                "model_profile": self._model_profile,
                "num_nodes": node_count,
                "total_sensors": len(sensor_predictions),
                "tgcn_direct_count": tgcn_count,
                "interpolated_count": interp_count,
                "selected_step": step,
                "selected_horizon_minutes": step * 5,
                "summary": {
                    "avg_speed_kmh": round(float(np.mean(all_speeds)), 3),
                    "min_speed_kmh": round(float(np.min(all_speeds)), 3),
                    "max_speed_kmh": round(float(np.max(all_speeds)), 3),
                    "p10_speed_kmh": round(float(np.percentile(all_speeds, 10)), 3),
                    "low_speed_threshold_kmh": low_speed_threshold,
                    "low_speed_count": low_speed_count,
                    "low_speed_ratio": round(low_speed_count / total_count, 4),
                },
                "step_stats": step_stats,
                "top_congested": top_congested,
                "sensor_predictions": sensor_predictions,
                "inference_ms": round(infer_ms, 2),
                "interpolation_ms": round(ext_ms, 2),
                "generated_at": datetime.utcnow().isoformat() + "Z",
                "data_source": {
                    "model_path": self._project_rel(self._model_path),
                    "speed_path": self._project_rel(self._speed_path),
                    "station_list_path": self._project_rel(self._station_list_path),
                    "interpolation_method": "IDW-6-nearest",
                },
            }

    def predict_all_steps(self) -> Tuple[np.ndarray, List[int], Dict[int, Dict[str, Any]]]:
        """
        返回方差恢复后的全部预测步、站点 ID 列表和站点元数据。

        Returns:
            (predictions, station_ids, sensor_coords)
            predictions: shape=(pre_len, num_nodes), 单位 km/h
            station_ids: 长度 num_nodes 的站点 ID 列表
            sensor_coords: {sensor_id: {latitude, longitude, ...}}
        """
        with self._lock:
            self._ensure_paths()
            self._load_predictor_locked()
            speed_data = self._load_speed_data_locked()

            raw_predictions = self._predictor.predict(speed_data)

            if self._restorer is not None and raw_predictions.shape[1] == self._restorer.num_sensors:
                predictions = self._restorer.restore(raw_predictions)
            else:
                predictions = raw_predictions

            return predictions, list(self._station_ids), dict(self._sensor_by_id)

    def predict_all_sensors_all_steps(self) -> Tuple[np.ndarray, List[int]]:
        """
        返回全部传感器、全部预测步的扩展结果。

        Returns:
            (extended_predictions, all_sensor_ids)
            extended_predictions: shape=(pre_len, num_all_sensors)
            all_sensor_ids: 全部传感器 ID 列表
        """
        with self._lock:
            self._ensure_paths()
            self._load_predictor_locked()
            speed_data = self._load_speed_data_locked()

            raw = self._predictor.predict(speed_data)
            if self._restorer is not None and raw.shape[1] == self._restorer.num_sensors:
                base_preds = self._restorer.restore(raw)
            else:
                base_preds = raw

            all_sensor_ids = [s["id"] for s in self._all_sensors]
            base_id_set = set(self._station_ids)
            base_idx_map = {sid: i for i, sid in enumerate(self._station_ids)}

            base_coords = np.array(
                [[s["latitude"], s["longitude"]] for s in self._all_sensors if s["id"] in base_id_set],
                dtype=np.float64,
            )

            pre_len = base_preds.shape[0]
            num_all = len(self._all_sensors)
            extended = np.empty((pre_len, num_all), dtype=np.float32)

            col_map = {}
            ext_col = 0
            for i, sensor in enumerate(self._all_sensors):
                sid = sensor["id"]
                if sid in base_idx_map:
                    extended[:, i] = base_preds[:, base_idx_map[sid]]
                else:
                    col_map[i] = ext_col
                    ext_col += 1

            if col_map:
                ext_indices = list(col_map.keys())
                ext_lats = np.array([self._all_sensors[i]["latitude"] for i in ext_indices])
                ext_lons = np.array([self._all_sensors[i]["longitude"] for i in ext_indices])

                for ei, si in enumerate(ext_indices):
                    dists = np.sqrt(
                        (base_coords[:, 0] - ext_lats[ei]) ** 2
                        + (base_coords[:, 1] - ext_lons[ei]) ** 2
                    )
                    k = min(6, len(dists))
                    nearest = np.argpartition(dists, k)[:k]
                    nd = dists[nearest]
                    mask = nd < 1e-8
                    if mask.any():
                        col_in_base = base_idx_map[
                            [s["id"] for s in self._all_sensors if s["id"] in base_id_set][nearest[mask][0]]
                        ]
                        extended[:, si] = base_preds[:, col_in_base]
                    else:
                        w = 1.0 / (nd + 1e-9)
                        w /= w.sum()
                        cols = [
                            base_idx_map[[s["id"] for s in self._all_sensors if s["id"] in base_id_set][j]]
                            for j in nearest
                        ]
                        for t in range(pre_len):
                            extended[t, si] = float(np.dot(w, base_preds[t, cols].astype(np.float64)))

            return extended, all_sensor_ids
