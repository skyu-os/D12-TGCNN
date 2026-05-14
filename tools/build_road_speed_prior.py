"""
道路速度先验提取 — 从 PeMS 历史数据中学习每种道路类型的典型速度分布

参考: Tang et al. (2025) 用 OSM 特征推断未覆盖路段速度等级
      Acharya et al. (2024) 用 XGBoost + 道路属性预测拥堵速度

输入：
  PeMS 5min 原始数据 (data/d12_data/data/*.txt.gz) — 2个月
  PeMS 传感器元数据 (d12_text_meta_2023_12_05.txt)
  OSM 边-传感器映射 (data/processed/edge_sensor_map.pkl)

输出：
  data/processed/road_speed_prior.pkl — 每种道路类型的速度统计
    { "motorway":  {"mean": 95, "std": 12, "p10": 78, "p50": 98, "p90": 108}, ... }
"""
import os, sys, gzip, pickle, time
from collections import defaultdict
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def parse_meta(meta_path):
    """解析 PeMS 元数据：sensor_id → {fwy, dir, type, lat, lon}"""
    sensors = {}
    with open(meta_path) as f:
        header = f.readline().strip().split("\t")
        for line in f:
            if not line.strip():
                continue
            parts = line.strip().split("\t")
            if len(parts) < 14:
                continue
            sid = int(parts[0])
            sensors[sid] = {
                "fwy": parts[1],
                "dir": parts[2],
                "type": parts[11],  # ML/OR/FR/HV
                "lat": float(parts[8]) if parts[8] else None,
                "lon": float(parts[9]) if parts[9] else None,
            }
    return sensors


def load_sensor_road_type(sensor_id, meta, edge_sensor_map):
    """查找传感器的对应路段类型（取该传感器覆盖最多的路段类型）"""
    road_types = defaultdict(int)
    for (u, v, key), nearest_list in edge_sensor_map.items():
        for sid, dist in nearest_list:
            if sid == sensor_id and dist <= 0.5:
                # 需要读取 OSM 边属性，但这里我们用传感器本身的 fwy 编号
                # 作为代理（PeMS 传感器都在高速上）
                break
    return None  # 直接返回 None，稍后按 freeway 聚合


