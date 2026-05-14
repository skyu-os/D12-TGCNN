"""
ALT 性能基准测试 — 测量不猜测
系统性地测量每个阶段的耗时，定位真正的瓶颈。
"""
import os
import sys
import time
import cProfile
import pstats

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from backend.graph.road_graph import RoadGraph
from backend.routing.alt import ALTRouter


def measure_precomputation(road_graph):
    """测量 landmark 预计算耗时（仅首次）"""
    cache_path = "data/processed/alt_landmarks.pkl"
    if os.path.exists(cache_path):
        os.remove(cache_path)
        print("已删除旧缓存，重新预计算")

    t0 = time.time()
    alt = ALTRouter(road_graph, num_landmarks=16)
    elapsed = time.time() - t0
    print(f"\n[PREP] 预计算 + 加载总耗时: {elapsed:.1f}s")
    return alt


def measure_find_path(alt, name, start_node, end_node):
    """测量 find_path 耗时"""
    t0 = time.time()
    result = alt.find_path(start_node, end_node)
    elapsed_ms = (time.time() - t0) * 1000

    if result:
        print(f"\n[PATH: {name}]")
        print(f"  距离: {result['distance_km']} km")
        print(f"  时间: {result['time_min']} min")
        print(f"  节点数: {len(result['path'])}")
        print(f"  耗时: {elapsed_ms:.1f} ms")
    else:
        print(f"\n[PATH: {name}] 无路径! ({elapsed_ms:.1f} ms)")

    return elapsed_ms


def measure_heuristic_overhead(alt, start_node, end_node):
    """测量 _heuristic 调用的纯开销"""
    t0 = time.time()
    for _ in range(10000):
        alt._heuristic(start_node, end_node)
    elapsed_ms = (time.time() - t0) * 1000
    per_call_us = elapsed_ms / 10  # microseconds
    print(f"\n[HEURISTIC] 10000 次调用: {elapsed_ms:.1f} ms ({per_call_us:.1f} us/call)")
    return per_call_us


def measure_edge_weight_overhead(road_graph, alt, start_node):
    """测量 get_edge_weight 调用的开销"""
    neighbors = list(alt.G.neighbors(start_node))
    if not neighbors:
        print("\n[EDGE] 无邻居，跳过")
        return 0

    neighbor = neighbors[0]
    t0 = time.time()
    for _ in range(10000):
        for key in alt.G[start_node][neighbor]:
            road_graph.get_edge_weight(start_node, neighbor, key, "time")
    elapsed_ms = (time.time() - t0) * 1000
    per_call_us = elapsed_ms / (10000 * len(alt.G[start_node][neighbor]))
    print(f"\n[EDGE] 10000 次调用: {elapsed_ms:.1f} ms ({per_call_us:.1f} us/call)")
    return per_call_us


def profile_find_path(alt, start_node, end_node):
    """用 cProfile 找出 find_path 中的热点"""
    print("\n--- cProfile: find_path ---")
    profiler = cProfile.Profile()
    profiler.enable()
    alt.find_path(start_node, end_node)
    profiler.disable()

    stats = pstats.Stats(profiler).sort_stats("cumtime")
    stats.print_stats(20)


def main():
    print("=" * 60)
    print("  ALT 性能基准测试")
    print("=" * 60)

    # 1. 加载路网
    print("\n>>> 加载路网...")
    t0 = time.time()
    rg = RoadGraph.build_from_osm()
    print(f"  加载耗时: {time.time() - t0:.1f}s")
    print(f"  节点: {rg.G.number_of_nodes():,}")
    print(f"  边: {rg.G.number_of_edges():,}")

    # 2. 预计算（或从缓存加载）
    print("\n>>> 加载 ALT...")
    t0 = time.time()
    cache_path = "data/processed/alt_landmarks.pkl"
    if os.path.exists(cache_path):
        alt = ALTRouter(rg, num_landmarks=16)
        print(f"  从缓存加载耗时: {time.time() - t0:.1f}s")
        print(f"  地标: {len(alt.landmarks)}")
    else:
        alt = measure_precomputation(rg)

    # 3. 选取多组 OD 对进行测试
    print("\n>>> 选取测试 OD 对...")
    nodes = list(rg.G.nodes)
    import random
    random.seed(42)
    test_nodes = random.sample(nodes, min(20, len(nodes)))
    od_pairs = [
        ("E-W 远距离", test_nodes[0], test_nodes[1]),
        ("N-S 远距离", test_nodes[2], test_nodes[3]),
        ("NW-SE 对角线", test_nodes[4], test_nodes[5]),
        ("中距离 (中间节点)", test_nodes[6], test_nodes[7]),
    ]

    # 4. 测量微基准
    print("\n\n>>> 微基准测量")
    measure_heuristic_overhead(alt, test_nodes[0], test_nodes[1])
    measure_edge_weight_overhead(rg, alt, test_nodes[0])

    # 5. 测量路径规划
    print("\n\n>>> 路径规划性能")
    total_ms = 0
    for name, s, e in od_pairs:
        ms = measure_find_path(alt, name, s, e)
        total_ms += ms

    print(f"\n  平均耗时: {total_ms / len(od_pairs):.1f} ms")

    # 6. 性能剖面
    print("\n\n>>> 详细剖面 (第一个 OD 对)")
    profile_find_path(alt, od_pairs[0][1], od_pairs[0][2])


if __name__ == "__main__":
    main()
