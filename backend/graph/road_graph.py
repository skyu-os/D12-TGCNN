"""
路网图构建 - 基于 OSMNX 下载的数据构建可查询的路网图
"""

import osmnx as ox
import networkx as nx
import pickle
import os
import numpy as np

# PeMS D12 (Orange County) 配置 - bbox 精确边界
BBOX = {
    "north": 33.95,
    "south": 33.38,
    "east": -117.41,
    "west": -118.10,
}

DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "data")
OSM_RAW_PATH = os.path.join(DATA_DIR, "osm", "pems_d12_graph.graphml")
PROCESSED_PATH = os.path.join(DATA_DIR, "processed", "road_graph.pkl")
SENSOR_META_PATH = os.path.join(DATA_DIR, "osm", "d12_text_meta_2023_12_05.txt")
LOCAL_PBF_PATH = os.path.join(
    DATA_DIR, "osm", "planet_-118.576_33.424_ba6504c4.osm.pbf"
)
LOCAL_OSM_XZ_PATH = os.path.join(
    DATA_DIR, "osm", "planet_-118.579_33.669_3838a635.osm.xz"
)
LOCAL_OSM_EXTRACTED_PATH = os.path.join(DATA_DIR, "osm", "d12_drive.osm")


class RoadGraph:
    """路网图封装"""

    _cached_instance = None

    def __init__(self, graph=None):
        self.G = graph
        self.node_to_osm = {}  # 内部节点ID -> OSM节点ID
        self.osm_to_node = {}  # OSM节点ID -> 内部节点ID
        self._nearest_node_tree = None
        self._nearest_node_ids = None
        self.landuse_prior = None
        self.edge_landuse = None
        self._speed_cache = {}  # (highway, landuse) -> speed

    def _load_landuse_data(self):
        """Load landuse speed prior and edge->landuse map if available."""
        self.landuse_prior = None
        self.edge_landuse = None

        prior_path = os.path.join(DATA_DIR, "processed", "landuse_speed_prior.pkl")
        if os.path.exists(prior_path):
            try:
                with open(prior_path, "rb") as f:
                    self.landuse_prior = pickle.load(f)
            except Exception:
                pass

        landuse_path = os.path.join(DATA_DIR, "processed", "edge_landuse_map.pkl")
        if os.path.exists(landuse_path):
            try:
                with open(landuse_path, "rb") as f:
                    self.edge_landuse = pickle.load(f)
            except Exception:
                pass

    @classmethod
    def build_from_osm(cls, force_download=False):
        """从 OSM 构建路网图（支持多种格式）"""
        if not force_download and cls._cached_instance is not None:
            return cls._cached_instance

        # 1. 优先加载 pickle 缓存
        if not force_download and os.path.exists(PROCESSED_PATH):
            print(f"[OK] 加载缓存路网: {PROCESSED_PATH}")
            with open(PROCESSED_PATH, "rb") as f:
                G = pickle.load(f)
            print(f"[OK] 路网: {G.number_of_nodes()} 节点, {G.number_of_edges()} 边")
            cls._cached_instance = cls(G)
            cls._cached_instance._load_landuse_data()
            return cls._cached_instance

        # 2. 从预提取的 OSM XML 文件加载（由 tools/extract_d12_from_xz.py 生成）
        if os.path.exists(LOCAL_OSM_EXTRACTED_PATH):
            print(f"[INFO] 从提取的 OSM 文件加载: {LOCAL_OSM_EXTRACTED_PATH}")
            try:
                G = ox.graph_from_xml(
                    LOCAL_OSM_EXTRACTED_PATH, simplify=True, retain_all=False
                )
                print(
                    f"[OK] OSM 加载完成: {G.number_of_nodes()} 节点, {G.number_of_edges()} 边"
                )
                # 保存缓存
                os.makedirs(os.path.dirname(PROCESSED_PATH), exist_ok=True)
                with open(PROCESSED_PATH, "wb") as f:
                    pickle.dump(G, f)
                print(f"[OK] 已保存缓存: {PROCESSED_PATH}")
                cls._cached_instance = cls(G)
                cls._cached_instance._load_landuse_data()
                return cls._cached_instance
            except Exception as e:
                print(f"[WARN] 从提取的 OSM 文件加载失败: {e}")

        # 3. 在线下载（需要网络连接）
        print(f"[INFO] 正在从 OSM 下载路网 (bbox: {BBOX})...")
        try:
            bbox = (
                BBOX["west"],
                BBOX["south"],
                BBOX["east"],
                BBOX["north"],
            )
            G = ox.graph_from_bbox(
                bbox=bbox,
                network_type="drive",
                simplify=True,
            )
            print(
                f"[OK] 下载完成: {G.number_of_nodes()} 节点, {G.number_of_edges()} 边"
            )
            os.makedirs(os.path.dirname(PROCESSED_PATH), exist_ok=True)
            ox.save_graphml(G, OSM_RAW_PATH)
            with open(PROCESSED_PATH, "wb") as f:
                pickle.dump(G, f)
            print(f"[OK] 已保存: {PROCESSED_PATH}")
            cls._cached_instance = cls(G)
            cls._cached_instance._load_landuse_data()
            return cls._cached_instance
        except Exception as e:
            print(f"[ERROR] 下载失败: {e}")
            print("\n[TIPS] 建议:")
            print("  1. 检查网络连接")
            print("  2. 运行 python tools/extract_d12_from_xz.py 从本地 XZ 文件提取路网")
            raise

    def get_nearest_node(self, lat, lon):
        """找到距离给定坐标最近的路网节点"""
        if self._nearest_node_tree is None:
            from scipy.spatial import cKDTree

            self._nearest_node_ids = list(self.G.nodes)
            coords = np.array(
                [[self.G.nodes[node].get("y", 0), self.G.nodes[node].get("x", 0)] for node in self._nearest_node_ids],
                dtype=np.float64,
            )
            self._nearest_node_tree = cKDTree(coords)

        _, idx = self._nearest_node_tree.query([lat, lon], k=1)
        return self._nearest_node_ids[int(idx)]

    def get_edge_length(self, u, v, key=0):
        """获取边的长度（米）"""
        data = self.G.edges[u, v, key]
        return data.get("length", 0)

    def get_edge_speed(self, u, v, key=0):
        """获取边的限速（km/h），无数据则返回默认值"""
        data = self.G.edges[u, v, key]
        # OSM 的 maxspeed 通常是字符串如 "55 mph"
        speed = data.get("maxspeed", None)
        if speed:
            return self._parse_speed(speed)

        highway = data.get("highway")

        # Look up landuse for this edge if prior is loaded
        landuse_type = None
        if self.landuse_prior and self.edge_landuse:
            landuse_type = self.edge_landuse.get((u, v, key))

        return self._default_speed_by_highway(highway, landuse_type)

    def _default_speed_by_highway(self, highway, landuse_type=None):
        """Return default speed (km/h) for a highway type, optionally adjusted by landuse."""
        if isinstance(highway, (list, tuple, set)):
            highway = next(iter(highway), None)

        # Try 2D lookup if landuse prior is available
        if landuse_type and self.landuse_prior:
            key = (str(highway), landuse_type)
            if key in self.landuse_prior.get("by_road_landuse", {}):
                return self.landuse_prior["by_road_landuse"][key]["p50"]

        # Fall back to 1D table
        return {
            "motorway": 105.0,
            "motorway_link": 55.0,
            "trunk": 90.0,
            "trunk_link": 50.0,
            "primary": 65.0,
            "primary_link": 45.0,
            "secondary": 55.0,
            "secondary_link": 40.0,
            "tertiary": 45.0,
            "tertiary_link": 35.0,
            "residential": 35.0,
            "unclassified": 35.0,
            "service": 20.0,
            "living_street": 15.0,
        }.get(highway, 35.0)

    def get_edge_weight(self, u, v, key=0, weight_type="time"):
        """
        获取边权重
        weight_type: 'distance' | 'time'
        """
        length = self.get_edge_length(u, v, key)
        if weight_type == "distance":
            return length

        # time = length / speed
        speed = self.get_edge_speed(u, v, key)
        speed_ms = speed * 1000 / 3600
        return length / speed_ms if speed_ms > 0 else float("inf")

    def get_path_coords(self, path):
        """将节点路径转换为经纬度坐标列表"""
        coords = []
        for node in path:
            data = self.G.nodes[node]
            coords.append((data.get("y", 0), data.get("x", 0)))  # (lat, lon)
        return coords

    def get_edge_coords(self, u, v, key=0):
        """获取有向边的真实几何坐标，返回 [(lat, lon), ...]。"""
        data = self.G.edges[u, v, key]
        if "geometry" in data:
            try:
                return [(lat, lon) for lon, lat in data["geometry"].coords]
            except Exception:
                pass

        start = self.G.nodes[u]
        end = self.G.nodes[v]
        return [
            (start.get("y", 0), start.get("x", 0)),
            (end.get("y", 0), end.get("x", 0)),
        ]

    def get_path_edge_coords(self, edge_path):
        """按有向边序列拼接真实 geometry，避免节点直连导致偏离路网。"""
        coords = []
        for u, v, key in edge_path:
            edge_coords = self.get_edge_coords(u, v, key)
            if coords and edge_coords and coords[-1] == edge_coords[0]:
                coords.extend(edge_coords[1:])
            else:
                coords.extend(edge_coords)
        return coords

    def get_stats(self):
        """返回图统计信息"""
        stats = {
            "nodes": self.G.number_of_nodes(),
            "edges": self.G.number_of_edges(),
        }
        if self.G.number_of_edges() > 0:
            lengths = [d.get("length", 0) for _, _, d in self.G.edges(data=True)]
            stats["avg_length"] = sum(lengths) / len(lengths)
            stats["total_length_km"] = sum(lengths) / 1000
        return stats

    @staticmethod
    def _parse_speed(speed_str):
        """解析速度字符串，如 '55 mph' -> km/h，支持列表取第一个值"""
        if isinstance(speed_str, (int, float)):
            return float(speed_str)
        # OSM maxspeed 可能是列表如 ['40 mph', '45 mph']，取第一个
        if isinstance(speed_str, list):
            speed_str = speed_str[0]
        speed_str = str(speed_str).lower().strip()
        # 去除方括号（字符串化的列表如 "['40 mph', '45 mph']"）
        if speed_str.startswith("["):
            import ast

            try:
                vals = ast.literal_eval(speed_str)
                if isinstance(vals, list) and vals:
                    speed_str = str(vals[0]).lower().strip()
            except Exception:
                speed_str = speed_str.strip("[]'\"")
        if "mph" in speed_str:
            try:
                return float(speed_str.replace("mph", "").strip()) * 1.609
            except ValueError:
                return 60
        elif "km/h" in speed_str or "kmph" in speed_str:
            try:
                return float(speed_str.replace("km/h", "").replace("kmph", "").strip())
            except ValueError:
                return 60
        try:
            return float(speed_str)
        except ValueError:
            return 60