def main():
    print("=" * 60)
    print("  道路速度先验提取")
    print("=" * 60)

    data_dir = "TGCN/data/d12_data/data"
    meta_path = os.path.join(data_dir, "d12_text_meta_2023_12_05.txt")

    # 1. 解析元数据
    print("\n[1/4] 解析传感器元数据...")
    meta = parse_meta(meta_path)
    print(f"  传感器: {len(meta)}")

    # 2. 读取 2 个月 5min 数据，按传感器类型聚合速度统计
    print("\n[2/4] 读取历史速度数据...")
    data_files = sorted([
        f for f in os.listdir(data_dir)
        if f.startswith("d12_text_station_5min_") and f.endswith(".txt.gz")
    ])
    print(f"  文件数: {len(data_files)}")

    # 速度聚合: sensor_type → [all speeds]
    type_speeds = defaultdict(list)
    fwy_speeds = defaultdict(list)  # per-freeway
    hour_speeds = defaultdict(lambda: defaultdict(list))  # type → hour → speeds
    total_processed = 0

    for fname in data_files:
        fpath = os.path.join(data_dir, fname)
        try:
            with gzip.open(fpath, "rt", encoding="utf-8", errors="replace") as f:
                for line in f:
                    parts = line.strip().split(",")
                    if len(parts) < 10:
                        continue
                    try:
                        sensor_id = int(parts[1])
                        # 从时间戳提取小时
                        timestamp = parts[0]
                        hour = int(timestamp.split()[1].split(":")[0])
                    except (ValueError, IndexError):
                        continue

                    if sensor_id not in meta:
                        continue

                    # PeMS 格式: ts, sid, district, fwy, dir, type,
                    #   每车道: [samples, pct_obs, flow, occ, speed] × N lanes
                    lane_data = parts[6:]
                    speeds = []
                    weights = []
                    for i in range(0, len(lane_data) - 4, 5):
                        try:
                            samples = float(lane_data[i]) if lane_data[i] else 0
                            speed = float(lane_data[i+4]) if lane_data[i+4] else 0
                        except (ValueError, IndexError):
                            continue
                        if samples > 0 and speed > 0:
                            speeds.append(speed)
                            weights.append(samples)

                    if not speeds:
                        continue

                    avg_speed = np.average(speeds, weights=weights) if weights else np.mean(speeds)

                    stype = meta[sensor_id]["type"]
                    fwy = meta[sensor_id]["fwy"]
                    type_speeds[stype].append(avg_speed)
                    fwy_speeds[f"Fwy{fwy}"].append(avg_speed)
                    hour_speeds[stype][hour].append(avg_speed)
                    total_processed += 1
        except Exception as e:
            print(f"  [WARN] {fname}: {e}")

    print(f"  总速度记录: {total_processed:,}")

    # 3. 计算统计量
    print("\n[3/4] 计算速度先验...")
    prior = {}
    for stype, speeds in sorted(type_speeds.items()):
        arr = np.array(speeds)
        prior[stype] = {
            "count": len(arr),
            "mean": round(float(np.mean(arr)), 1),
            "std": round(float(np.std(arr)), 1),
            "p5": round(float(np.percentile(arr, 5)), 1),
            "p25": round(float(np.percentile(arr, 25)), 1),
            "p50": round(float(np.percentile(arr, 50)), 1),
            "p75": round(float(np.percentile(arr, 75)), 1),
            "p95": round(float(np.percentile(arr, 95)), 1),
        }

    # 按高速
    fwy_prior = {}
    for fwy, speeds in sorted(fwy_speeds.items()):
        arr = np.array(speeds)
        fwy_prior[fwy] = {
            "count": len(arr),
            "mean": round(float(np.mean(arr)), 1),
            "std": round(float(np.std(arr)), 1),
        }

    # 按小时+类型
    hour_prior = {}
    for stype, hours in hour_speeds.items():
        hour_prior[stype] = {}
        for h, speeds in sorted(hours.items()):
            arr = np.array(speeds)
            hour_prior[stype][h] = {
                "mean": round(float(np.mean(arr)), 1),
                "count": len(arr),
            }

    # 4. 展示 & 保存
    print("\n  传感器类型速度分布:")
    print(f"  {'Type':<8} {'Count':>10} {'Mean':>8} {'Std':>8} {'P5':>8} {'P50':>8} {'P95':>8}")
    for stype, s in prior.items():
        print(f"  {stype:<8} {s['count']:>10,} {s['mean']:>8.1f} {s['std']:>8.1f} {s['p5']:>8.1f} {s['p50']:>8.1f} {s['p95']:>8.1f}")

    print(f"\n  按高速:")
    for fwy, s in fwy_prior.items():
        print(f"  {fwy:<10} mean={s['mean']:.1f} std={s['std']:.1f} (n={s['count']:,})")

    # OSM 道路类型 → PeMS 传感器类型 映射
    # PeMS 传感器在高速上 → 对应 OSM motorway/trunk/primary
    # 对于无传感器的 residential/secondary 等，用低速道路的默认值
    road_type_mapping = {
        "motorway": "ML",      # 主线传感器 → motorway
        "motorway_link": "ML",
        "trunk": "ML",
        "trunk_link": "ML",
        "primary": "ML",       # 主要道路也用高速数据（保守估计会偏高，但合理）
        "primary_link": "ML",
        "secondary": "OR",     # 次要道路用匝道数据（速度较低）
        "secondary_link": "OR",
        "tertiary": "OR",
        "tertiary_link": "OR",
        "residential": "FR",   # 居民区用最低速
        "living_street": "FR",
        "service": "FR",
        "unclassified": "OR",
    }

    # 为每种 OSM 道路类型生成速度先验
    osm_prior = {}
    for osm_type, pems_type in road_type_mapping.items():
        if pems_type in prior:
            osm_prior[osm_type] = prior[pems_type]

    os.makedirs("data/processed", exist_ok=True)
    with open("data/processed/road_speed_prior.pkl", "wb") as f:
        pickle.dump({
            "type_prior": prior,
            "fwy_prior": fwy_prior,
            "hour_prior": hour_prior,
            "osm_mapping": road_type_mapping,
            "osm_prior": osm_prior,
        }, f)
    print(f"\n  ✅ 保存: data/processed/road_speed_prior.pkl")


if __name__ == "__main__":
    main()
