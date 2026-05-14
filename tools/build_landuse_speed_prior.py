"""
OSM 用地性质 → 道路速度先验提取

参考: Acharya et al. (2024) 使用 XGBoost + OSM + 用地性质 + 人口数据预测拥堵速度
      Tang et al. (2025) 用 OSM 特征推断未覆盖路段速度等级

输入:
  OSM landuse 多边形 (通过 osmnx 在线下载 D12 区域)
  OSM 路网图 (data/processed/road_graph.pkl)
  PeMS 传感器元数据 (TGCN/data/d12_data/data/d12_text_meta_2023_12_05.txt)
  PeMS 5min 速度数据 (TGCN/data/d12_data/data/d12_text_station_5min_*.txt.gz)

输出:
  data/processed/landuse_polygons.pkl  — GeoDataFrame of OSM landuse polygons
  data/processed/edge_landuse_map.pkl  — Dict[(u,v,key) -> landuse_type or None]
  data/processed/landuse_speed_prior.pkl — 2D (road_type, landuse) -> speed stats
"""
import os
import sys
import pickle
import gzip
import time
from collections import defaultdict
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

D12_BBOX = dict(north=33.95, south=33.38, east=-117.41, west=-118.10)

OSM_LANDUSE_CATEGORIES = {
    "commercial": "commercial",
    "retail": "commercial",
    "industrial": "industrial",
    "residential": "residential",
    "farmland": "rural",
    "farmyard": "rural",
    "forest": "rural",
    "grass": "rural",
    "meadow": "rural",
    "orchard": "rural",
    "vineyard": "rural",
    "greenfield": "rural",
    "recreation_ground": "recreation",
    "park": "recreation",
    "village_green": "recreation",
    "military": "institutional",
    "education": "institutional",
    "hospital": "institutional",
    "religious": "institutional",
    "cemetery": "institutional",
    "construction": "construction",
    "brownfield": "construction",
    "quarry": "industrial",
}


def normalize_landuse(raw_tag):
    """Map raw OSM landuse tag to one of 7 coarse categories."""
    if raw_tag is None:
        return None
    raw = str(raw_tag).lower().strip()
    return OSM_LANDUSE_CATEGORIES.get(raw, "other")


def extract_landuse_from_local_pbf(pbf_path, bbox):
    """Extract landuse polygons from a local OSM PBF/XZ file using osmium.

    Uses osmium's NodeLocationsForWays handler to efficiently store only
    node locations referenced by landuse-tagged ways (not all 50M+ nodes).
    """
    import osmium
    from shapely.geometry import Polygon

    class LanduseWayCollector(osmium.SimpleHandler):
        """First pass: collect landuse way IDs and their node references."""
        def __init__(self, bbox):
            super().__init__()
            self.bbox = bbox
            self.ways = []  # (landuse_tag, [node_refs])
            self.needed_nodes = set()

        def way(self, w):
            landuse = w.tags.get("landuse")
            if not landuse:
                return
            refs = [nr.ref for nr in w.nodes]
            if len(refs) >= 3:
                self.ways.append((landuse, refs))
                self.needed_nodes.update(refs)

    print(f"  Pass 1/2: scanning landuse ways in {os.path.basename(pbf_path)}...")
    collector = LanduseWayCollector(bbox)
    collector.apply_file(pbf_path, locations=True)
    print(f"    Found {len(collector.ways)} landuse ways "
          f"referencing {len(collector.needed_nodes):,} unique nodes")

    # Second pass: extract coordinates for needed nodes from the
    # osmium-internal location store (populated by locations=True)
    needed = collector.needed_nodes
    node_coords = {}

    class NodeExtractor(osmium.SimpleHandler):
        def __init__(self, needed, bbox):
            super().__init__()
            self.needed = needed
            self.bbox = bbox
            self.found = 0

        def node(self, n):
            if n.id in self.needed:
                node_coords[n.id] = (n.location.lon, n.location.lat)
                self.found += 1

    print(f"  Pass 2/2: extracting coordinates for needed nodes...")
    extractor = NodeExtractor(needed, bbox)
    extractor.apply_file(pbf_path)
    print(f"    Extracted {extractor.found:,} / {len(needed):,} node coordinates")

    # Build polygons from way node references
    polygons = []
    landuse_tags = []
    for landuse, refs in collector.ways:
        coords = []
        for ref in refs:
            if ref in node_coords:
                coords.append(node_coords[ref])
        if len(coords) >= 3:
            if coords[0] != coords[-1]:
                coords.append(coords[0])
            try:
                poly = Polygon(coords)
                if poly.is_valid and poly.area > 0:
                    polygons.append(poly)
                    landuse_tags.append(landuse)
            except Exception:
                pass

    import geopandas as gpd
    gdf = gpd.GeoDataFrame(
        {"landuse": landuse_tags, "geometry": polygons}, crs="EPSG:4326"
    )
    gdf["landuse_coarse"] = gdf["landuse"].apply(normalize_landuse)
    gdf = gdf[gdf["landuse_coarse"].notna()].copy()
    print(f"  Extracted {len(gdf)} valid landuse polygons")
    return gdf


