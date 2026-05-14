"""
增强版路由服务 - 统一路径规划接口
支持多目标优化和路口约束
"""

from backend.graph.road_graph import RoadGraph
from backend.routing.enhanced_astar import EnhancedAStarRouter
from backend.routing.multi_objective_optimizer import (
    MultiObjectiveOptimizer,
    OptimizationObjective,
    create_optimizer
)
from backend.routing.intersection_constraints import (
    IntersectionConstraints,
    create_default_constraints
)


class EnhancedRouterService:
    """增强版路径规划服务（单例）"""

    _instance = None
    _road_graph = None
    _enhanced_astar = None
    _constraints = None

    @classmethod
    def get_instance(cls, vehicle_type: str = 'gasoline'):
        if cls._instance is None:
            cls._instance = cls()
            cls._road_graph = RoadGraph.build_from_osm()
            cls._constraints = create_default_constraints(vehicle_type)
            # 默认使用普通燃油车优化器
            optimizer = create_optimizer(vehicle_type)
            cls._enhanced_astar = EnhancedAStarRouter(
                cls._road_graph, optimizer, cls._constraints
            )
        return cls._instance

    def find_route(
        self,
        start_lat: float,
        start_lon: float,
        end_lat: float,
        end_lon: float,
        objective: str = "time",
        mode: str = "standard",
        vehicle_type: str = "gasoline",
        hour: int = 12,
    ) -> dict:
        """
        根据经纬度查找路径

        Args:
            start_lat: 起点纬度
            start_lon: 起点经度
            end_lat: 终点纬度
            end_lon: 终点经度
            objective: 优化目标 ('time' | 'distance' | 'energy' | 'carbon' | 'comfort' | 'balanced')
            mode: 优化模式 ('standard' | 'multi_objective' | 'with_constraints' | 'full')
            vehicle_type: 车辆类型 ('gasoline' | 'diesel' | 'electric' | 'hybrid')
            hour: 小时数 (0-23)，用于判断时段

        Returns:
            {
                'success': bool,
                'route': { path, coords, distance_m, distance_km, time_s, time_min, ... },
                'error': str (if failed)
            }
        """
        try:
            start_node = self._road_graph.get_nearest_node(start_lat, start_lon)
            end_node = self._road_graph.get_nearest_node(end_lat, end_lon)

            print(f"[DEBUG] 起点节点: {start_node}, 终点节点: {end_node}")

            # 根据车辆类型创建优化器
            if vehicle_type != 'gasoline':
                optimizer = create_optimizer(vehicle_type)
                router = EnhancedAStarRouter(
                    self._road_graph, optimizer, self._constraints
                )
            else:
                # 使用默认优化器
                router = self._enhanced_astar

            # 根据小时确定时段
            time_of_day = self._constraints.get_time_of_day(hour)

            result = router.find_path(
                start_node, end_node, objective, mode, time_of_day
            )

            if result is None:
                return {"success": False, "error": "路径不可达"}

            return {"success": True, "route": result}
        except Exception as e:
            print(f"[ERROR] 增强版路径规划异常: {e}")
            import traceback
            traceback.print_exc()
            return {"success": False, "error": str(e)}

    def get_objective_descriptions(self) -> dict:
        """获取所有优化目标的描述"""
        return {
            'time': '最短时间优先',
            'distance': '最短距离优先',
            'energy': '最低能耗优先',
            'carbon': '最低碳排放优先',
            'comfort': '道路舒适性优先',
            'balanced': '平衡模式（综合优化）',
        }

    def get_mode_descriptions(self) -> dict:
        """获取所有优化模式的描述"""
        return {
            'standard': '标准模式（仅时间/距离）',
            'multi_objective': '多目标优化模式',
            'with_constraints': '路口约束模式',
            'full': '完整模式（多目标+约束）',
        }

    def get_vehicle_types(self) -> list:
        """获取支持的车辆类型"""
        return ['gasoline', 'diesel', 'electric', 'hybrid']
