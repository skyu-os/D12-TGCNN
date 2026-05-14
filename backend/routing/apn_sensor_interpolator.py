"""
基于APN (Adaptive Patching Network) 思想的传感器插值器
将时间感知的加权平均策略应用到空间传感器插值中
"""

import numpy as np
import math
from typing import Dict, List, Tuple, Optional
from collections import defaultdict
from backend.routing.sensor_road_mapper import SensorRoadMapper


class TimeAwareSpatialInterpolation:
    """
    时间感知的空间插值器

    核心思想：
    1. 动态学习每个传感器的影响范围（类似APN的patch boundaries）
    2. 使用软加权机制（sigmoid函数）实现平滑的空间过渡
    3. 考虑时间因素（如时段、交通模式）对插值的影响
    """

    def __init__(self, mapper: SensorRoadMapper, n_patches: int = 8):
        """
        Args:
            mapper: 传感器-路网映射器
            n_patches: 空间patch数量（类似APN的P参数）
        """
        self.mapper = mapper
        self.n_patches = n_patches

        # 可学习参数的初始化值（实际应用中可以通过训练优化）
        # 这些参数控制传感器的影响范围和权重
        self.distance_tau = 0.08  # 距离衰减参数（优化后，增大影响范围）
        self.time_influence = 0.3  # 时间影响权重

        # 为每个传感器初始化影响范围参数
        self.sensor_influence_ranges = {}
        self._initialize_sensor_ranges()

        # 缓存边的中点坐标，避免重复计算
        self._edge_midpoints_cache = {}

    def _initialize_sensor_ranges(self):
        """初始化每个传感器的影响范围"""
        for sensor in self.mapper.sensors:
            # 基于传感器类型设置不同的默认影响范围
            if sensor['type'] == 'ML':  # 主线传感器影响范围更大
                base_range = 0.08  # 约8km
            elif sensor['type'] in ['OR', 'FR']:  # 匝道传感器
                base_range = 0.05  # 约5km
            else:
                base_range = 0.06  # 约6km

            self.sensor_influence_ranges[sensor['id']] = {
                'base_range': base_range,
                'left_boundary': 0.0,  # 动态左边界
                'right_boundary': base_range,  # 动态右边界
                'learnable_tau': self.distance_tau  # 可学习的tau参数
            }

    def _sigmoid_weight(self, distance: float, left_bound: float,
                       right_bound: float, tau: float) -> float:
        """
        计算sigmoid权重（类似APN的加权策略）

        Args:
            distance: 距离传感器的距离
            left_bound: 左边界
            right_bound: 右边界
            tau: 软化参数

        Returns:
            归一化的权重值 [0, 1]
        """
        # 使用双sigmoid函数实现平滑的空间加权
        # weight = sigmoid((right_bound - distance) / tau) * sigmoid((distance - left_bound) / tau)

        def sigmoid(x):
            return 1.0 / (1.0 + math.exp(-x))

        # 转换为度数距离
        dist_degrees = distance / 111.0  # 粗略转换：1度约111km

        weight_left = sigmoid((right_bound - dist_degrees) / (tau + 1e-6))
        weight_right = sigmoid((dist_degrees - left_bound) / (tau + 1e-6))

        return weight_left * weight_right

    def _get_time_factor(self, hour: int, day_of_week: int = None) -> float:
        """
        获取时间影响因子

        Args:
            hour: 小时 (0-23)
            day_of_week: 星期几 (0-6, Monday=0)

        Returns:
            时间影响因子 [0.5, 1.5]
        """
        # 时段影响
        if 7 <= hour < 9 or 17 <= hour < 19:  # 高峰时段
            time_factor = 1.3
        elif 9 <= hour < 17:  # 白天非高峰
            time_factor = 1.1
        elif 22 <= hour or hour < 6:  # 夜间
            time_factor = 0.7
        else:  # 其他时段
            time_factor = 1.0

        # 星期影响（如果提供）
        if day_of_week is not None:
            if day_of_week >= 5:  # 周末
                time_factor *= 0.8

        return time_factor

    def _calculate_adaptive_influence(self, edge_lat: float, edge_lon: float,
                                     sensor_id: int, hour: int = 12,
                                     day_of_week: int = None) -> float:
        """
        计算传感器对边的自适应影响权重

        Args:
            edge_lat: 边的纬度
            edge_lon: 边的经度
            sensor_id: 传感器ID
            hour: 当前小时
            day_of_week: 星期几

        Returns:
            影响权重
        """
        sensor = next((s for s in self.mapper.sensors if s['id'] == sensor_id), None)
        if not sensor:
            return 0.0

        # 计算距离
        distance = math.sqrt(
            (sensor['latitude'] - edge_lat)**2 +
            (sensor['longitude'] - edge_lon)**2
        ) * 111  # 转换为km

        # 获取传感器影响范围参数
        range_params = self.sensor_influence_ranges.get(sensor_id, {
            'base_range': 0.06,
            'left_boundary': 0.0,
            'right_boundary': 0.06,
            'learnable_tau': self.distance_tau
        })

        # 计算空间权重
        spatial_weight = self._sigmoid_weight(
            distance,
            range_params['left_boundary'],
            range_params['right_boundary'],
            range_params['learnable_tau']
        )

        # 计算时间因子
        time_factor = self._get_time_factor(hour, day_of_week)

        # 综合权重
        adaptive_weight = spatial_weight * time_factor

        return adaptive_weight

    def create_adaptive_speed_field(self, sensor_speeds: Dict[int, float],
                                   hour: int = 12,
                                   day_of_week: int = None,
                                   use_temporal_smoothing: bool = True) -> Dict[Tuple[int, int, int], float]:
        """
        创建自适应速度场（核心方法）

        Args:
            sensor_speeds: 传感器ID -> 速度的字典
            hour: 当前小时 (0-23)
            day_of_week: 星期几 (0-6)
            use_temporal_smoothing: 是否使用时间平滑

        Returns:
            边 -> 速度的字典
        """
        edge_speeds = {}

        # 预先提取所有传感器位置，减少循环内的查找
        sensor_positions = {}
        for sensor in self.mapper.sensors:
            if sensor['id'] in sensor_speeds:
                sensor_positions[sensor['id']] = (sensor['latitude'], sensor['longitude'])

        # 为每条边计算自适应插值速度
        for u, v, key in self.mapper.graph.G.edges(keys=True):
            # 使用缓存的中点坐标
            edge_key = (u, v, key)
            if edge_key in self._edge_midpoints_cache:
                edge_lat, edge_lon = self._edge_midpoints_cache[edge_key]
            else:
                u_data = self.mapper.graph.G.nodes[u]
                v_data = self.mapper.graph.G.nodes[v]
                edge_lat = (u_data.get('y', 0) + v_data.get('y', 0)) / 2
                edge_lon = (u_data.get('x', 0) + v_data.get('x', 0)) / 2
                self._edge_midpoints_cache[edge_key] = (edge_lat, edge_lon)

            # 计算所有传感器对该边的自适应影响权重
            weights = []
            speeds = []

            for sensor_id, speed in sensor_speeds.items():
                if sensor_id not in sensor_positions:
                    continue

                # 快速计算距离（使用预先提取的位置）
                sensor_lat, sensor_lon = sensor_positions[sensor_id]
                distance = math.sqrt(
                    (sensor_lat - edge_lat)**2 +
                    (sensor_lon - edge_lon)**2
                ) * 111  # 转换为km

                # 获取传感器影响范围参数
                range_params = self.sensor_influence_ranges.get(sensor_id, {
                    'base_range': 0.06,
                    'left_boundary': 0.0,
                    'right_boundary': 0.08,
                    'learnable_tau': self.distance_tau
                })

                # 优化的空间权重计算
                dist_degrees = distance / 111.0
                tau = range_params['learnable_tau'] + 1e-6
                right_bound = range_params['right_boundary']

                # 使用简单的指数衰减，避免双重sigmoid的计算开销
                if dist_degrees < right_bound:
                    spatial_weight = 1.0 / (1.0 + (dist_degrees / tau)**2)
                else:
                    spatial_weight = 0.0

                if spatial_weight < 0.01:
                    continue

                # 计算时间因子
                time_factor = self._get_time_factor(hour, day_of_week)

                # 综合权重
                adaptive_weight = spatial_weight * time_factor

                weights.append(adaptive_weight)
                speeds.append(speed)

            if weights:
                # 归一化权重
                weights = np.array(weights)
                weights = weights / (weights.sum() + 1e-9)

                # 加权平均
                interpolated_speed = np.sum(np.array(speeds) * weights)
            else:
                # 回退到简单方法
                interpolated_speed = self._fallback_interpolation(
                    u, v, key, sensor_speeds
                )

            edge_speeds[(u, v, key)] = interpolated_speed

        return edge_speeds

    def _fallback_interpolation(self, u: int, v: int, key: int,
                               sensor_speeds: Dict[int, float]) -> float:
        """回退插值方法（当自适应方法失败时）"""
        # 使用现有的插值方法
        from backend.routing.sensor_road_mapper import SpeedInterpolator
        interpolator = SpeedInterpolator(self.mapper)
        return interpolator._nearest_interpolate(u, v, key, sensor_speeds)

    def optimize_sensor_ranges(self, historical_data: Dict[int, List[Tuple[float, float, float]]]):
        """
        基于历史数据优化传感器影响范围

        Args:
            historical_data: 传感器ID -> [(lat, lon, actual_speed), ...] 的历史数据
        """
        print("[INFO] 开始优化传感器影响范围...")

        for sensor_id, data_points in historical_data.items():
            if sensor_id not in self.sensor_influence_ranges:
                continue

            # 分析历史数据的空间分布
            if len(data_points) < 10:  # 数据点太少，跳过
                continue

            distances = []
            for lat, lon, speed in data_points:
                sensor = next((s for s in self.mapper.sensors if s['id'] == sensor_id), None)
                if sensor:
                    dist = math.sqrt(
                        (sensor['latitude'] - lat)**2 +
                        (sensor['longitude'] - lon)**2
                    ) * 111
                    distances.append(dist)

            if distances:
                # 基于历史数据调整影响范围
                mean_distance = np.mean(distances)
                std_distance = np.std(distances)

                # 更新影响范围（均值 + 2倍标准差）
                new_range = (mean_distance + 2 * std_distance) / 111.0  # 转换为度数
                new_range = min(max(new_range, 0.02), 0.15)  # 限制在合理范围内

                self.sensor_influence_ranges[sensor_id]['base_range'] = new_range
                self.sensor_influence_ranges[sensor_id]['right_boundary'] = new_range

        print("[OK] 传感器影响范围优化完成")