def download_landuse_polygons(bbox, cache_path):
    """Download OSM landuse polygons via osmnx, falling back to local PBF."""
    import osmnx as ox
    from shapely.geometry import Polygon, MultiPolygon

    print("[1/5] Downloading OSM landuse polygons via osmnx...")
    tags = {"landuse": True}
    gdf = None

    # Try Overpass API first
    try:
        gdf = ox.features_from_bbox(
            bbox=(bbox["west"], bbox["south"], bbox["east"], bbox["north"]), tags=tags
        )
    except Exception as e:
        print(f"  Overpass download failed: {e}")
        print("  Falling back to local PBF/XZ extraction...")

        pbf_candidates = [
            "data/osm/planet_-118.576_33.424_ba6504c4.osm.pbf",
            "data/osm/planet_-118.579_33.669_3838a635.osm.xz",
        ]
        for pbf_path in pbf_candidates:
            if os.path.exists(pbf_path):
                try:
                    gdf = extract_landuse_from_local_pbf(pbf_path, bbox)
                    break
                except Exception as e2:
                    print(f"  Failed to extract from {os.path.basename(pbf_path)}: {e2}")
        else:
            raise RuntimeError(
                "No landuse data source available. "
                "Tried Overpass API and local PBF/XZ files."
            )

    if gdf is None:
        raise RuntimeError("Failed to obtain landuse data from any source.")

    # Filter to only Polygon/MultiPolygon geometries
    gdf = gdf[gdf.geometry.apply(lambda g: isinstance(g, (Polygon, MultiPolygon)))]

    # Normalize landuse values
    gdf["landuse_coarse"] = gdf["landuse"].apply(normalize_landuse)
    gdf = gdf[gdf["landuse_coarse"].notna()].copy()

    os.makedirs(os.path.dirname(cache_path), exist_ok=True)
    with open(cache_path, "wb") as f:
        pickle.dump(gdf, f)
    print(f"  Saved {len(gdf)} landuse polygons -> {cache_path}")
    return gdf


def load_or_download_landuse(cache_path="data/processed/landuse_polygons.pkl"):
    """Load cached landuse polygons, or download if missing."""
    if os.path.exists(cache_path):
        print(f"[1/5] Loading cached landuse polygons from {cache_path}")
        try:
            with open(cache_path, "rb") as f:
                return pickle.load(f)
        except Exception as e:
            print(f"  Failed to load cache: {e}, re-downloading...")
    return download_landuse_polygons(D12_BBOX, cache_path)


