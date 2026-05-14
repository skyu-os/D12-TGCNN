"""
PeMS → OSM 路段映射脚本
使用 KD-Tree 高效匹配 2588 传感器 → 777K OSM 路段

输出: data/processed/edge_sensor_map.pkl
"""
import os, sys, pickle, time
import numpy as np
from collections import defaultdict
from scipy.spatial import cKDTree

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from backend.graph.road_graph import RoadGraph
from backend.graph.sensor_parser import parse_sensors


def latlon_to_xyz(lat, lon):
    """球面坐标 → 3D 笛卡尔（用于 KD-Tree 精确距离）"""
    lat_r, lon_r = np.radians(lat), np.radians(lon)
    return np.column_stack([
        np.cos(lat_r) * np.cos(lon_r),
        np.cos(lat_r) * np.sin(lon_r),
        np.sin(lat_r),
    ])


def chord_to_km(chord):
    """弦长 → 球面距离(km)"""
    R = 6371.0
    chord = np.clip(chord, 0.0, 2.0)
    return R * 2.0 * np.arcsin(chord / 2.0)


def main():
    print("=" * 60)
    print("  PeMS → OSM 路段映射 (KD-Tree)")
    print("=" * 60)

    # 1. 路网
    print("\n[1/5] 加载路网...")
    t0 = time.time()
    road_graph = RoadGraph.build_from_osm()
    G = road_graph.G
    print(f"  节点={G.number_of_nodes():,}  边={G.number_of_edges():,}")

    # 2. 传感器
    print("\n[2/5] 加载传感器...")
    sensors = parse_sensors()
    print(f"  传感器={len(sensors)}")
    s_lat = np.array([s["latitude"] for s in sensors], dtype=np.float64)
    s_lon = np.array([s["longitude"] for s in sensors], dtype=np.float64)
    s_ids = [s["id"] for s in sensors]
    s_xyz = latlon_to_xyz(s_lat, s_lon)  # (N, 3)

    # 3. 边中点
    print("\n[3/5] 计算边中点 + KD-Tree...")
    edge_list, edge_xyz, edge_lengths = [], [], []
    for u, v, key in G.edges(keys=True):
        u_d, v_d = G.nodes[u], G.nodes[v]
        mlat = (u_d.get("y", 0) + v_d.get("y", 0)) / 2.0
        mlon = (u_d.get("x", 0) + v_d.get("x", 0)) / 2.0
        if mlat and mlon:
            lt, ln = np.radians(mlat), np.radians(mlon)
            edge_xyz.append([np.cos(lt)*np.cos(ln), np.cos(lt)*np.sin(ln), np.sin(lt)])
            edge_list.append((u, v, key))
            edge_lengths.append(road_graph.get_edge_length(u, v, key) / 1000.0)

    edge_xyz = np.array(edge_xyz, dtype=np.float64)
    edge_lengths = np.array(edge_lengths, dtype=np.float64)
    print(f"  有效边={len(edge_list):,}")

    # 用传感器坐标建 KD-Tree
    tree = cKDTree(s_xyz)

    # 4. 匹配：每条边 → 最近 3 个传感器
    print("\n[4/5] KD-Tree 最近邻查询 (k=3)...")
    k = min(3, len(sensors))
    dists_chord, idxs = tree.query(edge_xyz, k=k)  # (N_edges, k)
    if k == 1:
        dists_chord = dists_chord[:, np.newaxis]
        idxs = idxs[:, np.newaxis]

    dists_km = chord_to_km(dists_chord)
    edge_to_sensors = {}
    for i, (u, v, key) in enumerate(edge_list):
        nearest = [(int(s_ids[idxs[i, j]]), float(dists_km[i, j])) for j in range(k)]
        edge_to_sensors[(u, v, key)] = nearest

    elapsed = time.time() - t0
    print(f"  完成 — {elapsed:.1f}s")

    # 5. 覆盖率
    print("\n[5/5] 覆盖率分析...")
    thresholds = [0.1, 0.25, 0.5, 1.0, 2.0, 5.0]
    total_edges = len(edge_to_sensors)
    total_len = float(edge_lengths.sum())

    print(f"\n  路网总长: {total_len:,.0f} km  边: {total_edges:,}  传感器: {len(sensors)}")
    print(f"\n  {'阈值':<10} {'边数':<12} {'边覆盖率':<12} {'长度覆盖率':<12}")
    print(f"  {'-'*48}")

    for t in thresholds:
        cnt = 0
        len_cov = 0.0
        for i, (ekey, nearest) in enumerate(edge_to_sensors.items()):
            if nearest[0][1] <= t:
                cnt += 1
                len_cov += edge_lengths[i]
        print(f"  {t:4.1f}km    {cnt:>6,}      {cnt/total_edges*100:5.1f}%        {len_cov/total_len*100:5.1f}%")

    # 按道路类型
    print(f"\n  按道路类型 (0.5km 阈值):")
    rt_stats = defaultdict(lambda: {"total": 0, "covered": 0})
    for i, ((u, v, key), nearest) in enumerate(edge_to_sensors.items()):
        rt = G.edges[u, v, key].get("highway", "unclassified")
        if isinstance(rt, list): rt = rt[0]
        rt_stats[rt]["total"] += 1
        if nearest[0][1] <= 0.5:
            rt_stats[rt]["covered"] += 1

    for rt in sorted(rt_stats, key=lambda x: rt_stats[x]["total"], reverse=True):
        d = rt_stats[rt]
        pct = d["covered"]/d["total"]*100 if d["total"] else 0
        print(f"  {rt:20s} {pct:5.1f}% ({d['covered']}/{d['total']})")

    # 保存
    os.makedirs("data/processed", exist_ok=True)
    with open("data/processed/edge_sensor_map.pkl", "wb") as f:
        pickle.dump({
            "edge_to_sensors": edge_to_sensors,
            "sensor_ids": s_ids,
            "total_edges": total_edges,
            "total_length_km": total_len,
            "sensor_count": len(sensors),
        }, f)
    print(f"\n  ✅ 保存: data/processed/edge_sensor_map.pkl ({os.path.getsize('data/processed/edge_sensor_map.pkl')/1024/1024:.1f} MB)")


if __name__ == "__main__":
    main()
