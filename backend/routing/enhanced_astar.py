"""
增强版A*路径规划算法
支持多目标优化和路口约束
"""

import heapq
import math
from typing import List, Tuple, Optional, Dict, Any
from enum import Enum

from backend.routing.multi_objective_optimizer import (
    MultiObjectiveOptimizer,
    OptimizationObjective,
    create_optimizer
)
from backend.routing.intersection_constraints import (
    IntersectionConstraints,
    IntersectionType,
    TurnType,
    EdgeBearingCalculator,
    create_default_constraints
)


class OptimizationMode(Enum):
    """优化模式"""
    STANDARD = "standard"           # 标准模式（仅时间/距离）
    MULTI_OBJECTIVE = "multi_objective"  # 多目标优化
    WITH_CONSTRAINTS = "with_constraints"  # 包含路口约束
    FULL = "full"                  # 完整模式（多目标+约束）


class EnhancedAStarRouter:
    """增强版A*路径规划器"""

    def __init__(
        self,
        graph,
        optimizer: Optional[MultiObjectiveOptimizer] = None,
        constraints: Optional[IntersectionConstraints] = None
    ):
        """
        Args:
            graph: RoadGraph 实例
            optimizer: 多目标优化器
            constraints: 路口约束管理器
        """
        self.G = graph.G
        self.graph = graph
        self.optimizer = optimizer or create_optimizer()
        self.constraints = constraints or create_default_constraints()
        self.bearing_calculator = EdgeBearingCalculator()

    def _haversine(self, lat1: float, lon1: float, lat2: float, lon2: float) -> float:
        """计算两点间球面距离（米）- 作为 A* 启发函数"""
        R = 6371000  # 地球半径（米）
        dlat = math.radians(lat2 - lat1)
        dlon = math.radians(lon2 - lon1)
        a = (
            math.sin(dlat / 2) ** 2
            + math.cos(math.radians(lat1))
            * math.cos(math.radians(lat2))
            * math.sin(dlon / 2) ** 2
        )
        return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))

    def _heuristic(self, node: int, goal: int) -> float:
        """启发函数：当前节点到终点的直线距离"""
        node_data = self.G.nodes[node]
        goal_data = self.G.nodes[goal]
        return self._haversine(
            node_data.get("y", 0),
            node_data.get("x", 0),
            goal_data.get("y", 0),
            goal_data.get("x", 0),
        )

    def _get_road_type(self, u: int, v: int, key: int = 0) -> str:
        """获取道路类型"""
        edge_data = self.G.edges[u, v, key]
        highway_type = edge_data.get('highway', 'primary')
        if isinstance(highway_type, list):
            highway_type = highway_type[0]
        return highway_type

    def _calculate_edge_cost(
        self,
        u: int,
        v: int,
        key: int,
        objective: OptimizationObjective,
        mode: OptimizationMode
    ) -> Tuple[float, Dict[str, Any]]:
        """
        计算边的代价

        Args:
            u: 起始节点
            v: 目标节点
            key: 边键
            objective: 优化目标
            mode: 优化模式

        Returns:
            (代价, 详细信息字典)
        """
        length = self.graph.get_edge_length(u, v, key)
        speed = self.graph.get_edge_speed(u, v, key)
        road_type = self._get_road_type(u, v, key)

        # 基础时间和距离
        time_cost = self.graph.get_edge_weight(u, v, key, 'time')

        cost_info = {
            'length': length,
            'time': time_cost,
            'speed': speed,
            'road_type': road_type
        }

        if mode in [OptimizationMode.STANDARD, OptimizationMode.WITH_CONSTRAINTS]:
            if objective == OptimizationObjective.DISTANCE:
                return length, cost_info
            else:
                return time_cost, cost_info

        # 多目标优化模式
        if mode in [OptimizationMode.MULTI_OBJECTIVE, OptimizationMode.FULL]:
            elevation_change = 0  # 简化，暂不考虑海拔
            multi_cost = self.optimizer.calculate_comprehensive_cost(
                length, speed, road_type, elevation_change, objective
            )

            # 计算能耗和碳排放（用于统计）
            energy = self.optimizer.calculate_energy_consumption(length, speed, road_type, elevation_change)
            carbon = self.optimizer.calculate_carbon_emission(energy)
            comfort = self.optimizer.calculate_comfort_score(road_type, length, speed)

            cost_info.update({
                'energy': energy,
                'carbon': carbon,
                'comfort': comfort,
                'objective': objective.value
            })

            # 如果是完整模式，边代价使用多目标代价，但后面会加入路口约束
            if mode == OptimizationMode.MULTI_OBJECTIVE:
                return multi_cost, cost_info
            else:
                # 完整模式：在标准时间代价基础上，后面加入路口约束
                return time_cost, cost_info

        return time_cost, cost_info

    def _calculate_intersection_constraint_cost(
        self,
        u: int,
        v: int,
        prev_node: Optional[int],
        time_of_day: str = 'normal'
    ) -> Tuple[float, Dict[str, Any]]:
        """
        计算路口约束代价

        Args:
            u: 当前节点
            v: 下一个节点
            prev_node: 前一个节点（用于计算转向）
            time_of_day: 时段

        Returns:
            (约束代价, 详细信息字典)
        """
        constraint_info = {
            'turn_type': TurnType.THROUGH.value,
            'turn_penalty': 0.0,
            'intersection_type': IntersectionType.UNSIGNALIZED.value,
            'signal_wait': 0.0,
            'startup_time': 0.0,
            'total_constraint': 0.0
        }

        if prev_node is None:
            return 0.0, constraint_info

        # 计算入边和出边的方位角
        incoming_bearing = self.bearing_calculator.calculate_edge_bearing(
            self.G, prev_node, u
        )
        outgoing_bearing = self.bearing_calculator.calculate_edge_bearing(
            self.G, u, v
        )

        # 检测转向类型
        turn_type = self.constraints.detect_turn_type(incoming_bearing, outgoing_bearing)
        turn_penalty = self.constraints.get_turn_penalty(turn_type)

        # 获取路口类型
        node_degree = self.G.degree(u)
        road_types = []
        for neighbor in self.G.neighbors(u):
            for key in self.G[u][neighbor]:
                rt = self._get_road_type(u, neighbor, key)
                road_types.append(rt)
                break

        intersection_type = self.constraints.estimate_intersection_type(node_degree, road_types)
        signal_wait = self.constraints.get_signal_wait_time(intersection_type, time_of_day)

        # 直行 = 绿波通过，仅计极小的路过成本（保持"偏好高速"的倾向）
        if turn_type == TurnType.THROUGH:
            signal_wait = signal_wait * 0.1  # 路过的概率成本
            startup_time = 0.0
        else:
            startup_time = self.constraints.get_startup_time(intersection_type)

        total_constraint = turn_penalty + signal_wait + startup_time

        constraint_info = {
            'turn_type': turn_type.value,
            'turn_penalty': turn_penalty,
            'intersection_type': intersection_type.value,
            'signal_wait': signal_wait,
            'startup_time': startup_time,
            'total_constraint': total_constraint
        }

        return total_constraint, constraint_info

    def find_path(
        self,
        start_node: int,
        end_node: int,
        objective: str = "time",
        mode: str = "standard",
        time_of_day: str = 'normal'
    ) -> Optional[dict]:
        """
        增强版A*搜索路径

        Args:
            start_node: 起点节点 ID
            end_node: 终点节点 ID
            objective: 优化目标 ('time' | 'distance' | 'energy' | 'carbon' | 'comfort' | 'balanced')
            mode: 优化模式 ('standard' | 'multi_objective' | 'with_constraints' | 'full')
            time_of_day: 时段 ('normal' | 'morning_peak' | 'evening_peak' | 'night')

        Returns:
            路径信息字典或None
        """
        if start_node not in self.G or end_node not in self.G:
            return None

        # 解析参数
        opt_objective = OptimizationObjective(objective) if objective else OptimizationObjective.TIME
        opt_mode = OptimizationMode(mode) if mode else OptimizationMode.STANDARD

        # A* 核心
        open_set = [(0, 0, start_node, None)]  # (f_score, g_score, node, prev_node)
        came_from = {}
        g_score = {start_node: 0}
        f_score = {start_node: self._heuristic(start_node, end_node)}

        # 存储边代价信息
        edge_cost_info = {}
        constraint_info = {}

        while open_set:
            current_f, current_g, current, prev_node = heapq.heappop(open_set)

            if current == end_node:
                return self._reconstruct_path(
                    came_from, current, edge_cost_info, constraint_info, opt_objective, opt_mode
                )

            if current_f > f_score.get(current, float('inf')):
                continue

            for neighbor in self.G.neighbors(current):
                for key in self.G[current][neighbor]:
                    # 计算边代价
                    edge_cost, edge_info = self._calculate_edge_cost(
                        current, neighbor, key, opt_objective, opt_mode
                    )

                    # 计算路口约束代价
                    constraint_cost = 0.0
                    constraint_data = {}
                    if opt_mode in [OptimizationMode.WITH_CONSTRAINTS, OptimizationMode.FULL]:
                        constraint_cost, constraint_data = self._calculate_intersection_constraint_cost(
                            current, neighbor, prev_node, time_of_day
                        )

                    # 总代价 — 约束代价(s) 按目标换算
                    if constraint_cost > 0 and opt_mode in [OptimizationMode.WITH_CONSTRAINTS, OptimizationMode.FULL]:
                        edge_speed = self.graph.get_edge_speed(current, neighbor, key)
                        if opt_objective == OptimizationObjective.DISTANCE:
                            constraint_cost = constraint_cost * (edge_speed / 3.6)  # 秒→米
                        elif opt_objective == OptimizationObjective.ENERGY:
                            constraint_cost = constraint_cost * 0.005  # ~5kJ/s idle
                        elif opt_objective == OptimizationObjective.CARBON:
                            constraint_cost = constraint_cost * 0.015  # kg CO2/s
                        elif opt_objective == OptimizationObjective.COMFORT:
                            constraint_cost = constraint_cost * 0.5
                    total_edge_cost = edge_cost + constraint_cost

                    tentative_g = g_score[current] + total_edge_cost

                    if tentative_g < g_score.get(neighbor, float('inf')):
                        came_from[neighbor] = current
                        g_score[neighbor] = tentative_g
                        f = tentative_g + self._heuristic(neighbor, end_node)
                        f_score[neighbor] = f

                        # 存储代价信息
                        edge_cost_info[(current, neighbor)] = edge_info
                        if constraint_data:
                            constraint_info[(current, neighbor)] = constraint_data

                        heapq.heappush(open_set, (f, tentative_g, neighbor, current))

        return None  # 不可达

    def _reconstruct_path(
        self,
        came_from: dict,
        current: int,
        edge_cost_info: dict,
        constraint_info: dict,
        objective: OptimizationObjective,
        mode: OptimizationMode
    ) -> dict:
        """重建路径并计算详细统计信息"""
        path = [current]
        while current in came_from:
            current = came_from[current]
            path.append(current)
        path.reverse()

        # 计算详细统计
        total_distance = 0
        total_time = 0
        total_energy = 0
        total_carbon = 0
        avg_comfort = 0
        comfort_count = 0
        total_turn_penalties = 0
        total_signal_waits = 0
        total_startup_times = 0
        turn_types = []
        intersection_types = []

        for i in range(len(path) - 1):
            u, v = path[i], path[i + 1]

            # 获取边的基础信息
            edge_info = None
            if (u, v) in edge_cost_info:
                edge_info = edge_cost_info[(u, v)]
                total_distance += edge_info.get('length', 0)
                total_time += edge_info.get('time', 0)
                if 'energy' in edge_info:
                    total_energy += edge_info['energy']
                if 'carbon' in edge_info:
                    total_carbon += edge_info['carbon']
                if 'comfort' in edge_info:
                    avg_comfort += edge_info['comfort']
                    comfort_count += 1
            else:
                # 回退到基础计算
                min_length = float('inf')
                min_time = float('inf')
                for key in self.G[u][v]:
                    length = self.graph.get_edge_length(u, v, key)
                    time = self.graph.get_edge_weight(u, v, key, 'time')
                    if length < min_length:
                        min_length = length
                        min_time = time
                total_distance += min_length
                total_time += min_time

            # 获取约束信息
            if (u, v) in constraint_info:
                ci = constraint_info[(u, v)]
                total_turn_penalties += ci.get('turn_penalty', 0)
                total_signal_waits += ci.get('signal_wait', 0)
                total_startup_times += ci.get('startup_time', 0)
                turn_types.append(ci.get('turn_type', 'through'))
                intersection_types.append(ci.get('intersection_type', 'unsignalized'))

        coords = self.graph.get_path_coords(path)

        # 计算平均舒适性
        if comfort_count > 0:
            avg_comfort = avg_comfort / comfort_count

        # 构建结果
        result = {
            'path': path,
            'coords': coords,
            'distance_m': round(total_distance, 1),
            'distance_km': round(total_distance / 1000, 2),
            'time_s': round(total_time, 1),
            'time_min': round(total_time / 60, 1),
            'objective': objective.value,
            'mode': mode.value,
        }

        # 添加多目标优化指标
        if mode in [OptimizationMode.MULTI_OBJECTIVE, OptimizationMode.FULL]:
            result.update({
                'energy_mj': round(total_energy, 3),
                'carbon_kg': round(total_carbon, 3),
                'avg_comfort': round(avg_comfort, 3),
            })

        # 添加约束信息
        if mode in [OptimizationMode.WITH_CONSTRAINTS, OptimizationMode.FULL]:
            result.update({
                'turn_penalties_s': round(total_turn_penalties, 1),
                'signal_waits_s': round(total_signal_waits, 1),
                'startup_times_s': round(total_startup_times, 1),
                'total_constraint_s': round(total_turn_penalties + total_signal_waits + total_startup_times, 1),
                'turn_types': list(set(turn_types)),
                'intersection_types': list(set(intersection_types)),
            })

        return result