def build_edge_landuse_map(road_graph, landuse_gdf,
                           cache_path="data/processed/edge_landuse_map.pkl"):
    """Map each road edge to its landuse type via point-in-polygon spatial join."""
    from shapely.geometry import Point
    from shapely import STRtree

    print("[2/5] Building edge -> landuse spatial join...")

    landuse_geoms = landuse_gdf.geometry.values
    landuse_types = landuse_gdf["landuse_coarse"].values
    tree = STRtree(landuse_geoms)

    G = road_graph.G
    edge_landuse = {}
    total = G.number_of_edges()
    assigned = 0
    report_every = max(1, total // 10)

    for i, (u, v, key, data) in enumerate(G.edges(keys=True, data=True)):
        # Get edge midpoint
        if "geometry" in data and data["geometry"] is not None:
            midpoint = data["geometry"].interpolate(0.5, normalized=True)
        else:
            u_pt = Point(G.nodes[u].get("x", 0), G.nodes[u].get("y", 0))
            v_pt = Point(G.nodes[v].get("x", 0), G.nodes[v].get("y", 0))
            midpoint = Point(
                (u_pt.x + v_pt.x) / 2,
                (u_pt.y + v_pt.y) / 2,
            )

        landuse_type = None
        candidate_idxs = tree.query(midpoint, predicate="intersects")
        if len(candidate_idxs) > 0:
            landuse_type = landuse_types[candidate_idxs[0]]
            assigned += 1

        edge_landuse[(u, v, key)] = landuse_type

        if (i + 1) % report_every == 0:
            pct = (i + 1) / total * 100
            print(f"  {i+1}/{total} edges ({pct:.0f}%), {assigned} assigned landuse")

    os.makedirs(os.path.dirname(cache_path), exist_ok=True)
    with open(cache_path, "wb") as f:
        pickle.dump(edge_landuse, f)
    print(f"  Coverage: {assigned}/{total} ({assigned/total*100:.1f}%)")
    return edge_landuse


def parse_meta(meta_path):
    """Parse PeMS metadata: sensor_id -> {fwy, dir, type, lat, lon}."""
    sensors = {}
    with open(meta_path, encoding="utf-8") as f:
        f.readline()  # skip header
        for line in f:
            if not line.strip():
                continue
            parts = line.strip().split("\t")
            if len(parts) < 14:
                continue
            sid = int(parts[0])
            sensors[sid] = {
                "fwy": parts[1], "dir": parts[2],
                "type": parts[11],
                "lat": float(parts[8]) if parts[8] else None,
                "lon": float(parts[9]) if parts[9] else None,
            }
    return sensors


def compute_speed_stats(speeds):
    """Compute speed statistics from an array of speed values."""
    arr = np.array(speeds)
    return {
        "count": len(arr),
        "mean": round(float(np.mean(arr)), 1),
        "std": round(float(np.std(arr)), 1),
        "p5": round(float(np.percentile(arr, 5)), 1),
        "p25": round(float(np.percentile(arr, 25)), 1),
        "p50": round(float(np.percentile(arr, 50)), 1),
        "p75": round(float(np.percentile(arr, 75)), 1),
        "p95": round(float(np.percentile(arr, 95)), 1),
    }


def build_landuse_speed_prior(
    road_graph, edge_landuse, meta,
    data_dir="TGCN/data/d12_data/data",
    cache_path="data/processed/landuse_speed_prior.pkl",
):
    """Compute speed statistics grouped by (OSM road_type, landuse_type)."""
    print("[3/5] Loading PeMS speed data...")

    G = road_graph.G
    data_files = sorted([
        f for f in os.listdir(data_dir)
        if f.startswith("d12_text_station_5min_") and f.endswith(".txt.gz")
    ])

    sensor_speeds = defaultdict(list)
    for fname in data_files:
        fpath = os.path.join(data_dir, fname)
        try:
            with gzip.open(fpath, "rt", encoding="utf-8", errors="replace") as f:
                for line in f:
                    parts = line.strip().split(",")
                    if len(parts) < 10:
                        continue
                    try:
                        sensor_id = int(parts[1])
                    except (ValueError, IndexError):
                        continue
                    if sensor_id not in meta:
                        continue

                    lane_data = parts[6:]
                    speeds, weights = [], []
                    for j in range(0, len(lane_data) - 4, 5):
                        try:
                            samples = float(lane_data[j]) if lane_data[j] else 0
                            speed = float(lane_data[j+4]) if lane_data[j+4] else 0
                        except (ValueError, IndexError):
                            continue
                        if samples > 0 and speed > 0:
                            speeds.append(speed)
                            weights.append(samples)
                    if speeds:
                        avg = np.average(speeds, weights=weights) if weights else np.mean(speeds)
                        sensor_speeds[sensor_id].append(avg)
        except Exception as e:
            print(f"  [WARN] {fname}: {e}")

    print("[4/5] Computing per-(road_type, landuse) speed statistics...")

    group_speeds = defaultdict(list)

    edge_sensor_map_path = "data/processed/edge_sensor_map.pkl"
    if os.path.exists(edge_sensor_map_path):
        with open(edge_sensor_map_path, "rb") as f:
            raw = pickle.load(f)
        # edge_sensor_map.pkl wraps the mapping under "edge_to_sensors"
        edge_sensor_map = raw.get("edge_to_sensors", raw)

        for (u, v, key), nearest_list in edge_sensor_map.items():
            highway = G.edges[u, v, key].get("highway", "unclassified")
            if isinstance(highway, list):
                highway = highway[0]
            landuse = edge_landuse.get((u, v, key))

            for sid, dist in nearest_list:
                if dist <= 0.5 and sid in sensor_speeds:
                    key_2d = (str(highway), landuse or "unknown")
                    group_speeds[key_2d].extend(sensor_speeds[sid])
                    key_1d = (str(highway), "*")
                    group_speeds[key_1d].extend(sensor_speeds[sid])

    by_road_landuse = {}
    for key, speeds in sorted(group_speeds.items()):
        if len(speeds) >= 30:
            by_road_landuse[key] = compute_speed_stats(speeds)

    by_road_only = {}
    for key, stats in by_road_landuse.items():
        if key[1] == "*":
            by_road_only[key[0]] = stats

    landuse_types = sorted(set(k[1] for k in by_road_landuse.keys() if k[1] != "*"))

    prior = {
        "by_road_landuse": by_road_landuse,
        "by_road_only": by_road_only,
        "landuse_types": landuse_types,
    }

    os.makedirs(os.path.dirname(cache_path), exist_ok=True)
    with open(cache_path, "wb") as f:
        pickle.dump(prior, f)

    print("\n[5/5] Landuse Speed Prior Summary:")
    print(f"  Landuse types: {landuse_types}")
    print(f"  (road_type, landuse) groups: {len(by_road_landuse)}")
    for key, stats in sorted(by_road_landuse.items()):
        if key[1] == "*":
            continue
        print(f"  {str(key[0]):<20} x {str(key[1]):<15} p50={stats['p50']:>6.1f} km/h  (n={stats['count']:>8,})")

    print(f"\n  Saved -> {cache_path}")
    return prior


def main():
    t0 = time.time()
    print("=" * 60)
    print("  OSM Landuse -> Road Speed Prior")
    print("  Ref: Acharya et al. (2024)")
    print("=" * 60)

    # 1. Load landuse polygons
    landuse_gdf = load_or_download_landuse()

    # 2. Load road graph
    print("\n[2/5] Loading road graph...")
    graph_path = "data/processed/road_graph.pkl"
    if not os.path.exists(graph_path):
        print(f"  ERROR: {graph_path} not found. Run RoadGraph.build_from_osm() first.")
        sys.exit(1)

    from backend.graph.road_graph import RoadGraph
    road_graph = RoadGraph.build_from_osm()

    # 3. Build edge->landuse map
    edge_landuse = build_edge_landuse_map(road_graph, landuse_gdf)

    # 4-5. Load PeMS meta and compute stats
    meta_path = os.path.join("TGCN/data/d12_data/data", "d12_text_meta_2023_12_05.txt")
    if not os.path.exists(meta_path):
        print(f"  WARNING: {meta_path} not found, skipping PeMS join. Will only save edge_landuse_map.")
        return

    meta = parse_meta(meta_path)
    prior = build_landuse_speed_prior(road_graph, edge_landuse, meta)

    elapsed = time.time() - t0
    print(f"\n  Total time: {elapsed:.1f}s")


if __name__ == "__main__":
    main()
