"""
修复路网图 - 添加crs属性和其他必要属性
"""

import pickle
import os
import networkx as nx

# 读取当前路网
graph_path = os.path.join(
    os.path.dirname(__file__), 
    "data", "processed", "road_graph.pkl"
)

print("=" * 60)
print("  修复路网图属性")
print("=" * 60)

with open(graph_path, "rb") as f:
    G = pickle.load(f)

print(f"\n[INFO] 当前路网:")
print(f"  节点数: {G.number_of_nodes()}")
print(f"  边数: {G.number_of_edges()}")

# 添加crs属性(OSMnx需要)
if not hasattr(G, 'graph'):
    G.graph = {}
if 'crs' not in G.graph:
    G.graph['crs'] = 'EPSG:4326'  # WGS84坐标系
    print("[OK] 添加crs属性")

# 添加其他必要属性
if 'name' not in G.graph:
    G.graph['name'] = 'Orange County Road Network'

# 确保所有节点都有x和y属性
for node, data in G.nodes(data=True):
    if 'x' not in data:
        data['x'] = data.get('lon', -117.8311)
    if 'y' not in data:
        data['y'] = data.get('lat', 33.7175)

# 确保所有边都有length属性
for u, v, key, data in G.edges(keys=True, data=True):
    if 'length' not in data:
        # 计算距离
        import math
        node_u = G.nodes[u]
        node_v = G.nodes[v]
        lat1, lon1 = node_u['y'], node_u['x']
        lat2, lon2 = node_v['y'], node_v['x']
        distance = math.sqrt((lat2-lat1)**2 + (lon2-lon1)**2) * 111000
        data['length'] = distance

print(f"\n[OK] 修复完成")
print(f"  crs: {G.graph.get('crs', 'N/A')}")
print(f"  name: {G.graph.get('name', 'N/A')}")

# 保存修复后的图
with open(graph_path, "wb") as f:
    pickle.dump(G, f)

print(f"\n[OK] 已保存到: {graph_path}")
print("\n" + "=" * 60)
print("  完成! 现在重启服务:")
print("  python backend/app.py")
print("=" * 60)
