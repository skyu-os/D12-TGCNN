"""
检查路网数据 - 验证节点坐标和边数据
"""

import pickle
import os

graph_path = os.path.join(
    os.path.dirname(__file__), 
    "data", "processed", "road_graph.pkl"
)

print("=" * 60)
print("  检查路网数据")
print("=" * 60)

with open(graph_path, "rb") as f:
    G = pickle.load(f)

print(f"\n[INFO] 基本信息:")
print(f"  节点数: {G.number_of_nodes()}")
print(f"  边数: {G.number_of_edges()}")

# 检查节点数据
print(f"\n[INFO] 前5个节点坐标:")
count = 0
for node, data in G.nodes(data=True):
    if count < 5:
        print(f"  节点 {node}: x={data.get('x', 'N/A'):.4f}, y={data.get('y', 'N/A'):.4f}")
        count += 1

# 检查边数据
print(f"\n[INFO] 前5条边:")
count = 0
for u, v, key, data in G.edges(keys=True, data=True):
    if count < 5:
        length = data.get('length', 0)
        maxspeed = data.get('maxspeed', 0)
        print(f"  边 {u} -> {v}: length={length:.1f}m, maxspeed={maxspeed}km/h")
        count += 1

# 测试路径计算
print(f"\n[INFO] 测试路径计算:")
try:
    import networkx as nx
    
    # 随机选择两个节点
    nodes = list(G.nodes())
    if len(nodes) >= 2:
        start = nodes[0]
        end = nodes[-1]
        
        print(f"  起点: {start}")
        print(f"  终点: {end}")
        
        # 尝试找路径
        try:
            path = nx.shortest_path(G, start, end, weight='length')
            print(f"  找到路径,节点数: {len(path)}")
            
            # 计算总距离
            total_length = 0
            for i in range(len(path) - 1):
                u, v = path[i], path[i+1]
                # 获取最短的边
                min_length = float('inf')
                for key in G[u][v]:
                    length = G[u][v][key].get('length', 0)
                    if length < min_length:
                        min_length = length
                total_length += min_length
            
            print(f"  总距离: {total_length:.1f}m ({total_length/1000:.2f}km)")
            
        except nx.NetworkXNoPath:
            print(f"  错误: 两点之间没有路径!")
    
except Exception as e:
    print(f"  错误: {e}")

# 检查图属性
print(f"\n[INFO] 图属性:")
if hasattr(G, 'graph'):
    for key, value in G.graph.items():
        print(f"  {key}: {value}")

# 检查连通性
print(f"\n[INFO] 连通性检查:")
print(f"  是否弱连通: {nx.is_weakly_connected(G)}")
print(f"  是否强连通: {nx.is_strongly_connected(G)}")

# 统计边长度
lengths = [data.get('length', 0) for u, v, data in G.edges(data=True)]
if lengths:
    print(f"\n[INFO] 边长度统计:")
    print(f"  最小值: {min(lengths):.1f}m")
    print(f"  最大值: {max(lengths):.1f}m")
    print(f"  平均值: {sum(lengths)/len(lengths):.1f}m")
    print(f"  总长度: {sum(lengths)/1000:.1f}km")

print("\n" + "=" * 60)
