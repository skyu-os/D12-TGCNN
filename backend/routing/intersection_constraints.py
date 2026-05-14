"""
路口与转向约束系统
处理红绿灯等待时间、转向惩罚、掉头限制等真实驾驶约束
"""

import math
from typing import Dict, List, Optional, Tuple
from enum import Enum


class TurnType(Enum):
    """转向类型"""
    THROUGH = "through"      # 直行
    LEFT = "left"           # 左转
    RIGHT = "right"         # 右转
    U_TURN = "u_turn"       # 掉头


class IntersectionType(Enum):
    """路口类型"""
    SIGNAL = "signal"       # 信号灯路口
    STOP_SIGN = "stop"      # 停车标志
    YIELD = "yield"         # 让行标志
    UNSIGNALIZED = "unsignalized"  # 无信号路口
    FREEWAY = "freeway"     # 高速公路（无路口）


class IntersectionConstraints:
    """路口与转向约束管理器"""

    # 默认转向惩罚（秒）
    DEFAULT_TURN_PENALTIES = {
        TurnType.THROUGH: 0.0,      # 直行无惩罚
        TurnType.RIGHT: 5.0,        # 右转惩罚5秒
        TurnType.LEFT: 15.0,        # 左转惩罚15秒
        TurnType.U_TURN: 30.0,      # 掉头惩罚30秒
    }

    # 红绿灯等待时间（秒）— 概率期望值（≈ 遇红灯概率 × 平均红灯时长）
    DEFAULT_SIGNAL_WAIT_TIMES = {
        IntersectionType.SIGNAL: 4.0,       # 信号灯路口（~30%概率等红灯 × 12s平均等待）
        IntersectionType.STOP_SIGN: 2.0,    # 停车标志（短暂停车+观察）
        IntersectionType.YIELD: 1.0,        # 让行标志
        IntersectionType.UNSIGNALIZED: 0.0, # 无信号路口不等待
        IntersectionType.FREEWAY: 0.0,      # 高速公路无路口
    }

    # 车辆启动时间（秒）- 不同车辆类型从静止到正常行驶的时间
    VEHICLE_STARTUP_TIMES = {
        'gasoline': 3.0,    # 燃油车启动时间（引擎启动+加速）
        'diesel': 4.0,      # 柴油车启动时间较长
        'electric': 1.5,    # 电动车启动时间短（电机响应快）
        'hybrid': 2.0,      # 混合动力车启动时间中等
    }

    # 基于路口类型的启动时间调整因子
    STARTUP_ADJUSTMENT_FACTORS = {
        IntersectionType.SIGNAL: 1.0,       # 信号灯路口正常启动
        IntersectionType.STOP_SIGN: 0.8,    # 停车标志后启动较快
        IntersectionType.YIELD: 0.5,        # 让行后可能不完全停止
        IntersectionType.UNSIGNALIZED: 0.7, # 无信号路口启动较快
        IntersectionType.FREEWAY: 0.0,      # 高速公路无需启动
    }

    # 基于时间的信号灯调整因子
    TIME_OF_DAY_FACTORS = {
        'morning_peak': 1.5,    # 早高峰等待时间增加50%
        'evening_peak': 1.5,    # 晚高峰等待时间增加50%
        'night': 0.5,           # 夜间等待时间减少50%
        'normal': 1.0,          # 正常时段
    }

    def __init__(
        self,
        turn_penalties: Optional[Dict[TurnType, float]] = None,
        signal_wait_times: Optional[Dict[IntersectionType, float]] = None,
        vehicle_type: str = 'gasoline'
    ):
        """
        Args:
            turn_penalties: 各转向类型的惩罚时间（秒）
            signal_wait_times: 各路口类型的平均等待时间（秒）
            vehicle_type: 车辆类型，影响启动时间
        """
        self.turn_penalties = turn_penalties or self.DEFAULT_TURN_PENALTIES.copy()
        self.signal_wait_times = signal_wait_times or self.DEFAULT_SIGNAL_WAIT_TIMES.copy()
        self.vehicle_type = vehicle_type

        # 路口属性缓存（节点ID -> 路口属性）
        self.intersection_cache: Dict[int, Dict] = {}

    def detect_turn_type(
        self,
        incoming_bearing: float,
        outgoing_bearing: float
    ) -> TurnType:
        """
        检测转向类型

        Args:
            incoming_bearing: 入边方位角（度，0-360）
            outgoing_bearing: 出边方位角（度，0-360）

        Returns:
            转向类型
        """
        # 计算角度差（-180 到 180）
        angle_diff = (outgoing_bearing - incoming_bearing + 180) % 360 - 180

        if abs(angle_diff) <= 20:
            return TurnType.THROUGH
        elif angle_diff > 20 and angle_diff <= 150:
            return TurnType.RIGHT
        elif angle_diff < -20 and angle_diff >= -150:
            return TurnType.LEFT
        else:
            return TurnType.U_TURN

    def get_turn_penalty(self, turn_type: TurnType) -> float:
        """
        获取转向惩罚时间

        Args:
            turn_type: 转向类型

        Returns:
            惩罚时间（秒）
        """
        return self.turn_penalties.get(turn_type, 0.0)

    def estimate_intersection_type(
        self,
        node_degree: int,
        road_types: List[str]
    ) -> IntersectionType:
        """
        估计路口类型

        Args:
            node_degree: 节点度数（连接的道路数量）
            road_types: 连接的道路类型列表

        Returns:
            路口类型
        """
        # 高速公路
        if any(rt in ['motorway', 'trunk'] for rt in road_types):
            return IntersectionType.FREEWAY

        major_roads = {'motorway', 'trunk', 'primary', 'secondary', 'tertiary'}
        has_major = any(rt in major_roads for rt in road_types)

        # 主要道路的复杂路口 → 信号灯；次要路口 → 停车标志
        if node_degree >= 4:
            return IntersectionType.SIGNAL if has_major else IntersectionType.STOP_SIGN

        # 简单路口（度数<=3）
        if node_degree <= 3:
            if has_major:
                return IntersectionType.STOP_SIGN
            else:
                return IntersectionType.UNSIGNALIZED

        return IntersectionType.UNSIGNALIZED

    def get_signal_wait_time(
        self,
        intersection_type: IntersectionType,
        time_of_day: str = 'normal'
    ) -> float:
        """
        获取信号灯等待时间

        Args:
            intersection_type: 路口类型
            time_of_day: 时段 ('morning_peak', 'evening_peak', 'night', 'normal')

        Returns:
            等待时间（秒）
        """
        base_wait = self.signal_wait_times.get(intersection_type, 0.0)
        time_factor = self.TIME_OF_DAY_FACTORS.get(time_of_day, 1.0)

        return base_wait * time_factor

    def get_startup_time(
        self,
        intersection_type: IntersectionType
    ) -> float:
        """
        获取车辆启动时间

        Args:
            intersection_type: 路口类型

        Returns:
            启动时间（秒）
        """
        base_startup = self.VEHICLE_STARTUP_TIMES.get(self.vehicle_type, 3.0)
        adjustment = self.STARTUP_ADJUSTMENT_FACTORS.get(intersection_type, 0.0)
        return base_startup * adjustment

    def calculate_intersection_cost(
        self,
        node_id: int,
        incoming_bearing: float,
        outgoing_bearing: float,
        node_degree: int,
        road_types: List[str],
        time_of_day: str = 'normal'
    ) -> float:
        """
        计算通过路口的总代价

        Args:
            node_id: 节点ID
            incoming_bearing: 入边方位角
            outgoing_bearing: 出边方位角
            node_degree: 节点度数
            road_types: 连接的道路类型
            time_of_day: 时段

        Returns:
            总代价（秒）
        """
        # 1. 检测转向类型
        turn_type = self.detect_turn_type(incoming_bearing, outgoing_bearing)

        # 2. 获取转向惩罚
        turn_cost = self.get_turn_penalty(turn_type)

        # 3. 估计路口类型
        intersection_type = self.estimate_intersection_type(node_degree, road_types)

        # 4. 获取信号灯等待时间
        signal_cost = self.get_signal_wait_time(intersection_type, time_of_day)

        # 5. 获取车辆启动时间
        startup_cost = self.get_startup_time(intersection_type)

        # 6. 总代价
        total_cost = turn_cost + signal_cost + startup_cost

        return total_cost

    def cache_intersection_attributes(
        self,
        node_id: int,
        attributes: Dict
    ):
        """缓存路口属性"""
        self.intersection_cache[node_id] = attributes

    def get_intersection_attributes(self, node_id: int) -> Optional[Dict]:
        """获取缓存的路口属性"""
        return self.intersection_cache.get(node_id)

    def get_time_of_day(self, hour: int) -> str:
        """
        根据小时数确定时段

        Args:
            hour: 小时数（0-23）

        Returns:
            时段标识
        """
        if 7 <= hour < 9:
            return 'morning_peak'
        elif 17 <= hour < 19:
            return 'evening_peak'
        elif 22 <= hour or hour < 6:
            return 'night'
        else:
            return 'normal'


