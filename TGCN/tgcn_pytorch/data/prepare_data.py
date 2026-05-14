"""
PeMS D12 原始数据解析脚本

从 gz 压缩的 5 分钟站点数据中提取速度矩阵，构建邻接矩阵。

用法:
    # 默认: top200 传感器, 2周训练数据
    python data/prepare_data.py

    # 自定义
    python data/prepare_data.py --top_n 100 --days 7 --threshold 3.0

    # 用全部 top500
    python data/prepare_data.py --top_n 500 --days 30
"""
import os
import gzip
import yaml
import argparse
import numpy as np
import pandas as pd
from collections import defaultdict


RAW_DATA_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "data", "d12_data"))


def load_station_list(path):
    with open(path) as f:
        return [int(line.strip()) for line in f if line.strip()]


def load_sensor_metadata(meta_path):
    df = pd.read_csv(meta_path, sep='\t')
    df = df.dropna(subset=['Latitude', 'Longitude'])
    df = df[(df['Latitude'] != 0) & (df['Longitude'] != 0)]
    return df


def parse_one_day(gz_path, target_stations):
    """解析单天 gz 数据，返回 {station_id: [speed_per_5min]}"""
    station_speed = defaultdict(list)
    with gzip.open(gz_path, 'rt') as f:
        for line in f:
            parts = line.strip().split(',')
            try:
                sid = int(parts[1])
            except (ValueError, IndexError):
                continue
            if sid not in target_stations:
                continue
            # PeMS 格式: timestamp, station_id, district, fwy, dir, type,
            #   然后每车道: [samples, pct_obs, flow, occ, speed] × N lanes
            # 提取各车道速度，取加权平均
            lane_data = parts[6:]
            speeds = []
            weights = []
            for i in range(0, len(lane_data) - 4, 5):
                try:
                    samples = float(lane_data[i]) if lane_data[i] else 0
                    speed = float(lane_data[i + 4]) if lane_data[i + 4] else 0
                except (ValueError, IndexError):
                    continue
                if samples > 0 and speed > 0:
                    speeds.append(speed)
                    weights.append(samples)
            if speeds and weights:
                avg_speed = np.average(speeds, weights=weights)
            elif speeds:
                avg_speed = np.mean(speeds)
            else:
                avg_speed = 0.0
            station_speed[sid].append(avg_speed)
    return station_speed


def build_speed_matrix(raw_dir, station_ids, days, start_date="2026_01_01"):
    """构建 (timesteps, num_stations) 速度矩阵"""
    station_set = set(station_ids)
    all_data = {sid: [] for sid in station_ids}

    # 解析 start_date 得到起始文件序号
    from datetime import datetime, timedelta
    start = datetime.strptime(start_date, "%Y_%m_%d")

    processed = 0
    for d in range(365):
        date = start + timedelta(days=d)
        fname = f"d12_text_station_5min_{date.strftime('%Y_%m_%d')}.txt.gz"
        fpath = os.path.join(raw_dir, fname)
        if not os.path.exists(fpath):
            continue

        day_data = parse_one_day(fpath, station_set)
        for sid in station_ids:
            vals = day_data.get(sid, [])
            if len(vals) == 288:
                all_data[sid].extend(vals)
            else:
                # 数据缺失，用 0 填充
                all_data[sid].extend([0.0] * 288)

        processed += 1
        if processed >= days:
            break

    # 转成矩阵 (timesteps, stations)
    matrix = np.array([all_data[sid] for sid in station_ids], dtype=np.float32).T
    return matrix


def build_adjacency(sensor_df, station_ids, threshold_km=3.0):
    """根据传感器坐标构建邻接矩阵"""
    df = sensor_df[sensor_df['ID'].isin(station_ids)].copy()
    df = df.set_index('ID').loc[station_ids].reset_index()

    lat = df['Latitude'].values
    lon = df['Longitude'].values
    n = len(station_ids)

    R = 6371.0
    lat_rad = np.radians(lat)
    lon_rad = np.radians(lon)

    adj = np.zeros((n, n), dtype=np.float32)
    for i in range(n):
        for j in range(i + 1, n):
            dlat = lat_rad[i] - lat_rad[j]
            dlon = lon_rad[i] - lon_rad[j]
            a = np.sin(dlat/2)**2 + np.cos(lat_rad[i]) * np.cos(lat_rad[j]) * np.sin(dlon/2)**2
            dist = R * 2 * np.arctan2(np.sqrt(a), np.sqrt(1 - a))
            if dist < threshold_km:
                adj[i, j] = 1
                adj[j, i] = 1

    return adj


def fill_missing(speed_matrix):
    """线性插值填补 0 值（缺失数据）"""
    mat = speed_matrix.copy()
    for col in range(mat.shape[1]):
        series = mat[:, col]
        zero_mask = (series == 0)
        if zero_mask.all():
            series[:] = 60.0  # 全缺失用默认值
        elif zero_mask.any():
            x = np.arange(len(series))
            valid = ~zero_mask
            series[zero_mask] = np.interp(x[zero_mask], x[valid], series[valid])
        mat[:, col] = series
    return mat