class APNStyleSensorInterpolator:
    """
    APN风格的传感器插值器（完整版）
    结合了时间感知、自适应patching和注意力机制
    """

    def __init__(self, mapper: SensorRoadMapper, n_patches: int = 8):
        self.mapper = mapper
        self.time_aware_interpolator = TimeAwareSpatialInterpolation(mapper, n_patches)

    def create_speed_field(self, sensor_speeds: Dict[int, float],
                          method: str = 'adaptive',
                          hour: int = 12,
                          day_of_week: int = None) -> Dict[Tuple[int, int, int], float]:
        """
        创建速度场

        Args:
            sensor_speeds: 传感器速度数据
            method: 插值方法 ('adaptive', 'nearest', 'inverse_distance', 'average')
            hour: 当前小时
            day_of_week: 星期几

        Returns:
            边 -> 速度的字典
        """
        if method == 'adaptive':
            return self.time_aware_interpolator.create_adaptive_speed_field(
                sensor_speeds, hour, day_of_week
            )
        else:
            # 回退到传统方法
            from backend.routing.sensor_road_mapper import SpeedInterpolator
            interpolator = SpeedInterpolator(self.mapper)
            return interpolator.create_speed_field(sensor_speeds, method)

    def get_interpolation_statistics(self, edge_speeds: Dict[Tuple[int, int, int], float]) -> Dict:
        """获取插值统计信息"""
        speeds = list(edge_speeds.values())

        return {
            'num_edges': len(edge_speeds),
            'min_speed': float(np.min(speeds)),
            'max_speed': float(np.max(speeds)),
            'mean_speed': float(np.mean(speeds)),
            'std_speed': float(np.std(speeds)),
            'median_speed': float(np.median(speeds)),
            'percentile_25': float(np.percentile(speeds, 25)),
            'percentile_75': float(np.percentile(speeds, 75))
        }


