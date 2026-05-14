"""
ALT 路径规划算法 (A* + Landmarks + Triangle inequality)

通过预计算地标节点的最短路径距离，利用三角不等式获得比 Haversine
直线距离更紧的启发式下界，从而减少 A* 搜索扩展的节点数。
"""

import heapq
import math
import pickle
import os
from typing import Optional, Dict, List, Tuple

import networkx as nx

LANDMARKS_PATH = os.path.join(
    os.path.dirname(__file__), "..", "..", "data", "processed", "alt_landmarks.pkl"
)


class ALTRouter:
    """ALT 路径规划器 — A* + 地标三角不等式启发式"""

    def __init__(self, graph, num_landmarks: int = 16):
        self.G = graph.G
        self.graph = graph
        self.num_landmarks = num_landmarks

        # landmarks: List[int]  地标节点 ID
        # from_lm: Dict[int, Dict[int, float]]  地标→所有节点的距离
        # to_lm:   Dict[int, Dict[int, float]]  所有节点→地标的距离
        self.landmarks: List[int] = []
        self.from_lm: Dict[int, Dict[int, float]] = {}
        self.to_lm: Dict[int, Dict[int, float]] = {}
        self._from_goal = None  # 当前搜索目标的预计算距离
        self._to_goal = None

        self._load_or_precompute()

    # ------------------------------------------------------------------
    # 预计算
    # ------------------------------------------------------------------

    def _load_or_precompute(self):
        if os.path.exists(LANDMARKS_PATH):
            print(f"[ALT] 加载缓存: {LANDMARKS_PATH}")
            with open(LANDMARKS_PATH, "rb") as f:
                data = pickle.load(f)
            self.landmarks = data["landmarks"]
            self.from_lm = data["from_lm"]
            self.to_lm = data["to_lm"]
            print(f"[ALT] {len(self.landmarks)} 个地标已加载")
        else:
            print("[ALT] 首次启动，开始预计算地标距离...")
            self.landmarks = self._select_landmarks(self.num_landmarks)
            self.from_lm, self.to_lm = self._precompute_distances()
            self._save_cache()
            print(f"[ALT] 预计算完成，已缓存到 {LANDMARKS_PATH}")

    def _select_landmarks(self, num_landmarks: int) -> List[int]:
        """坐标极值法选取地标：取路网四角 + 中心 + 均匀分布的边缘点"""
        nodes = list(self.G.nodes(data=True))

        if len(nodes) <= num_landmarks:
            return [n for n, _ in nodes]

        # 提取坐标
        coords = []
        for nid, data in nodes:
            lat = data.get("y", 0)
            lon = data.get("x", 0)
            coords.append((nid, lat, lon))

        lats = [c[1] for c in coords]
        lons = [c[2] for c in coords]

        min_lat, max_lat = min(lats), max(lats)
        min_lon, max_lon = min(lons), max(lons)

        # 四角 + 中心 + 各边中点 = 9 个关键点，剩余均匀分布在边界
        key_positions = [
            (min_lat, min_lon),  # 西南
            (min_lat, max_lon),  # 东南
            (max_lat, min_lon),  # 西北
            (max_lat, max_lon),  # 东北
            ((min_lat + max_lat) / 2, (min_lon + max_lon) / 2),  # 中心
            (min_lat, (min_lon + max_lon) / 2),  # 南中
            (max_lat, (min_lon + max_lon) / 2),  # 北中
            ((min_lat + max_lat) / 2, min_lon),  # 西中
            ((min_lat + max_lat) / 2, max_lon),  # 东中
        ]

        # 剩余地标均匀分布在对角线上
        remaining = num_landmarks - len(key_positions)
        for i in range(max(0, remaining)):
            t = (i + 1) / (remaining + 1)
            lat = min_lat + t * (max_lat - min_lat)
            lon = min_lon + t * (max_lon - min_lon)
            key_positions.append((lat, lon))

        # 每个目标位置找最近节点
        landmarks = []
        used = set()
        for target_lat, target_lon in key_positions[:num_landmarks]:
            best_node = None
            best_dist = float("inf")
            for nid, lat, lon in coords:
                if nid in used:
                    continue
                d = (lat - target_lat) ** 2 + (lon - target_lon) ** 2
                if d < best_dist:
                    best_dist = d
                    best_node = nid
            if best_node is not None:
                landmarks.append(best_node)
                used.add(best_node)

        print(f"[ALT] 选取 {len(landmarks)} 个地标（坐标极值法）")
        return landmarks

    def _precompute_distances(self) -> Tuple[Dict, Dict]:
        """对每个地标跑单源 Dijkstra，存储正向和反向距离"""
        from_lm: Dict[int, Dict[int, float]] = {}
        to_lm: Dict[int, Dict[int, float]] = {}

        G = self.G
        total = len(self.landmarks)

        for idx, lm in enumerate(self.landmarks):
            print(f"[ALT] 预计算地标 {idx + 1}/{total} (node {lm})...")

            # 正向：地标到所有节点（原始图）
            lengths_fwd = nx.single_source_dijkstra_path_length(
                G, lm, weight=self._edge_weight_fwd
            )
            from_lm[lm] = dict(lengths_fwd)

            # 反向：所有节点到地标（反转图）
            G_rev = G.reverse(copy=False)
            lengths_rev = nx.single_source_dijkstra_path_length(
                G_rev, lm, weight=self._edge_weight_rev
            )
            to_lm[lm] = dict(lengths_rev)

        return from_lm, to_lm

    def _edge_weight_fwd(self, u, v, data):
        """正向边权（时间）"""
        length = data.get("length", 0)
        if length <= 0:
            return 1e9
        speed = self._parse_speed(data.get("maxspeed", None))
        speed_ms = speed * 1000 / 3600
        return length / speed_ms

    def _edge_weight_rev(self, u, v, data):
        """反向边权（反转图中 u→v 对应原始 v→u）"""
        return self._edge_weight_fwd(u, v, data)

    @staticmethod
    def _parse_speed(speed_str) -> float:
        if speed_str is None:
            return 60.0
        if isinstance(speed_str, (int, float)):
            return float(speed_str)
        if isinstance(speed_str, list):
            speed_str = speed_str[0]
        s = str(speed_str).lower().strip()
        if "mph" in s:
            try:
                return float(s.replace("mph", "").strip()) * 1.609
            except ValueError:
                return 60.0
        try:
            return float(s)
        except ValueError:
            return 60.0

    def _save_cache(self):
        os.makedirs(os.path.dirname(LANDMARKS_PATH), exist_ok=True)
        with open(LANDMARKS_PATH, "wb") as f:
            pickle.dump(
                {
                    "landmarks": self.landmarks,
                    "from_lm": self.from_lm,
                    "to_lm": self.to_lm,
                },
                f,
            )

    # ------------------------------------------------------------------
    # 启发式
    # ------------------------------------------------------------------

    def _heuristic(self, node: int, goal: int) -> float:
        """
        ALT 三角不等式启发式。
        当 self._from_goal / self._to_goal 已设置时，goal 侧距离直接
        从预计算数组中读取，避免每节点重复字典查找。
        """
        h = 0.0
        from_lm = self.from_lm
        to_lm = self.to_lm
        from_goal = self._from_goal
        to_goal = self._to_goal

        if from_goal is not None:
            for i, lm in enumerate(self.landmarks):
                fl = from_lm.get(lm)
                if fl is None:
                    continue
                tl = to_lm.get(lm)
                if tl is None:
                    continue
                d_lu = fl.get(node, 0.0)
                diff1 = abs(d_lu - from_goal[i])
                d_ul = tl.get(node, 0.0)
                diff2 = abs(d_ul - to_goal[i])
                if diff1 > h:
                    h = diff1
                if diff2 > h:
                    h = diff2
        else:
            for lm in self.landmarks:
                fl = from_lm.get(lm)
                if fl is None:
                    continue
                tl = to_lm.get(lm)
                if tl is None:
                    continue
                d_lu = fl.get(node, 0.0)
                d_lv = fl.get(goal, 0.0)
                diff1 = abs(d_lu - d_lv)
                d_ul = tl.get(node, 0.0)
                d_vl = tl.get(goal, 0.0)
                diff2 = abs(d_ul - d_vl)
                if diff1 > h:
                    h = diff1
                if diff2 > h:
                    h = diff2

        return h

    # ------------------------------------------------------------------
    # 搜索
    # ------------------------------------------------------------------

    def find_path(
        self, start_node: int, end_node: int, weight_type: str = "time"
    ) -> Optional[dict]:
        if start_node not in self.G or end_node not in self.G:
            return None

        # 预计算 goal 到各地标的距离，存入实例属性（一次查询，全搜索复用）
        self._from_goal = [
            self.from_lm.get(lm, {}).get(end_node, 0.0)
            for lm in self.landmarks
        ]
        self._to_goal = [
            self.to_lm.get(lm, {}).get(end_node, 0.0)
            for lm in self.landmarks
        ]

        counter = 0
        open_set = [(0.0, counter, start_node)]
        came_from: Dict[int, tuple] = {}
        g_score = {start_node: 0.0}

        while open_set:
            _, _, current = heapq.heappop(open_set)

            if current == end_node:
                return self._reconstruct_path(came_from, current)

            current_g = g_score.get(current, float("inf"))

            for neighbor in self.G.neighbors(current):
                best_weight = float("inf")
                best_key = None
                for key in self.G[current][neighbor]:
                    w = self.graph.get_edge_weight(current, neighbor, key, weight_type)
                    if w < best_weight:
                        best_weight = w
                        best_key = key

                if best_weight >= float("inf"):
                    continue

                tentative_g = current_g + best_weight

                if tentative_g < g_score.get(neighbor, float("inf")):
                    came_from[neighbor] = (current, best_key)
                    g_score[neighbor] = tentative_g
                    h = self._heuristic(neighbor, end_node)
                    counter += 1
                    heapq.heappush(open_set, (tentative_g + h, counter, neighbor))

        return None

    def _reconstruct_path(self, came_from: dict, current: int) -> dict:
        path = [current]
        edge_path = []
        while current in came_from:
            previous, key = came_from[current]
            edge_path.append((previous, current, key))
            current = previous
            path.append(current)
        path.reverse()
        edge_path.reverse()

        total_distance = 0.0
        total_time = 0.0
        for u, v, key in edge_path:
            total_distance += self.graph.get_edge_length(u, v, key)
            total_time += self.graph.get_edge_weight(u, v, key, "time")

        coords = self.graph.get_path_edge_coords(edge_path)

        return {
            "path": path,
            "coords": coords,
            "distance_m": round(total_distance, 1),
            "distance_km": round(total_distance / 1000.0, 2),
            "time_s": round(total_time, 1),
            "time_min": round(total_time / 60.0, 1),
        }
