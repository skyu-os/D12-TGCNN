"""
传感器-路网映射器
解决传感器数据稀疏性问题，将有限的传感器数据扩展到整个路网
"""

import osmnx as ox
import numpy as np
from typing import Dict, List, Tuple, Optional
from collections import defaultdict
from backend.graph.road_graph import RoadGraph
from backend.graph.sensor_parser import parse_sensors


class SensorRoadMapper:
    """传感器与路网的映射管理器"""
    
    def __init__(self, road_graph: RoadGraph):
        self.graph = road_graph
        self.sensors = parse_sensors()
        self.sensor_to_node = {}  # 传感器ID -> 路网节点ID
        self.node_to_sensor = {}  # 路网节点ID -> 最近的传感器ID
        self.edge_to_sensor = {}  # 边 -> 传感器
        self.regions = {}  # 区域划分
        
    def build_mapping(self):
        """构建传感器与路网的映射关系"""
        print(f"[INFO] 开始构建传感器-路网映射...")
        print(f"[INFO] 路网节点: {self.graph.G.number_of_nodes()}")
        print(f"[INFO] 传感器数量: {len(self.sensors)}")
        
        # 1. 将每个传感器映射到最近的路网节点
        self._map_sensors_to_nodes()
        
        # 2. 为每个路网节点找到最近的传感器
        self._map_nodes_to_sensors()
        
        # 3. 为路网边分配传感器
        self._map_edges_to_sensors()
        
        # 4. 评估覆盖情况
        self._evaluate_coverage()
        
        print(f"[OK] 传感器-路网映射构建完成")
        
    def _map_sensors_to_nodes(self):
        """将每个传感器映射到最近的路网节点"""
        for sensor in self.sensors:
            lat = sensor['latitude']
            lon = sensor['longitude']
            nearest_node = ox.distance.nearest_nodes(
                self.graph.G, 
                X=lon, 
                Y=lat
            )
            self.sensor_to_node[sensor['id']] = nearest_node
            
        print(f"[OK] 映射了 {len(self.sensor_to_node)} 个传感器到路网节点")
        
    def _map_nodes_to_sensors(self):
        """为每个路网节点找到最近的传感器（基于空间距离）"""
        # 提取传感器坐标
        sensor_coords = np.array([
            [s['latitude'], s['longitude']] 
            for s in self.sensors
        ])
        
        # 遍历所有路网节点（采样，避免太慢）
        all_nodes = list(self.graph.G.nodes(data=True))
        sample_rate = 0.1  # 只处理10%的节点作为示例
        
        for i, (node_id, node_data) in enumerate(all_nodes):
            if i / len(all_nodes) > sample_rate:
                break
                
            node_lat = node_data.get('y', 0)
            node_lon = node_data.get('x', 0)
            
            # 计算到所有传感器的距离
            distances = np.sqrt(
                (sensor_coords[:, 0] - node_lat)**2 + 
                (sensor_coords[:, 1] - node_lon)**2
            )
            
            # 找到最近的传感器
            nearest_idx = np.argmin(distances)
            nearest_sensor = self.sensors[nearest_idx]['id']
            
            self.node_to_sensor[node_id] = nearest_sensor
            
        print(f"[OK] 为 {len(self.node_to_sensor)} 个路网节点分配了最近传感器")
        
    def _map_edges_to_sensors(self):
        """为路网边分配传感器"""
        count = 0
        for u, v, key, data in self.graph.G.edges(data=True, keys=True):
            # 优先使用起点的传感器
            if u in self.node_to_sensor:
                self.edge_to_sensor[(u, v, key)] = self.node_to_sensor[u]
                count += 1
                
        print(f"[OK] 为 {count} 条路网边分配了传感器")
        
    def _evaluate_coverage(self):
        """评估传感器覆盖情况"""
        covered_nodes = len(self.node_to_sensor)
        total_nodes = self.graph.G.number_of_nodes()
        coverage = covered_nodes / total_nodes * 100
        
        print(f"\n=== 传感器覆盖评估 ===")
        print(f"路网总节点数: {total_nodes}")
        print(f"有传感器覆盖的节点: {covered_nodes}")
        print(f"覆盖率: {coverage:.2f}%")
        print(f"传感器数量: {len(self.sensors)}")
        
        # 按高速公路统计
        fwy_stats = defaultdict(int)
        for s in self.sensors:
            fwy_stats[s['fwy']] += 1
            
        print(f"\n按高速公路分布:")
        for fwy, count in sorted(fwy_stats.items()):
            print(f"  I-{fwy}: {count} 个传感器")
    
    def get_sensor_for_node(self, node_id: int) -> Optional[int]:
        """获取路网节点对应的传感器ID"""
        return self.node_to_sensor.get(node_id)
    
    def get_sensor_for_edge(self, u: int, v: int, key: int = 0) -> Optional[int]:
        """获取路网边对应的传感器ID"""
        return self.edge_to_sensor.get((u, v, key))
    
    def get_nearby_sensors(self, lat: float, lon: float, radius_km: float = 5, 
                          count: int = 5) -> List[Dict]:
        """获取指定位置附近的传感器"""
        nearby = []
        for sensor in self.sensors:
            dist = np.sqrt(
                (sensor['latitude'] - lat)**2 + 
                (sensor['longitude'] - lon)**2
            ) * 111  # 粗略转换为km
            
            if dist <= radius_km:
                nearby.append({**sensor, 'distance_km': dist})
        
        # 按距离排序
        nearby.sort(key=lambda x: x['distance_km'])
        return nearby[:count]
    
    def interpolate_speed_for_edge(self, u: int, v: int, key: int, 
                                  sensor_speeds: Dict[int, float]) -> float:
        """
        为没有直接传感器数据的边插值速度
        
        Args:
            u, v, key: 边标识
            sensor_speeds: 传感器ID -> 速度的字典
            
        Returns:
            插值后的速度 (km/h)
        """
        # 1. 尝试直接获取边对应的传感器
        sensor_id = self.get_sensor_for_edge(u, v, key)
        if sensor_id and sensor_id in sensor_speeds:
            return sensor_speeds[sensor_id]
        
        # 2. 使用起点的传感器
        if u in self.node_to_sensor:
            sensor_id = self.node_to_sensor[u]
            if sensor_id in sensor_speeds:
                return sensor_speeds[sensor_id]
        
        # 3. 使用终点的传感器
        if v in self.node_to_sensor:
            sensor_id = self.node_to_sensor[v]
            if sensor_id in sensor_speeds:
                return sensor_speeds[sensor_id]
        
        # 4. 使用邻居边的平均速度
        neighbor_speeds = []
        for neighbor in self.graph.G.neighbors(u):
            if neighbor == v:
                continue
            s_id = self.get_sensor_for_edge(u, neighbor, 0)
            if s_id and s_id in sensor_speeds:
                neighbor_speeds.append(sensor_speeds[s_id])
        
        if neighbor_speeds:
            return np.mean(neighbor_speeds)
        
        # 5. 使用默认速度
        return 60.0  # 默认60 km/h