def demo_apn_style_interpolation():
    """演示APN风格的传感器插值"""
    print("=" * 60)
    print("APN风格传感器插值演示")
    print("=" * 60)

    from backend.graph.road_graph import RoadGraph
    from backend.graph.sensor_parser import parse_sensors

    # 1. 加载路网和传感器
    print("\n[步骤1] 加载路网和传感器数据...")
    road_graph = RoadGraph.build_from_osm()
    sensors = parse_sensors()
    print(f"[OK] 路网节点: {road_graph.G.number_of_nodes():,}")
    print(f"[OK] 传感器数量: {len(sensors):,}")

    # 2. 创建映射器
    print("\n[步骤2] 创建传感器-路网映射...")
    from backend.routing.sensor_road_mapper import SensorRoadMapper
    mapper = SensorRoadMapper(road_graph)
    mapper.build_mapping()

    # 3. 创建APN风格插值器
    print("\n[步骤3] 创建APN风格插值器...")
    apn_interpolator = APNStyleSensorInterpolator(mapper, n_patches=8)
    print("[OK] APN风格插值器初始化完成")

    # 4. 创建模拟速度数据
    print("\n[步骤4] 创建模拟速度数据...")
    sensor_speeds = {}
    for sensor in sensors[:100]:  # 使用前100个传感器
        if sensor['type'] == 'ML':
            speed = np.random.uniform(60, 100)
        elif sensor['type'] in ['OR', 'FR']:
            speed = np.random.uniform(30, 60)
        else:
            speed = np.random.uniform(40, 80)
        sensor_speeds[sensor['id']] = speed

    print(f"[OK] 创建了 {len(sensor_speeds)} 个传感器的速度数据")
    print(f"     速度范围: {min(sensor_speeds.values()):.1f} - {max(sensor_speeds.values()):.1f} km/h")

    # 5. 对比不同时段的插值效果
    print("\n[步骤5] 对比不同时段的插值效果...")
    time_scenarios = [
        (8, "早高峰"),
        (12, "中午"),
        (18, "晚高峰"),
        (2, "夜间")
    ]

    for hour, description in time_scenarios:
        edge_speeds = apn_interpolator.create_speed_field(
            sensor_speeds, method='adaptive', hour=hour
        )
        stats = apn_interpolator.get_interpolation_statistics(edge_speeds)

        print(f"\n{description} (hour={hour}):")
        print(f"  插值边数: {stats['num_edges']:,}")
        print(f"  速度范围: {stats['min_speed']:.1f} - {stats['max_speed']:.1f} km/h")
        print(f"  平均速度: {stats['mean_speed']:.1f} km/h")
        print(f"  标准差: {stats['std_speed']:.1f} km/h")

    # 6. 对比不同插值方法
    print(f"\n[步骤6] 对比不同插值方法...")
    methods = ['adaptive', 'nearest', 'inverse_distance', 'average']

    print(f"\n{'方法':<20} {'边数':>12} {'最小值':>10} {'最大值':>10} {'平均值':>10} {'标准差':>10}")
    print("-" * 64)

    for method in methods:
        edge_speeds = apn_interpolator.create_speed_field(
            sensor_speeds, method=method, hour=12
        )
        stats = apn_interpolator.get_interpolation_statistics(edge_speeds)

        print(f"{method:<20} {stats['num_edges']:>12,} {stats['min_speed']:>10.1f} "
              f"{stats['max_speed']:>10.1f} {stats['mean_speed']:>10.1f} {stats['std_speed']:>10.1f}")

    print("\n" + "=" * 60)
    print("演示完成！")
    print("=" * 60)
    print("\n关键优势:")
    print("1. 时间感知: 考虑时段对交通的影响")
    print("2. 自适应范围: 动态调整传感器影响范围")
    print("3. 平滑加权: 使用sigmoid函数实现平滑过渡")
    print("4. 多方法融合: 可与传统方法结合使用")


if __name__ == "__main__":
    demo_apn_style_interpolation()