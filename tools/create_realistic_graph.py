"""
创建更大规模的测试路网 - 支持真实路径规划
模拟Orange County区域的路网结构
"""

import networkx as nx
import pickle
import os
import math

def generate_grid_graph(center_lat, center_lon, size=10, spacing=0.01):
    """
    生成网格状的路网图
    
    Args:
        center_lat: 中心纬度
        center_lon: 中心经度
        size: 网格大小 (size x size)
        spacing: 节点间距(度)
    """
    nodes = {}
    node_id = 1
    
    # 生成网格节点
    for i in range(size):
        for j in range(size):
            lat = center_lat + (i - size/2) * spacing
            lon = center_lon + (j - size/2) * spacing
            
            nodes[(i, j)] = {
                'id': node_id,
                'lat': lat,
                'lon': lon
            }
            node_id += 1
    
    # 创建边
    edges = []
    for i in range(size):
        for j in range(size):
            current_node = nodes[(i, j)]['id']
            
            # 水平连接
            if j < size - 1:
                next_node = nodes[(i, j+1)]['id']
                distance = calculate_distance(
                    nodes[(i, j)]['lat'], nodes[(i, j)]['lon'],
                    nodes[(i, j+1)]['lat'], nodes[(i, j+1)]['lon']
                )
                edges.append((current_node, next_node, distance))
            
            # 垂直连接
            if i < size - 1:
                next_node = nodes[(i+1, j)]['id']
                distance = calculate_distance(
                    nodes[(i, j)]['lat'], nodes[(i, j)]['lon'],
                    nodes[(i+1, j)]['lat'], nodes[(i+1, j)]['lon']
                )
                edges.append((current_node, next_node, distance))
            
            # 对角线连接(增加连通性)
            if i < size - 1 and j < size - 1:
                next_node = nodes[(i+1, j+1)]['id']
                distance = calculate_distance(
                    nodes[(i, j)]['lat'], nodes[(i, j)]['lon'],
                    nodes[(i+1, j+1)]['lat'], nodes[(i+1, j+1)]['lon']
                )
                edges.append((current_node, next_node, distance * 1.4))  # 对角线更长
    
    return nodes, edges

def calculate_distance(lat1, lon1, lat2, lon2):
    """计算两点间距离(米)"""
    R = 6371000  # 地球半径(米)
    lat1_rad = math.radians(lat1)
    lat2_rad = math.radians(lat2)
    delta_lat = math.radians(lat2 - lat1)
    delta_lon = math.radians(lon2 - lon1)
    
    a = (math.sin(delta_lat/2)**2 + 
         math.cos(lat1_rad) * math.cos(lat2_rad) * 
         math.sin(delta_lon/2)**2)
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))
    
    return R * c

def create_realistic_road_network():
    """创建真实的路网图"""
    
    print("=" * 60)
    print("  生成大规模测试路网")
    print("=" * 60)
    
    # Orange County 中心坐标
    CENTER_LAT = 33.7175  # Santa Ana
    CENTER_LON = -117.8311
    
    # 生成15x15的网格
    print("\n[INFO] 生成15x15网格路网...")
    nodes, edges = generate_grid_graph(CENTER_LAT, CENTER_LON, size=15, spacing=0.008)
    
    print(f"[INFO] 节点数: {len(nodes)}")
    print(f"[INFO] 边数: {len(edges) * 2} (双向)")
    
    # 创建NetworkX图
    G = nx.MultiDiGraph()
    
    # 添加节点
    for pos, node_data in nodes.items():
        G.add_node(node_data['id'], x=node_data['lon'], y=node_data['lat'])
    
    # 添加边(双向)
    speed_kmh = 50  # 默认速度 50 km/h
    for u, v, distance in edges:
        # 正向边
        G.add_edge(u, v, 
                   length=distance,
                   maxspeed=speed_kmh)
        # 反向边
        G.add_edge(v, u,
                   length=distance,
                   maxspeed=speed_kmh)
    
    # 添加一些主要道路(更快的速度)
    print("[INFO] 添加主要道路...")
    main_roads = [
        # 横向主干道
        (nodes[(7, 0)]['id'], nodes[(7, 14)]['id'], 80),
        (nodes[(8, 0)]['id'], nodes[(8, 14)]['id'], 80),
        # 纵向主干道
        (nodes[(0, 7)]['id'], nodes[(14, 7)]['id'], 80),
        (nodes[(0, 8)]['id'], nodes[(14, 8)]['id'], 80),
    ]
    
    for u, v, speed in main_roads:
        if G.has_edge(u, v):
            for key in G[u][v]:
                G[u][v][key]['maxspeed'] = speed
        if G.has_edge(v, u):
            for key in G[v][u]:
                G[v][u][key]['maxspeed'] = speed
    
    # 输出统计信息
    print("\n" + "=" * 60)
    print("  路网统计")
    print("=" * 60)
    print(f"  总节点数: {G.number_of_nodes()}")
    print(f"  总边数: {G.number_of_edges()}")
    
    # 计算总长度
    total_length = sum([d.get('length', 0) for u, v, d in G.edges(data=True)])
    print(f"  总长度: {total_length/1000:.1f} km")
    print(f"  平均边长: {total_length/G.number_of_edges():.0f} 米")
    
    # 检查连通性
    print(f"  图是否连通: {nx.is_weakly_connected(G)}")
    
    # 保存
    data_dir = os.path.join(os.path.dirname(__file__), "data", "processed")
    os.makedirs(data_dir, exist_ok=True)
    
    output_path = os.path.join(data_dir, "road_graph.pkl")
    with open(output_path, "wb") as f:
        pickle.dump(G, f)
    
    print(f"\n[OK] 路网已保存到: {output_path}")
    print("\n" + "=" * 60)
    print("  完成!")
    print("=" * 60)
    print("\n现在可以:")
    print("  1. 启动服务: python backend/app.py")
    print("  2. 访问: http://localhost:5000")
    print("  3. 在地图上选择任意两点进行路径规划")
    print("\n路网覆盖区域:")
    print(f"  中心: {CENTER_LAT}, {CENTER_LON}")
    print(f"  范围: 约 {15*0.008*111:.1f}km x {15*0.008*111:.1f}km")
    print("=" * 60)

if __name__ == "__main__":
    create_realistic_road_network()
