"""
转换PBF文件为路网图 - 使用pyosmium和OSMnx
"""

import os
import pickle
import sys

def convert_pbf_to_graph():
    """将PBF文件转换为NetworkX图"""
    
    print("=" * 60)
    print("  PBF文件转路网图工具")
    print("=" * 60)
    
    # 检查pyosmium是否安装
    try:
        import osmium
    except ImportError:
        print("\n[ERROR] 需要安装 pyosmium")
        print("请运行: pip install osmium")
        return False
    
    # 检查OSMnx是否可用
    try:
        import osmnx as ox
        import networkx as nx
    except ImportError:
        print("\n[ERROR] 缺少必要的库")
        print("请运行: pip install osmnx networkx")
        return False
    
    # PBF文件路径
    pbf_path = os.path.join(
        os.path.dirname(__file__), 
        "data", "osm", "planet_-118.576_33.424_ba6504c4.osm.pbf"
    )
    
    # 输出路径
    output_path = os.path.join(
        os.path.dirname(__file__), 
        "data", "processed", "road_graph.pkl"
    )
    
    if not os.path.exists(pbf_path):
        print(f"\n[ERROR] 找不到PBF文件: {pbf_path}")
        return False
    
    print(f"\n[INFO] PBF文件: {pbf_path}")
    print(f"[INFO] 输出路径: {output_path}")
    
    # 方法1: 使用OSMnx的graph_from_xml (如果PBF可以读取)
    print("\n[INFO] 尝试方法1: 使用OSMnx读取...")
    try:
        # OSMnx 1.9+ 支持直接读取PBF
        G = ox.graph_from_xml(pbf_path, simplify=True)
        
        # 过滤只保留机动车道
        if G.number_of_nodes() > 0:
            print(f"[OK] 加载成功: {G.number_of_nodes()} 节点, {G.number_of_edges()} 边")
            
            # 保存
            os.makedirs(os.path.dirname(output_path), exist_ok=True)
            with open(output_path, "wb") as f:
                pickle.dump(G, f)
            
            print(f"[OK] 已保存到: {output_path}")
            print("\n[SUCCESS] 路网图创建成功!")
            return True
            
    except Exception as e:
        print(f"[WARN] 方法1失败: {e}")
    
    # 方法2: 使用pyosmium解析PBF
    print("\n[INFO] 尝试方法2: 使用pyosmium解析...")
    
    try:
        import osmium
        
        class OSMHandler(osmium.SimpleHandler):
            def __init__(self):
                super(OSMHandler, self).__init__()
                self.nodes = {}
                self.edges = []
                self.node_count = 0
                self.way_count = 0
            
            def node(self, n):
                # 只保存指定区域的节点
                if -118.1 <= n.lon <= -117.4 and 33.4 <= n.lat <= 34.0:
                    self.nodes[n.id] = {
                        'x': n.lon,
                        'y': n.lat,
                        'id': n.id
                    }
                    self.node_count += 1
                    if self.node_count % 1000 == 0:
                        print(f"  已处理 {self.node_count} 个节点...")
            
            def way(self, w):
                # 过滤机动车道
                if 'highway' in w.tags:
                    highway = w.tags['highway']
                    valid_types = ['motorway', 'trunk', 'primary', 'secondary', 
                                 'tertiary', 'unclassified', 'residential', 'service']
                    
                    if highway in valid_types:
                        # 获取所有节点
                        node_ids = [n.ref for n in w.nodes]
                        
                        # 只保留所有节点都在我们区域内的道路
                        if all(nid in self.nodes for nid in node_ids):
                            for i in range(len(node_ids) - 1):
                                self.edges.append((node_ids[i], node_ids[i+1]))
                            
                            self.way_count += 1
                            if self.way_count % 100 == 0:
                                print(f"  已处理 {self.way_count} 条道路...")
        
        # 处理PBF文件
        handler = OSMHandler()
        handler.apply_file(pbf_path)
        
        print(f"\n[INFO] 解析完成:")
        print(f"  节点: {len(handler.nodes)}")
        print(f"  道路: {handler.way_count}")
        print(f"  边: {len(handler.edges)}")
        
        # 创建NetworkX图
        import networkx as nx
        G = nx.MultiDiGraph()
        
        # 添加节点
        for node_id, data in handler.nodes.items():
            G.add_node(node_id, x=data['x'], y=data['y'])
        
        # 添加边
        for u, v in handler.edges:
            # 计算距离
            import math
            node_u = handler.nodes[u]
            node_v = handler.nodes[v]
            
            # Haversine距离估算
            lat1, lon1 = node_u['y'], node_u['x']
            lat2, lon2 = node_v['y'], node_v['x']
            
            # 简单的距离估算
            distance = math.sqrt((lat2-lat1)**2 + (lon2-lon1)**2) * 111000  # 米
            
            G.add_edge(u, v, length=distance, maxspeed=50)
            G.add_edge(v, u, length=distance, maxspeed=50)  # 双向
        
        print(f"\n[OK] 图创建完成:")
        print(f"  节点数: {G.number_of_nodes()}")
        print(f"  边数: {G.number_of_edges()}")
        
        # 保存
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        with open(output_path, "wb") as f:
            pickle.dump(G, f)
        
        print(f"\n[OK] 已保存到: {output_path}")
        print("\n[SUCCESS] 路网图创建成功!")
        return True
        
    except Exception as e:
        print(f"[ERROR] 方法2失败: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    print("\n提示: 这个脚本可能需要几分钟时间处理PBF文件")
    print("请确保PBF文件路径正确\n")
    
    success = convert_pbf_to_graph()
    
    if success:
        print("\n" + "=" * 60)
        print("  下一步:")
        print("  1. 运行服务: python backend/app.py")
        print("  2. 访问: http://localhost:5000")
        print("  3. 在地图上选择起点和终点进行路径规划")
        print("=" * 60)
    else:
        print("\n" + "=" * 60)
        print("  失败: 无法创建路网图")
        print("  建议: 在有网络的环境下运行服务")
        print("        系统会自动下载OSM数据")
        print("=" * 60)