def main():
    parser = argparse.ArgumentParser(description="PeMS D12 数据准备")
    parser.add_argument("--raw_dir", type=str,
                        default=os.path.join(RAW_DATA_DIR, "data"),
                        help="原始 gz 数据目录")
    parser.add_argument("--val_dir", type=str,
                        default=os.path.join(RAW_DATA_DIR, "val"),
                        help="验证集 gz 数据目录")
    parser.add_argument("--meta_path", type=str,
                        default=os.path.join(RAW_DATA_DIR, "data",
                                             "d12_text_meta_2023_12_05.txt"),
                        help="传感器元数据路径")
    parser.add_argument("--station_list", type=str,
                        default=os.path.join(RAW_DATA_DIR, "top500_stations.txt"),
                        help="站点列表文件（优先于 --all_sensors）")
    parser.add_argument("--all_sensors", action="store_true",
                        help="使用 all_stations.txt 全部传感器（覆盖 --station_list）")
    parser.add_argument("--top_n", type=int, default=0,
                        help="取前 N 个传感器 (0=全部, 推荐: 100/200/300/500)")
    parser.add_argument("--days", type=int, default=14,
                        help="训练数据天数 (推荐: 7/14/30)")
    parser.add_argument("--start_date", type=str, default="2026_01_01",
                        help="训练数据起始日期")
    parser.add_argument("--val_days", type=int, default=7,
                        help="验证数据天数")
    parser.add_argument("--threshold", type=float, default=3.0,
                        help="邻接矩阵距离阈值(km)")
    parser.add_argument("--output_dir", type=str, default="data",
                        help="输出目录")
    args = parser.parse_args()

    os.makedirs(args.output_dir, exist_ok=True)

    # 1. 加载站点列表
    print("=" * 55)
    if args.all_sensors:
        args.station_list = os.path.join(RAW_DATA_DIR, "all_stations.txt")
        print(f"[全传感器模式] 使用 {args.station_list}")
    all_stations = load_station_list(args.station_list)
    if args.top_n > 0:
        station_ids = all_stations[:args.top_n]
    else:
        station_ids = all_stations
    print(f"选取传感器: {len(station_ids)} / {len(all_stations)}")

    # 2. 加载元数据
    print("=" * 55)
    print("加载传感器元数据...")
    sensor_df = load_sensor_metadata(args.meta_path)
    print(f"元数据中传感器: {len(sensor_df)}")

    # 3. 构建邻接矩阵
    print("=" * 55)
    print(f"构建邻接矩阵 (阈值={args.threshold}km)...")
    adj = build_adjacency(sensor_df, station_ids, args.threshold)
    adj_path = os.path.join(args.output_dir, "d12_adj.csv")
    pd.DataFrame(adj).to_csv(adj_path, index=False, header=False)
    print(f"邻接矩阵: {adj.shape}, 边数={int(adj.sum())}, 平均度={adj.sum()/len(station_ids):.1f}")

    # 4. 解析训练速度数据
    print("=" * 55)
    print(f"解析训练数据: {args.days} 天, 起始 {args.start_date}...")
    train_speed = build_speed_matrix(args.raw_dir, station_ids, args.days, args.start_date)
    train_speed = fill_missing(train_speed)
    print(f"训练数据: {train_speed.shape} (时间步×传感器)")
    print(f"速度范围: {train_speed.min():.1f} ~ {train_speed.max():.1f}, 均值: {train_speed.mean():.1f}")

    # 5. 解析验证速度数据
    print("=" * 55)
    print(f"解析验证数据: {args.val_days} 天...")
    val_speed = build_speed_matrix(args.val_dir, station_ids, args.val_days, "2026_03_01")
    val_speed = fill_missing(val_speed)
    print(f"验证数据: {val_speed.shape}")

    # 6. 合并保存 (训练+验证一起存，train.py 按 split_ratio 切分)
    print("=" * 55)
    full_speed = np.vstack([train_speed, val_speed])
    speed_path = os.path.join(args.output_dir, "d12_speed.csv")
    pd.DataFrame(full_speed, columns=station_ids).to_csv(speed_path, index=False)

    # 保存站点 ID
    id_path = os.path.join(args.output_dir, "sensor_ids.csv")
    pd.DataFrame(station_ids, columns=['ID']).to_csv(id_path, index=False)

    # 保存配置
    config = {
        "top_n": args.top_n,
        "train_days": args.days,
        "val_days": args.val_days,
        "train_start": args.start_date,
        "threshold_km": args.threshold,
        "num_stations": len(station_ids),
        "train_timesteps": train_speed.shape[0],
        "val_timesteps": val_speed.shape[0],
        "total_timesteps": full_speed.shape[0],
    }
    import json
    config_path = os.path.join(args.output_dir, "data_config.json")
    with open(config_path, 'w') as f:
        json.dump(config, f, indent=2)

    print(f"\n数据准备完成!")
    print(f"  传感器数: {len(station_ids)}")
    print(f"  训练集: {train_speed.shape[0]} 步 ({args.days}天)")
    print(f"  验证集: {val_speed.shape[0]} 步 ({args.val_days}天)")
    print(f"  邻接矩阵: {adj_path}")
    print(f"  速度数据: {speed_path}")
    print(f"\n预计 GPU 训练时间 (TGCN, 100 epochs):")
    print(f"  {len(station_ids)} 节点: ~{len(station_ids)//50 * 5}~{len(station_ids)//50 * 15} 分钟")


if __name__ == "__main__":
    main()
