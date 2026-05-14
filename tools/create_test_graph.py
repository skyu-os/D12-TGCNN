"""
创建最小测试路网 - 用于快速演示功能
"""

import networkx as nx
import pickle
import os

# Orange County 中心附近的测试节点
test_nodes = [
    (1, {'x': -117.8311, 'y': 33.7175}),  # Santa Ana
    (2, {'x': -117.8200, 'y': 33.7200}),
    (3, {'x': -117.8100, 'y': 33.7300}),
    (4, {'x': -117.8000, 'y': 33.7400}),
    (5, {'x': -117.8250, 'y': 33.7100}),
    (6, {'x': -117.8150, 'y': 33.7050}),
    (7, {'x': -117.8050, 'y': 33.6950}),
    (8, {'x': -117.8300, 'y': 33.7000}),
    (9, {'x': -117.8350, 'y': 33.6900}),
    (10, {'x': -117.8400, 'y': 33.6800}),
]

# 测试边 (带长度和限速)
test_edges = [
    (1, 2, {'length': 500, 'maxspeed': 50}),
    (2, 3, {'length': 600, 'maxspeed': 60}),
    (3, 4, {'length': 700, 'maxspeed': 70}),
    (1, 5, {'length': 400, 'maxspeed': 40}),
    (5, 6, {'length': 450, 'maxspeed': 45}),
    (6, 7, {'length': 500, 'maxspeed': 50}),
    (1, 8, {'length': 300, 'maxspeed': 35}),
    (8, 9, {'length': 350, 'maxspeed': 40}),
    (9, 10, {'length': 400, 'maxspeed': 45}),
    (2, 5, {'length': 250, 'maxspeed': 30}),
    (3, 6, {'length': 300, 'maxspeed': 35}),
    (4, 7, {'length': 350, 'maxspeed': 40}),
    (8, 5, {'length': 200, 'maxspeed': 25}),
    (9, 6, {'length': 250, 'maxspeed': 30}),
    (10, 7, {'length': 300, 'maxspeed': 35}),
]

# 创建有向图
G = nx.MultiDiGraph()

# 添加节点
G.add_nodes_from(test_nodes)

# 添加边 (双向)
for u, v, data in test_edges:
    # 正向边
    G.add_edge(u, v, **data)
    # 反向边
    G.add_edge(v, u, **data)

# 输出统计信息
print("=" * 50)
print("  创建测试路网")
print("=" * 50)
print(f"  节点数: {G.number_of_nodes()}")
print(f"  边数: {G.number_of_edges()}")
print(f"  区域: Orange County 中心")
print("=" * 50)

# 保存为pickle
data_dir = os.path.join(os.path.dirname(__file__), "data", "processed")
os.makedirs(data_dir, exist_ok=True)

output_path = os.path.join(data_dir, "road_graph.pkl")
with open(output_path, "wb") as f:
    pickle.dump(G, f)

print(f"\n[OK] 测试路网已保存到: {output_path}")
print("\n现在可以运行服务了:")
print("  python backend/app.py")
print("\n访问 http://localhost:5000 使用系统!")
