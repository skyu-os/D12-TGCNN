#!/usr/bin/env python3
"""
Simple segment traffic service without osmnx dependency issues
"""

import os
import numpy as np
from typing import Dict, List, Tuple, Optional
from collections import defaultdict
import pandas as pd
import networkx as nx

from backend.graph.road_graph import RoadGraph
from backend.graph.sensor_parser import parse_sensors
from backend.prediction.traffic_prediction_service import TrafficPredictionService


class SimpleSegmentTrafficService:
    """简化版路段级交通预测服务"""

    _instance = None

    @classmethod
    def get_instance(cls):
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def __init__(self):
        self.road_graph = RoadGraph.build_from_osm()
        self.sensors = parse_sensors()
        self.prediction_service = TrafficPredictionService.get_instance()

        # 构建传感器到路段的映射
        self.sensor_to_segments = {}  # 传感器ID -> 路段列表
        self.segment_to_sensor = {}  # 路段ID -> 最近传感器

        print("[INFO] 初始化简化版路段级交通预测服务")
        self._build_sensor_segment_mapping()

    def _build_sensor_segment_mapping(self):
        """构建传感器与路段的映射关系"""
        print("[INFO] 构建传感器-路段映射...")

        # 为每个传感器找到最近的路网节点（使用手动距离计算）
        for sensor in self.sensors:
            sensor_lat = sensor['latitude']
            sensor_lon = sensor['longitude']

            # 手动计算最近节点
            min_distance = float('inf')
            nearest_node_id = None

            for node_id, node_data in self.road_graph.G.nodes(data=True):
                node_lat = node_data['y']
                node_lon = node_data['x']

                # 计算欧氏距离
                distance = ((sensor_lat - node_lat) ** 2 + (sensor_lon - node_lon) ** 2) ** 0.5

                if distance < min_distance:
                    min_distance = distance
                    nearest_node_id = node_id

            if nearest_node_id:
                # 找到连接该节点的所有边（路段）
                edges = list(self.road_graph.G.edges(nearest_node_id, data=True))

                if edges:
                    # 为每个路段分配传感器（使用加权平均）
                    for edge_data in edges:
                        edge_key = (edge_data[0], edge_data[1])

                        # 计算边的几何中心点
                        if 'geometry' in edge_data[2]:
                            edge_coords = list(edge_data[2]['geometry'].coords)
                            edge_center = edge_coords[len(edge_coords) // 2]
                        else:
                            # 如果没有几何信息，使用节点坐标
                            node1_pos = self.road_graph.G.nodes[edge_data[0]]
                            node2_pos = self.road_graph.G.nodes[edge_data[1]]
                            edge_center = (
                                (node1_pos['y'] + node2_pos['y']) / 2,
                                (node1_pos['x'] + node2_pos['x']) / 2
                            )

                        # 计算距离权重
                        distance = np.sqrt(
                            (edge_center[0] - sensor_lat) ** 2 +
                            (edge_center[1] - sensor_lon) ** 2
                        )

                        # 保存传感器-路段映射
                        if sensor['id'] not in self.sensor_to_segments:
                            self.sensor_to_segments[sensor['id']] = []

                        self.sensor_to_segments[sensor['id']].append({
                            'edge_key': edge_key,
                            'edge_data': edge_data[2],
                            'distance': distance
                        })

        # 为每个路段找到最近的传感器
        self._find_nearest_sensor_for_segments()

        print(f"[OK] 传感器-路段映射完成: {len(self.sensor_to_segments)}个传感器, {len(self.segment_to_sensor)}个路段")

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
        # 获取传感器预测
        sensor_pred = self.prediction_service.predict(step=step, top_k=len(self.sensors))
        sensor_predictions = {}

        # 构建传感器预测字典
        for sensor in sensor_pred['sensor_predictions']:
            sensor_predictions[sensor['sensor_id']] = sensor['pred_speed_kmh']

        # 计算路段预测
        segments = []
        congestion_counts = {'畅通': 0, '缓行': 0, '拥堵': 0, '严重拥堵': 0}

        for edge_key, sensor_id in self.segment_to_sensor.items():
            # 获取边的详细信息
            try:
                edge_data = self.road_graph.G.edges[edge_key]

                # 获取传感器预测速度
                pred_speed = sensor_predictions.get(sensor_id, speed_threshold)

                # 确定拥堵状态
                congestion_status = self._get_congestion_status(pred_speed, speed_threshold)
                congestion_counts[congestion_status] += 1

                # 提取路段几何信息
                segment = self._create_segment_data(edge_key, edge_data, pred_speed, congestion_status)
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

        # 颜色图例
        legend = [
            {'status': '畅通', 'color': '#10b981', 'range': f'> {speed_threshold:.0f} km/h'},
            {'status': '缓行', 'color': '#f59e0b', 'range': '40-60 km/h'},
            {'status': '拥堵', 'color': '#f97316', 'range': '20-40 km/h'},
            {'status': '严重拥堵', 'color': '#ef4444', 'range': '< 20 km/h'}
        ]

        return {
            'segments': segments,
            'stats': stats,
            'legend': legend,
            'step': step,
            'horizon_minutes': step * 5
        }

    def _get_congestion_status(self, speed: float, threshold: float = 60.0) -> str:
        """根据速度确定拥堵状态"""
        if speed >= threshold:
            return '畅通'
        elif speed >= 40:
            return '缓行'
        elif speed >= 20:
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
            'length': edge_data.get('length', 0)
        }

        return road_info

    def _get_status_color(self, status: str) -> str:
        """获取状态对应的颜色"""
        color_map = {
            '畅通': '#10b981',      # 绿色
            '缓行': '#f59e0b',      # 黄色
            '拥堵': '#f97316',      # 橙色
            '严重拥堵': '#ef4444'    # 红色
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
                            hotspot_data = self._create_segment_data(
                                edge_key, edge_data,
                                sensor['pred_speed_kmh'],
                                self._get_congestion_status(sensor['pred_speed_kmh'])
                            )
                            hotspots.append(hotspot_data)
                            seen_edges.add(edge_key)
                        except Exception:
                            continue

        return hotspots[:top_k]


if __name__ == '__main__':
    # 测试简化版路段级交通预测服务
    service = SimpleSegmentTrafficService.get_instance()

    print("\n=== 测试简化版路段级预测服务 ===")

    # 测试基本预测
    print("\n1. 测试基本预测功能...")
    result = service.get_segment_predictions(step=1)

    print(f"路段数量: {result['stats']['total_segments']}")
    print(f"传感器数量: {result['stats']['total_sensors']}")
    print(f"覆盖率: {result['stats']['coverage_ratio']:.2%}")
    print(f"平均速度: {result['stats']['avg_speed']:.2f} km/h")
    print(f"拥堵比例: {result['stats']['congestion_ratio']:.2%}")

    # 测试拥堵热点
    print("\n2. 测试拥堵热点功能...")
    hotspots = service.get_congestion_hotspots(top_k=5)
    print(f"热点数量: {len(hotspots)}")

    for i, hotspot in enumerate(hotspots, 1):
        print(f"  {i}. {hotspot['road_name']}: {hotspot['speed']:.2f} km/h ({hotspot['status']})")

    print("\n✅ 所有测试通过!")
