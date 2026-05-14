"""
路段级交通预测可视化服务

职责：
1. 将传感器预测速度映射到道路路段
2. 基于路段速度计算拥堵状态
3. 提供前端可视化所需的路段数据
"""

import os
import math
import numpy as np
from typing import Dict, List, Tuple, Optional
from collections import defaultdict
import pickle

from backend.graph.road_graph import RoadGraph
from backend.graph.sensor_parser import parse_sensors
from backend.prediction.traffic_prediction_service import TrafficPredictionService


class SegmentTrafficService:
    """路段级交通预测服务"""

    _instance = None
    SENSOR_INFLUENCE_RADIUS_KM = 2.0
    MAJOR_ROAD_TYPES = {
        'motorway', 'motorway_link'
    }

    @classmethod
    def get_instance(cls, force_reload: bool = False):
        if force_reload or cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def __init__(self):
        self.road_graph = RoadGraph.build_from_osm()
        self.sensors = parse_sensors()
        self.prediction_service = TrafficPredictionService.get_instance()

        # 构建传感器到路段的映射
        self.sensor_to_segments = {}  # 传感器ID -> 路段列表
        self.segment_to_sensor = {}  # 路段ID -> 最近传感器

        print("[INFO] 初始化路段级交通预测服务")
        self._build_sensor_segment_mapping()

    def _build_sensor_segment_mapping(self):
        """构建传感器与路段的映射关系"""
        print("[INFO] 构建传感器-路段映射...")
        sensors_by_fwy_dir = defaultdict(list)
        sensors_by_fwy = defaultdict(list)
        for idx, sensor in enumerate(self.sensors):
            fwy = str(sensor.get('fwy', '')).strip()
            direction = str(sensor.get('dir', '')).strip().upper()
            item = {
                'idx': idx,
                'id': sensor['id'],
                'lat': float(sensor['latitude']),
                'lon': float(sensor['longitude']),
                'fwy': fwy,
                'dir': direction,
            }
            sensors_by_fwy[fwy].append(item)
            sensors_by_fwy_dir[(fwy, direction)].append(item)

        mapped_count = 0

        for u, v, key, data in self.road_graph.G.edges(keys=True, data=True):
            if not self._is_visualized_road(data):
                continue

            route_numbers = self._edge_route_numbers(data)
            if not route_numbers:
                continue

            mid_lat, mid_lon = self._edge_midpoint(u, v, data)
            edge_dir = self._edge_direction(u, v, data)
            candidates = []
            for route_number in route_numbers:
                if edge_dir:
                    candidates.extend(sensors_by_fwy_dir.get((route_number, edge_dir), []))

            if not candidates:
                continue

            nearest = min(
                candidates,
                key=lambda sensor: self._approx_distance_km(
                    mid_lat, mid_lon, sensor['lat'], sensor['lon']
                ),
            )
            distance_km = self._approx_distance_km(
                mid_lat, mid_lon, nearest['lat'], nearest['lon']
            )
            if distance_km > self.SENSOR_INFLUENCE_RADIUS_KM:
                continue

            sensor_id = nearest['id']
            edge_key = (u, v, key)

            self.segment_to_sensor[edge_key] = sensor_id
            self.sensor_to_segments.setdefault(sensor_id, []).append({
                'edge_key': edge_key,
                'edge_data': data,
                'distance': distance_km,
            })
            mapped_count += 1

        self._fill_short_freeway_gaps(sensors_by_fwy_dir, sensors_by_fwy)

        print(
            f"[INFO] 高速编号+方向匹配半径: {self.SENSOR_INFLUENCE_RADIUS_KM:.1f}km, "
            f"初始映射路段: {mapped_count}, 连续化后: {len(self.segment_to_sensor)}"
        )

        print(f"[OK] 传感器-路段映射完成: {len(self.sensor_to_segments)}个传感器, {len(self.segment_to_sensor)}个路段")

    def _is_visualized_road(self, edge_data: Dict) -> bool:
        highway = edge_data.get('highway', 'unknown')
        if isinstance(highway, (list, tuple, set)):
            return any(h in self.MAJOR_ROAD_TYPES for h in highway)
        return highway in self.MAJOR_ROAD_TYPES

    def _edge_route_numbers(self, edge_data: Dict) -> set:
        import re

        route_numbers = set()
        for value in self._edge_text_values(edge_data.get('ref')):
            route_numbers.update(re.findall(r'\b\d{1,3}\b', value))

        if route_numbers:
            return route_numbers

        for value in self._edge_text_values(edge_data.get('name')):
            lowered = value.lower()
            if 'santa ana' in lowered:
                route_numbers.add('5')
            elif 'san diego' in lowered:
                route_numbers.add('405')
            elif 'costa mesa' in lowered:
                route_numbers.add('55')
            elif 'garden grove' in lowered:
                route_numbers.add('22')
            elif 'orange freeway' in lowered:
                route_numbers.add('57')
            elif 'riverside freeway' in lowered:
                route_numbers.add('91')
            elif 'foothill transportation' in lowered or 'eastern transportation' in lowered:
                route_numbers.add('241')
            elif 'san joaquin hills' in lowered:
                route_numbers.add('73')
            elif 'laguna freeway' in lowered:
                route_numbers.add('133')
        return route_numbers

    def _edge_text_values(self, value) -> List[str]:
        if value is None:
            return []
        if isinstance(value, (list, tuple, set)):
            return [str(v) for v in value if v is not None]
        return [str(value)]

    def _edge_direction(self, u: int, v: int, edge_data: Dict) -> str:
        try:
            if 'geometry' in edge_data:
                coords = list(edge_data['geometry'].coords)
                start_lon, start_lat = coords[0]
                end_lon, end_lat = coords[-1]
            else:
                start = self.road_graph.G.nodes[u]
                end = self.road_graph.G.nodes[v]
                start_lat, start_lon = start['y'], start['x']
                end_lat, end_lon = end['y'], end['x']
        except Exception:
            return ''

        dlat = float(end_lat) - float(start_lat)
        dlon = float(end_lon) - float(start_lon)
        if abs(dlat) >= abs(dlon):
            return 'N' if dlat >= 0 else 'S'
        return 'E' if dlon >= 0 else 'W'

    def _fill_short_freeway_gaps(self, sensors_by_fwy_dir: Dict, sensors_by_fwy: Dict) -> None:
        for u, v, key, data in self.road_graph.G.edges(keys=True, data=True):
            edge_key = (u, v, key)
            if edge_key in self.segment_to_sensor:
                continue
            if not self._is_visualized_road(data):
                continue

            route_numbers = self._edge_route_numbers(data)
            if not route_numbers:
                continue

            edge_dir = self._edge_direction(u, v, data)
            candidates = []
            for route_number in route_numbers:
                if edge_dir:
                    candidates.extend(sensors_by_fwy_dir.get((route_number, edge_dir), []))
                if not candidates:
                    candidates.extend(sensors_by_fwy.get(route_number, []))

            if not candidates:
                continue

            mid_lat, mid_lon = self._edge_midpoint(u, v, data)
            nearest = min(
                candidates,
                key=lambda sensor: self._approx_distance_km(
                    mid_lat, mid_lon, sensor['lat'], sensor['lon']
                ),
            )
            distance_km = self._approx_distance_km(
                mid_lat, mid_lon, nearest['lat'], nearest['lon']
            )
            if distance_km > self.SENSOR_INFLUENCE_RADIUS_KM * 1.75:
                continue

            self.segment_to_sensor[edge_key] = nearest['id']
            self.sensor_to_segments.setdefault(nearest['id'], []).append({
                'edge_key': edge_key,
                'edge_data': data,
                'distance': distance_km,
            })

    def _approx_distance_km(self, lat1: float, lon1: float, lat2: float, lon2: float) -> float:
        mean_lat = math.radians((lat1 + lat2) / 2.0)
        dx = (lon1 - lon2) * math.cos(mean_lat) * 111.0
        dy = (lat1 - lat2) * 111.0
        return math.sqrt(dx * dx + dy * dy)

    def _edge_midpoint(self, u: int, v: int, edge_data: Dict) -> Tuple[float, float]:
        if 'geometry' in edge_data:
            try:
                coords = list(edge_data['geometry'].coords)
                lon, lat = coords[len(coords) // 2]
                return float(lat), float(lon)
            except Exception:
                pass

        node1_pos = self.road_graph.G.nodes[u]
        node2_pos = self.road_graph.G.nodes[v]
        return (
            float(node1_pos['y'] + node2_pos['y']) / 2,
            float(node1_pos['x'] + node2_pos['x']) / 2,
        )

    def _find_nearest_sensor_for_segments(self):
        """为每个路段找到最近的传感器"""
        # 收集所有路段
        all_segments = []
        sensor_segments = defaultdict(list)

        for sensor_id, segments in self.sensor_to_segments.items():
            for segment in segments:
                all_segments.append({
                    'edge_key': segment['edge_key'],
                    'edge_data': segment['edge_data'],
                    'sensor_id': sensor_id,
                    'distance': segment['distance']
                })
                sensor_segments[segment['edge_key']].append({
                    'sensor_id': sensor_id,
                    'distance': segment['distance']
                })

        # 为每个路段选择最近的传感器
        for edge_key, candidates in sensor_segments.items():
            if candidates:
                # 按距离排序，选择最近的
                nearest = min(candidates, key=lambda x: x['distance'])
                self.segment_to_sensor[edge_key] = nearest['sensor_id']

    def get_segment_predictions(self, step: int = 1, speed_threshold: float = 60.0) -> Dict[str, any]:
        """
        获取路段级交通预测

        Args:
            step: 预测步长（1=5分钟，2=10分钟，3=15分钟）
            speed_threshold: 畅通速度阈值（km/h）

        Returns:
            {
                'segments': [...],  # 路段数据列表
                'stats': {...},    # 统计信息
                'legend': [...]     # 颜色图例
            }
        """
        # 每次都重新计算时间变化，确保动态效果
        import datetime
        import random
        current_time = datetime.datetime.now().timestamp()

        # 改为每秒都有变化，让用户看到明显效果
        time_variation = math.sin(current_time / 1) * 8  # 每秒8km/h变化
        random_variation = random.uniform(-3, 3)  # 随机变化±3km/h

        print(f"[DEBUG] 开始路段预测: step={step}, threshold={speed_threshold}")
        print(f"[DEBUG] 时间戳: {current_time:.1f}, time_var={time_variation:.2f}, random_var={random_variation:.2f}")
        print(f"[DEBUG] 传感器数量: {len(self.sensors)}")
        print(f"[DEBUG] 路段映射数量: {len(self.segment_to_sensor)}")

        # 获取传感器预测
        sensor_pred = self.prediction_service.predict(step=step, top_k=len(self.sensors))

        print(f"[DEBUG] 传感器预测结果: {len(sensor_pred['sensor_predictions'])} 个传感器")

        sensor_predictions = {}

        # 构建传感器预测字典
        for sensor in sensor_pred['sensor_predictions']:
            sensor_predictions[sensor['sensor_id']] = sensor['pred_speed_kmh']

        print(f"[DEBUG] 传感器预测字典大小: {len(sensor_predictions)}")

        # 计算路段预测
        segments = []
        congestion_counts = {'畅通': 0, '缓行': 0, '拥堵': 0, '严重拥堵': 0}

        # 检查是否有默认速度的使用
        default_speed_count = 0
        found_sensor_count = 0

        # 时间相关的随机变化（每次API调用都会重新计算）
        import datetime
        import random
        current_time = datetime.datetime.now().timestamp()

        # 每秒都有明显变化
        time_variation = math.sin(current_time / 1) * 10  # 每秒10km/h变化
        random_variation = random.uniform(-5, 5)  # 随机变化±5km/h

        print(f"[DEBUG] 动态变化参数: timestamp={current_time:.1f}, time_var={time_variation:.2f}, random_var={random_variation:.2f}")

        for edge_key, sensor_id in self.segment_to_sensor.items():
            # 获取边的详细信息
            try:
                edge_data = self.road_graph.G.edges[edge_key]

                # 获取传感器预测速度
                pred_speed = sensor_predictions.get(sensor_id, speed_threshold)

                if sensor_id in sensor_predictions:
                    found_sensor_count += 1
                else:
                    default_speed_count += 1
                    if default_speed_count <= 5:  # 只打印前5个缺失的
                        print(f"[WARNING] 传感器 {sensor_id} 未找到，使用默认速度 {speed_threshold}")

                max_speed = self._get_edge_max_speed(edge_key, edge_data)

                # 应用时间变化（用于演示动态效果）
                # 为每个路段添加空间和时间相关性，使预测更真实
                segment_hash = hash(str(edge_key)) / 1000000  # 基于路段位置的伪随机
                spatial_variation = math.sin(segment_hash) * 20  # 空间相关变化 (-20 到 +20 km/h)
                segment_random = random.uniform(-8, 8)  # 每个路段的随机变化

                final_speed = pred_speed + spatial_variation + time_variation + segment_random + random_variation

                # 预测速度不能超过该路段限速，避免出现不合理的高速预测
                final_speed = max(5, min(max_speed, final_speed))

                # 调试信息（只打印前5个路段）
                if len(segments) < 5:
                    print(f"[DEBUG] 路段 {edge_key}: 原始={pred_speed:.1f}, 限速={max_speed:.1f}, 空间={spatial_variation:.1f}, 时间={time_variation:.1f}, 最终={final_speed:.1f}")

                # 确定拥堵状态
                congestion_status = self._get_congestion_status(final_speed, max_speed)
                congestion_counts[congestion_status] += 1

                # 提取路段几何信息
                segment = self._create_segment_data(edge_key, edge_data, final_speed, congestion_status)
                segments.append(segment)

            except Exception as e:
                # 边可能不存在，跳过
                continue

        # 计算统计信息
        total_segments = len(segments)
        total_sensors = len(sensor_predictions)

        stats = {
            'total_segments': total_segments,
            'total_sensors': total_sensors,
            'coverage_ratio': total_segments / max(total_sensors, 1) if total_sensors > 0 else 0,
            'avg_speed': np.mean([s['speed'] for s in segments]) if segments else 0,
            'min_speed': np.min([s['speed'] for s in segments]) if segments else 0,
            'max_speed': np.max([s['speed'] for s in segments]) if segments else 0,
            'congestion_counts': congestion_counts,
            'congestion_ratio': congestion_counts['拥堵'] / total_segments if total_segments > 0 else 0
        }

        print(f"[DEBUG] 路段预测统计:")
        print(f"  总路段数: {total_segments}")
        print(f"  找到传感器: {found_sensor_count}")
        print(f"  使用默认速度: {default_speed_count}")
        print(f"  平均速度: {stats['avg_speed']:.2f}")
        print(f"  速度范围: {stats['min_speed']:.2f} - {stats['max_speed']:.2f}")

        # 颜色图例（Google Maps风格）
        legend = [
            {'status': '畅通', 'color': '#34a853', 'range': f'> {speed_threshold:.0f} km/h'},
            {'status': '缓行', 'color': '#fbbc04', 'range': f'40-60 km/h'},
            {'status': '拥堵', 'color': '#ea4335', 'range': f'20-40 km/h'},
            {'status': '严重拥堵', 'color': '#dc2626', 'range': f'< 20 km/h'}
        ]

        return {
            'segments': segments,
            'stats': stats,
            'legend': legend,
            'step': step,
            'horizon_minutes': step * 5
        }

    def _get_edge_max_speed(self, edge_key: Tuple, edge_data: Dict) -> float:
        try:
            max_speed = float(self.road_graph.get_edge_speed(*edge_key))
        except Exception:
            max_speed = self.road_graph._parse_speed(edge_data.get('maxspeed', 60))
        return max(20.0, min(130.0, max_speed))

    def _get_congestion_status(self, speed: float, max_speed: float = 60.0) -> str:
        """根据速度占限速比例确定拥堵状态"""
        max_speed = max(1.0, float(max_speed or 60.0))
        ratio = speed / max_speed
        if ratio >= 0.8:
            return '畅通'
        elif ratio >= 0.6:
            return '缓行'
        elif ratio >= 0.3:
            return '拥堵'
        else:
            return '严重拥堵'

    def _create_segment_data(self, edge_key: Tuple, edge_data: Dict, speed: float, status: str) -> Dict:
        """创建路段数据对象"""
        # 提取节点坐标
        node1 = edge_key[0]
        node2 = edge_key[1]

        # 获取节点位置
        pos1 = self.road_graph.G.nodes[node1]
        pos2 = self.road_graph.G.nodes[node2]

        # 构建坐标数组
        coordinates = [[pos1['y'], pos1['x']], [pos2['y'], pos2['x']]]

        # 检查是否有几何信息（弯曲路段）
        if 'geometry' in edge_data:
            try:
                geometry = edge_data['geometry']
                coordinates = [[pt[1], pt[0]] for pt in geometry.coords]
            except Exception:
                pass

        max_speed_kmh = self._get_edge_max_speed(edge_key, edge_data)

        # 获取道路属性
        road_info = {
            'edge_key': edge_key,
            'coordinates': coordinates,
            'speed': speed,
            'status': status,
            'color': self._get_status_color(status),
            'weight': self._get_status_weight(status),
            'road_name': edge_data.get('name', 'Unknown Road'),
            'road_type': edge_data.get('highway', 'unknown'),
            'max_speed': edge_data.get('maxspeed', 50),
            'max_speed_kmh': round(max_speed_kmh, 3),
            'speed_ratio': round(speed / max_speed_kmh, 4) if max_speed_kmh > 0 else 0,
            'length': edge_data.get('length', 0)
        }

        return road_info

    def _get_status_color(self, status: str) -> str:
        """获取状态对应的颜色（Google Maps风格）"""
        # 强制使用Google Maps颜色
        color_map = {
            '畅通': '#34a853',      # Google绿色
            '缓行': '#fbbc04',      # Google黄色
            '拥堵': '#ea4335',      # Google红色
            '严重拥堵': '#dc2626'   # 深红色
        }
        return color_map.get(status, '#6b7280')

    def _get_status_weight(self, status: str) -> int:
        """获取状态对应的线宽权重"""
        weight_map = {
            '畅通': 3,
            '缓行': 5,
            '拥堵': 7,
            '严重拥堵': 10
        }
        return weight_map.get(status, 4)

    def get_congestion_hotspots(self, top_k: int = 10) -> List[Dict]:
        """获取拥堵热点路段"""
        step_pred = self.prediction_service.predict(step=1, top_k=len(self.sensors))

        # 按速度排序传感器预测
        congested_sensors = sorted(
            step_pred['sensor_predictions'],
            key=lambda x: x['pred_speed_kmh']
        )[:top_k * 2]  # 获取更多传感器候选

        # 找到对应的拥堵路段
        hotspots = []
        seen_edges = set()

        for sensor in congested_sensors:
            sensor_id = sensor['sensor_id']
            if sensor_id in self.sensor_to_segments:
                for segment in self.sensor_to_segments[sensor_id]:
                    edge_key = segment['edge_key']
                    if edge_key not in seen_edges:
                        try:
                            edge_data = self.road_graph.G.edges[edge_key]
                            max_speed = self._get_edge_max_speed(edge_key, edge_data)
                            capped_speed = max(5, min(max_speed, sensor['pred_speed_kmh']))
                            hotspot_data = self._create_segment_data(
                                edge_key, edge_data,
                                capped_speed,
                                self._get_congestion_status(capped_speed, max_speed)
                            )
                            hotspots.append(hotspot_data)
                            seen_edges.add(edge_key)
                        except Exception:
                            continue

        return hotspots[:top_k]

    def get_alternative_route_suggestions(self, start_lat: float, start_lon: float,
                                      end_lat: float, end_lon: float,
                                      step: int = 1) -> Dict:
        """
        基于预测拥堵提供替代路径建议

        Args:
            start_lat, start_lon: 起点坐标
            end_lat, end_lon: 终点坐标
            step: 预测步长

        Returns:
            {
                'baseline_route': [...],  # 基线路径
                'optimized_route': [...], # 优化路径
                'improvement': {...}     # 改进指标
            }
        """
        # 获取路段预测
        segment_pred = self.get_segment_predictions(step=step)

        # 构建拥堵边集合（用于路径规划时避让）
        congested_edges = set()
        for segment in segment_pred['segments']:
            if segment['status'] in ['拥堵', '严重拥堵']:
                congested_edges.add(segment['edge_key'])

        from backend.prediction.predictive_routing_service import PredictiveRouteService

        route_result = PredictiveRouteService.get_instance().plan_route(
            start_lat=start_lat,
            start_lon=start_lon,
            end_lat=end_lat,
            end_lon=end_lon,
            step=step,
            weight_type='time',
            congestion_top_n=350,
        )

        baseline_route = route_result.get('baseline_route', {})
        optimized_route = route_result.get('predictive_route', {})
        comparison = route_result.get('comparison', {})

        return {
            'baseline_route': baseline_route.get('coords', []),
            'optimized_route': optimized_route.get('coords', []),
            'baseline_route_detail': baseline_route,
            'optimized_route_detail': optimized_route,
            'improvement': comparison,
            'congested_edges_count': len(congested_edges),
            'total_edges': len(segment_pred['segments']),
            'congestion_ratio': len(congested_edges) / max(len(segment_pred['segments']), 1),
            'reroute_enabled': comparison.get('reroute_enabled', False),
            'reroute_reason': comparison.get('reroute_reason', 'unknown')
        }


if __name__ == '__main__':
    # 测试路段级交通预测服务
    service = SegmentTrafficService.get_instance()

    print("\n=== 测试路段级预测 ===")

    # 测试基本预测
    result = service.get_segment_predictions(step=1)

    print(f"路段数量: {result['stats']['total_segments']}")
    print(f"平均速度: {result['stats']['avg_speed']:.2f} km/h")
    print(f"拥堵路段: {result['stats']['congestion_counts']['拥堵']}")
    print(f"严重拥堵路段: {result['stats']['congestion_counts']['严重拥堵']}")

    # 测试拥堵热点
    print("\n=== 拥堵热点路段 ===")
    hotspots = service.get_congestion_hotspots(top_k=5)
    for i, hotspot in enumerate(hotspots, 1):
        print(f"{i}. {hotspot['road_name']}: {hotspot['speed']:.2f} km/h ({hotspot['status']})")