class SpeedInterpolator:
    """速度插值器 - 将稀疏的传感器数据扩展到整个路网（默认使用APN自适应方法）"""

    def __init__(self, mapper: SensorRoadMapper):
        self.mapper = mapper
        # 默认使用APN风格插值器
        from backend.routing.apn_sensor_interpolator import APNStyleSensorInterpolator
        self.apn_interpolator = APNStyleSensorInterpolator(mapper)

    def create_speed_field(self, sensor_speeds: Dict[int, float],
                          method: str = 'adaptive',
                          hour: int = 12,
                          day_of_week: int = None) -> Dict[Tuple[int, int, int], float]:
        """
        创建整个路网的速度场

        Args:
            sensor_speeds: 传感器ID -> 速度的字典
            method: 插值方法
                - 'adaptive': APN自适应插值（推荐）
                - 'inverse_distance': 反距离加权
                - 'nearest': 最近邻
                - 'average': 区域平均
            hour: 当前小时 (0-23)，用于时段判断
            day_of_week: 星期几 (0-6)，用于时间模式判断

        Returns:
            边 -> 速度的字典
        """
        edge_speeds = {}

        if method == 'adaptive':
            # 优先使用APN自适应插值
            edge_speeds = self.apn_interpolator.create_speed_field(
                sensor_speeds, method='adaptive', hour=hour, day_of_week=day_of_week
            )
        else:
            # 传统方法备用
            for u, v, key in self.mapper.graph.G.edges(keys=True):
                if method == 'inverse_distance':
                    speed = self._inverse_distance_interpolate(u, v, key, sensor_speeds)
                elif method == 'nearest':
                    speed = self._nearest_interpolate(u, v, key, sensor_speeds)
                elif method == 'average':
                    speed = self._average_interpolate(u, v, key, sensor_speeds)
                else:
                    speed = self.mapper.interpolate_speed_for_edge(u, v, key, sensor_speeds)

                edge_speeds[(u, v, key)] = speed

        return edge_speeds
    
    def _inverse_distance_interpolate(self, u: int, v: int, key: int, 
                                      sensor_speeds: Dict[int, float]) -> float:
        """反距离加权插值"""
        # 获取边的中点坐标
        u_data = self.mapper.graph.G.nodes[u]
        v_data = self.mapper.graph.G.nodes[v]
        mid_lat = (u_data.get('y', 0) + v_data.get('y', 0)) / 2
        mid_lon = (u_data.get('x', 0) + v_data.get('x', 0)) / 2
        
        # 找到附近的传感器
        weights = []
        speeds = []
        
        for sensor_id, speed in sensor_speeds.items():
            sensor = next((s for s in self.mapper.sensors if s['id'] == sensor_id), None)
            if not sensor:
                continue
                
            # 计算距离
            dist = np.sqrt(
                (sensor['latitude'] - mid_lat)**2 + 
                (sensor['longitude'] - mid_lon)**2
            )
            
            if dist < 0.001:  # 避免除零
                return speed
                
            weight = 1.0 / (dist + 0.001)
            weights.append(weight)
            speeds.append(speed)
        
        if not weights:
            return 60.0
            
        # 加权平均
        weights = np.array(weights)
        weights = weights / weights.sum()
        return np.sum(np.array(speeds) * weights)
    
    def _nearest_interpolate(self, u: int, v: int, key: int, 
                            sensor_speeds: Dict[int, float]) -> float:
        """最近邻插值"""
        return self.mapper.interpolate_speed_for_edge(u, v, key, sensor_speeds)
    
    def _average_interpolate(self, u: int, v: int, key: int, 
                            sensor_speeds: Dict[int, float]) -> float:
        """区域平均插值"""
        # 获取边的所有传感器（起点和终点）
        speeds = []
        
        # 起点的传感器
        if u in self.mapper.node_to_sensor:
            s_id = self.mapper.node_to_sensor[u]
            if s_id in sensor_speeds:
                speeds.append(sensor_speeds[s_id])
        
        # 终点的传感器
        if v in self.mapper.node_to_sensor:
            s_id = self.mapper.node_to_sensor[v]
            if s_id in sensor_speeds:
                speeds.append(sensor_speeds[s_id])
        
        if speeds:
            return np.mean(speeds)
        return 60.0


