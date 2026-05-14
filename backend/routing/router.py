"""
路由服务 - 统一路径规划接口
"""

from backend.graph.road_graph import RoadGraph
from backend.routing.alt import ALTRouter
from backend.routing.astar import AStarRouter
from backend.routing.dijkstra import DijkstraRouter
from backend.routing.greedy import GreedyRouter


class RouterService:
    """路径规划服务（单例）"""

    _instance = None
    _road_graph = None
    _astar = None
    _dijkstra = None
    _greedy = None
    _alt = None

    @classmethod
    def get_instance(cls):
        if cls._instance is None:
            cls._instance = cls()
            cls._road_graph = RoadGraph.build_from_osm()
        return cls._instance

    def find_route(
        self,
        start_lat: float,
        start_lon: float,
        end_lat: float,
        end_lon: float,
        weight_type: str = "time",
        algorithm: str = "astar",
    ) -> dict:
        """
        根据经纬度查找路径

        Args:
            algorithm: 'astar' | 'dijkstra' | 'greedy'

        Returns:
            {
                'success': bool,
                'route': { path, coords, distance_m, distance_km, time_s, time_min },
                'error': str (if failed)
            }
        """
        try:
            start_node = self._road_graph.get_nearest_node(start_lat, start_lon)
            end_node = self._road_graph.get_nearest_node(end_lat, end_lon)

            # 根据算法选择路由器
            router = self._get_router(algorithm)
            if router is None:
                return {"success": False, "error": f"不支持的算法: {algorithm}"}

            result = router.find_path(start_node, end_node, weight_type)

            if result is None:
                return {"success": False, "error": "路径不可达"}

            return {"success": True, "route": result}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def _get_router(self, algorithm: str):
        """获取指定算法的路由器"""
        if algorithm == "astar":
            if self.__class__._astar is None:
                self.__class__._astar = AStarRouter(self.__class__._road_graph)
            return self.__class__._astar
        if algorithm == "dijkstra":
            if self.__class__._dijkstra is None:
                self.__class__._dijkstra = DijkstraRouter(self.__class__._road_graph)
            return self.__class__._dijkstra
        if algorithm == "greedy":
            if self.__class__._greedy is None:
                self.__class__._greedy = GreedyRouter(self.__class__._road_graph)
            return self.__class__._greedy
        if algorithm == "alt":
            if self.__class__._alt is None:
                self.__class__._alt = ALTRouter(self.__class__._road_graph)
            return self.__class__._alt
        return None
