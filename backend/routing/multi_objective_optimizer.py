"""
多目标路径优化器
支持能耗、碳排放、舒适性等多种优化目标
"""

import math
from enum import Enum
from typing import Dict, List, Optional


class OptimizationObjective(Enum):
    """优化目标类型"""

    TIME = "time"  # 最短时间
    DISTANCE = "distance"  # 最短距离
    ENERGY = "energy"  # 最少能耗
    CARBON = "carbon"  # 最低碳排放
    COMFORT = "comfort"  # 最舒适（道路平顺性）
    BALANCED = "balanced"  # 平衡模式


class MultiObjectiveOptimizer:
    """多目标路径优化器"""

    # 车辆参数（默认为普通燃油车）
    DEFAULT_VEHICLE_PARAMS = {
        "mass": 1500,  # 车辆质量 (kg)
        "drag_coefficient": 0.3,  # 空气阻力系数
        "frontal_area": 2.2,  # 迎风面积 (m²)
        "rolling_coefficient": 0.015,  # 滚动阻力系数
        "efficiency": 0.25,  # 发动机效率
        "fuel_calorific": 44.4,  # 燃料热值 (MJ/kg)
        "carbon_factor": 3.15,  # 碳排放因子 (kg CO2/kg fuel)
    }

    # 道路类型舒适性权重
    ROAD_COMFORT_WEIGHTS = {
        "motorway": 1.0,  # 高速公路最舒适
        "trunk": 0.9,
        "primary": 0.8,
        "secondary": 0.7,
        "tertiary": 0.6,
        "residential": 0.5,  # 居住区较舒适
        "service": 0.4,
    }

    def __init__(self, vehicle_params: Optional[Dict] = None):
        """
        Args:
            vehicle_params: 车辆参数，默认使用普通燃油车参数
        """
        self.vehicle_params = vehicle_params or self.DEFAULT_VEHICLE_PARAMS.copy()
        self.objective_weights = {
            OptimizationObjective.TIME: 1.0,
            OptimizationObjective.DISTANCE: 1.0,
            OptimizationObjective.ENERGY: 1.0,
            OptimizationObjective.CARBON: 1.0,
            OptimizationObjective.COMFORT: 1.0,
        }

    def set_objective_weights(self, weights: Dict[OptimizationObjective, float]):
        """设置各优化目标的权重"""
        for obj, weight in weights.items():
            if obj in self.objective_weights:
                self.objective_weights[obj] = weight

    def calculate_energy_consumption(
        self,
        distance: float,  # 米
        speed: float,  # km/h
        road_type: str = "primary",
        elevation_change: float = 0,  # 海拔变化（米）
    ) -> float:
        """
        计算路段的能耗（MJ）

        Args:
            distance: 路段距离（米）
            speed: 平均速度（km/h）
            road_type: 道路类型
            elevation_change: 海拔变化（米），正值为上坡

        Returns:
            能耗（兆焦耳 MJ）
        """
        if distance <= 0 or speed <= 0:
            return 0.0

        distance_km = distance / 1000.0  # 转换为公里
        speed_ms = speed / 3.6  # 转换为米/秒

        # 基础物理参数
        g = 9.81  # 重力加速度
        rho_air = 1.225  # 空气密度 (kg/m³)
        m = self.vehicle_params["mass"]
        Cd = self.vehicle_params["drag_coefficient"]
        Af = self.vehicle_params["frontal_area"]
        Cr = self.vehicle_params["rolling_coefficient"]

        # 1. 滚动阻力功率 (W)
        P_rolling = Cr * m * g * speed_ms

        # 2. 空气阻力功率 (W)
        P_aero = 0.5 * rho_air * Cd * Af * speed_ms**3

        # 3. 坡度阻力功率 (W)
        P_grade = m * g * speed_ms * math.sin(math.atan(elevation_change / distance))

        # 总功率 (W)
        P_total = P_rolling + P_aero + P_grade

        # 行驶时间 (秒)
        time_s = distance / speed_ms

        # 所需能量 (焦耳)
        energy_joules = P_total * time_s

        # 考虑发动机效率，计算燃料能量 (MJ)
        efficiency = self.vehicle_params["efficiency"]
        fuel_energy_mj = energy_joules / (efficiency * 1e6)

        return max(0, fuel_energy_mj)  # 确保非负

    def calculate_carbon_emission(self, energy_mj: float) -> float:
        """
        计算碳排放量（kg CO2）

        Args:
            energy_mj: 燃料能量 (MJ)

        Returns:
            碳排放量 (kg CO2)
        """
        if energy_mj <= 0:
            return 0.0

        carbon_factor = self.vehicle_params["carbon_factor"]
        return energy_mj * carbon_factor

    def calculate_comfort_score(
        self, road_type: str, distance: float, speed: float
    ) -> float:
        """
        计算舒适性得分（0-1，1为最舒适）

        舒适性因素：
        - 道路类型（高速公路更舒适）
        - 速度稳定性（匀速更舒适）
        - 路段长度（连续长路段更舒适）
        """
        # 基础舒适性（基于道路类型）
        base_comfort = self.ROAD_COMFORT_WEIGHTS.get(road_type, 0.5)

        # 速度稳定性惩罚（速度变化越大越不舒适）
        # 这里简化处理，假设高速公路速度更稳定
        speed_comfort = min(1.0, speed / 80.0)  # 80km/h以上为最佳

        # 路段连续性（长路段更舒适）
        distance_comfort = min(1.0, distance / 1000.0)  # 1km以上为最佳

        # 综合舒适性
        comfort_score = (
            base_comfort * 0.6 + speed_comfort * 0.2 + distance_comfort * 0.2
        )

        return max(0.0, min(1.0, comfort_score))

    def calculate_comprehensive_cost(
        self,
        distance: float,
        speed: float,
        road_type: str = "primary",
        elevation_change: float = 0,
        objective: OptimizationObjective = OptimizationObjective.BALANCED,
    ) -> float:
        """
        计算综合代价

        Args:
            distance: 距离（米）
            speed: 速度（km/h）
            road_type: 道路类型
            elevation_change: 海拔变化（米）
            objective: 主要优化目标

        Returns:
            综合代价（越小越好）
        """
        # 基础指标
        time_cost = distance / (speed / 3.6) if speed > 0 else float("inf")  # 秒
        energy_mj = self.calculate_energy_consumption(
            distance, speed, road_type, elevation_change
        )
        carbon_kg = self.calculate_carbon_emission(energy_mj)
        comfort_score = self.calculate_comfort_score(road_type, distance, speed)
        discomfort_cost = (1 - comfort_score) * distance  # 不舒适代价

        # 根据目标计算综合代价
        if objective == OptimizationObjective.TIME:
            return time_cost

        elif objective == OptimizationObjective.DISTANCE:
            return distance

        elif objective == OptimizationObjective.ENERGY:
            return energy_mj

        elif objective == OptimizationObjective.CARBON:
            return carbon_kg

        elif objective == OptimizationObjective.COMFORT:
            return discomfort_cost

        elif objective == OptimizationObjective.BALANCED:
            # 平衡模式：加权组合
            weights = {
                "time": 1.0,
                "distance": 0.1,
                "energy": 0.5,
                "carbon": 0.3,
                "comfort": 0.4,
            }

            # 归一化各项指标
            normalized_time = time_cost / 3600.0  # 小时
            normalized_distance = distance / 1000.0  # 公里
            normalized_energy = energy_mj / 10.0  # 10MJ为单位
            normalized_carbon = carbon_kg / 1.0  # 1kg为单位
            normalized_discomfort = discomfort_cost / 1000.0  # 1km为单位

            comprehensive_cost = (
                weights["time"] * normalized_time
                + weights["distance"] * normalized_distance
                + weights["energy"] * normalized_energy
                + weights["carbon"] * normalized_carbon
                + weights["comfort"] * normalized_discomfort
            )

            return comprehensive_cost

        return time_cost  # 默认为时间

    def get_objective_description(self, objective: OptimizationObjective) -> str:
        """获取优化目标的描述"""
        descriptions = {
            OptimizationObjective.TIME: "最短时间优先",
            OptimizationObjective.DISTANCE: "最短距离优先",
            OptimizationObjective.ENERGY: "最低能耗优先",
            OptimizationObjective.CARBON: "最低碳排放优先",
            OptimizationObjective.COMFORT: "道路舒适性优先",
            OptimizationObjective.BALANCED: "平衡模式（综合优化）",
        }
        return descriptions.get(objective, "未知优化目标")


# 便捷函数
def create_optimizer(vehicle_type: str = "gasoline") -> MultiObjectiveOptimizer:
    """
    创建优化器

    Args:
        vehicle_type: 车辆类型 ('gasoline', 'diesel', 'electric', 'hybrid')

    Returns:
        配置好的优化器实例
    """
    vehicle_params = MultiObjectiveOptimizer.DEFAULT_VEHICLE_PARAMS.copy()

    if vehicle_type == "electric":
        # 电动车参数
        vehicle_params.update(
            {
                "mass": 1800,  # 电动车较重
                "drag_coefficient": 0.25,  # 流线型设计
                "efficiency": 0.85,  # 电机效率高
                "carbon_factor": 0.0,  # 使用时零排放
            }
        )
    elif vehicle_type == "diesel":
        vehicle_params.update(
            {
                "efficiency": 0.35,  # 柴油机效率较高
                "carbon_factor": 2.68,  # 柴油碳排放略低
            }
        )
    elif vehicle_type == "hybrid":
        vehicle_params.update(
            {
                "mass": 1600,
                "efficiency": 0.40,  # 混合动力效率高
                "carbon_factor": 2.9,
            }
        )

    return MultiObjectiveOptimizer(vehicle_params)