if __name__ == "__main__":
    print("=== 传感器-路网映射测试 ===\n")
    
    # 1. 加载路网
    print("1. 加载路网...")
    road_graph = RoadGraph.build_from_osm()
    
    # 2. 构建映射
    print("\n2. 构建传感器-路网映射...")
    mapper = SensorRoadMapper(road_graph)
    mapper.build_mapping()
    
    # 3. 测试插值
    print("\n3. 测试速度插值...")
    interpolator = SpeedInterpolator(mapper)
    
    # 模拟传感器速度数据
    sensor_speeds = {s['id']: np.random.uniform(30, 100) for s in mapper.sensors[:100]}
    
    # 创建速度场
    edge_speeds = interpolator.create_speed_field(sensor_speeds, method='inverse_distance')
    
    print(f"生成了 {len(edge_speeds)} 条边的速度数据")
    print(f"速度范围: {min(edge_speeds.values()):.1f} - {max(edge_speeds.values()):.1f} km/h")
    print(f"平均速度: {np.mean(list(edge_speeds.values())):.1f} km/h")
    
    # 4. 查询示例
    print("\n4. 查询示例...")
    test_lat, test_lon = 33.7175, -117.8311
    nearby = mapper.get_nearby_sensors(test_lat, test_lon, radius_km=10)
    print(f"({test_lat}, {test_lon}) 附近的传感器:")
    for sensor in nearby[:3]:
        print(f"  {sensor['id']}: {sensor['name']} - {sensor['distance_km']:.2f}km")
    
    print("\n✅ 测试完成")
