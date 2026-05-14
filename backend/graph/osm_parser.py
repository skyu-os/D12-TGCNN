"""
OSMNX 下载 PeMS D12 区域路网数据
PeMS D12 = Orange County, California
坐标范围: lat 33.4-33.95, lon -118.1~-117.6
"""

import osmnx as ox
import networkx as nx
import pickle
import os

# PeMS D12 (Orange County) 中心点和范围
CENTER = (33.7175, -117.8311)  # Santa Ana, Orange County
DISTANCE = 25000  # 25km 半径覆盖整个 D12 区域

OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "..", "data")
OSM_RAW_PATH = os.path.join(OUTPUT_DIR, "osm", "pems_d12_graph.graphml")
PROCESSED_PATH = os.path.join(OUTPUT_DIR, "processed", "road_graph.pkl")


def download_road_network():
    """下载 PeMS D12 区域路网 (drive 模式 - 仅机动车道)"""
    print(f"正在下载 OSM 路网数据 (中心: {CENTER}, 半径: {DISTANCE}m)...")
    G = ox.graph_from_point(CENTER, dist=DISTANCE, network_type="drive", simplify=True)
    print(f"下载完成: {G.number_of_nodes()} 个节点, {G.number_of_edges()} 条边")
    return G


def save_graph(G, path):
    """保存图数据"""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    if path.endswith(".graphml"):
        ox.save_graphml(G, path)
        print(f"GraphML 已保存: {path}")
    elif path.endswith(".pkl"):
        with open(path, "wb") as f:
            pickle.dump(G, f)
        print(f"Pickle 已保存: {path}")


def load_graph(path):
    """加载图数据"""
    if path.endswith(".graphml"):
        return ox.load_graphml(path)
    elif path.endswith(".pkl"):
        with open(path, "rb") as f:
            return pickle.load(f)


def print_graph_stats(G):
    """打印图统计信息"""
    print(f"\n=== 路网统计 ===")
    print(f"节点数: {G.number_of_nodes()}")
    print(f"边数: {G.number_of_edges()}")

    # 检查边属性
    if G.number_of_edges() > 0:
        u, v, data = next(iter(G.edges(data=True)))
        print(f"边属性: {list(data.keys())}")
        if "length" in data:
            lengths = [d["length"] for _, _, d in G.edges(data=True) if "length" in d]
            print(f"平均边长: {sum(lengths) / len(lengths):.1f}m")


if __name__ == "__main__":
    # 检查是否已有缓存
    if os.path.exists(PROCESSED_PATH):
        print(f"发现缓存: {PROCESSED_PATH}, 加载中...")
        G = load_graph(PROCESSED_PATH)
        print_graph_stats(G)
    else:
        G = download_road_network()
        print_graph_stats(G)
        save_graph(G, OSM_RAW_PATH)
        save_graph(G, PROCESSED_PATH)

    print("\n路网构建完成!")