class EdgeBearingCalculator:
    """计算边的方位角"""

    @staticmethod
    def calculate_bearing(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
        """
        计算从点1到点2的方位角（度）

        Args:
            lat1, lon1: 起点（纬度，经度）
            lat2, lon2: 终点（纬度，经度）

        Returns:
            方位角（0-360度，正北为0）
        """
        lat1_rad = math.radians(lat1)
        lat2_rad = math.radians(lat2)
        diff_lon = math.radians(lon2 - lon1)

        x = math.sin(diff_lon) * math.cos(lat2_rad)
        y = math.cos(lat1_rad) * math.sin(lat2_rad) - (
            math.sin(lat1_rad) * math.cos(lat2_rad) * math.cos(diff_lon)
        )

        bearing = math.atan2(x, y)
        bearing = math.degrees(bearing)
        bearing = (bearing + 360) % 360

        return bearing

    @staticmethod
    def calculate_edge_bearing(graph, u: int, v: int, key: int = 0) -> float:
        """
        计算边的方位角

        Args:
            graph: NetworkX图对象
            u: 起始节点ID
            v: 结束节点ID
            key: 边的键（默认0）

        Returns:
            方位角（0-360度）
        """
        u_data = graph.nodes[u]
        v_data = graph.nodes[v]

        lat1 = u_data.get('y', 0)
        lon1 = u_data.get('x', 0)
        lat2 = v_data.get('y', 0)
        lon2 = v_data.get('x', 0)

        return EdgeBearingCalculator.calculate_bearing(lat1, lon1, lat2, lon2)


# 便捷函数
def create_default_constraints(vehicle_type: str = 'gasoline') -> IntersectionConstraints:
    """创建默认的路口约束管理器"""
    return IntersectionConstraints(vehicle_type=vehicle_type)


def create_custom_constraints(
    left_turn_penalty: float = 15.0,
    right_turn_penalty: float = 5.0,
    u_turn_penalty: float = 30.0,
    signal_wait_time: float = 30.0,
    vehicle_type: str = 'gasoline'
) -> IntersectionConstraints:
    """
    创建自定义的路口约束管理器

    Args:
        left_turn_penalty: 左转惩罚时间（秒）
        right_turn_penalty: 右转惩罚时间（秒）
        u_turn_penalty: 掉头惩罚时间（秒）
        signal_wait_time: 信号灯等待时间（秒）
        vehicle_type: 车辆类型

    Returns:
        配置好的约束管理器
    """
    turn_penalties = {
        TurnType.THROUGH: 0.0,
        TurnType.RIGHT: right_turn_penalty,
        TurnType.LEFT: left_turn_penalty,
        TurnType.U_TURN: u_turn_penalty,
    }

    signal_wait_times = {
        IntersectionType.SIGNAL: signal_wait_time,
        IntersectionType.STOP_SIGN: 5.0,
        IntersectionType.YIELD: 3.0,
        IntersectionType.UNSIGNALIZED: 2.0,
        IntersectionType.FREEWAY: 0.0,
    }

    return IntersectionConstraints(turn_penalties, signal_wait_times, vehicle_type)
