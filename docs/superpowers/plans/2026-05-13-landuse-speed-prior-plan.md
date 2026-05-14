# Land Use-Aware Road Speed Prior Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the 1D `road_type -> speed` default mapping with a 2D `(road_type, landuse) -> speed` prior, backed by OSM landuse polygon extraction and PeMS speed statistics.

**Architecture:** New script `tools/build_landuse_speed_prior.py` downloads OSM landuse polygons via osmnx, maps each road edge to its landuse type via Shapely STRtree spatial join, computes per-group speed statistics from PeMS data, and exports `landuse_speed_prior.pkl`. `road_graph.py` loads this prior and uses it in `_default_speed_by_highway()` when available, falling back to the existing 1D table.

**Tech Stack:** osmnx, shapely, geopandas, pickle, numpy

---

## File Structure

| File | Action | Responsibility |
|------|--------|----------------|
| `tools/build_landuse_speed_prior.py` | Create | Download landuse, spatial join, group stats, export |
| `backend/graph/road_graph.py:130-160` | Modify | Load landuse prior, add 2D speed lookup |
| `tests/test_landuse_speed_prior.py` | Create | Unit tests for landuse mapping and speed lookup |

---

### Task 1: Create `tools/build_landuse_speed_prior.py` — Landuse download and spatial join

**Files:**
- Create: `tools/build_landuse_speed_prior.py`
- Test: `tests/test_landuse_speed_prior.py`

- [ ] **Step 1: Write failing test for landuse download + spatial join**

```python
# tests/test_landuse_speed_prior.py
import os
import pickle
import pytest
import numpy as np

# Skip if no network or in CI
pytestmark = pytest.mark.slow

def test_build_landuse_speed_prior_output_structure():
    """Test that the output file has the expected structure."""
    prior_path = "data/processed/landuse_speed_prior.pkl"
    if not os.path.exists(prior_path):
        pytest.skip("landuse_speed_prior.pkl not built yet — run tools/build_landuse_speed_prior.py first")
    
    with open(prior_path, "rb") as f:
        prior = pickle.load(f)
    
    assert "by_road_landuse" in prior
    assert "by_road_only" in prior
    assert "landuse_types" in prior
    
    # Each (road_type, landuse) key should have required stats
    for key, stats in prior["by_road_landuse"].items():
        assert isinstance(key, tuple) and len(key) == 2
        for field in ["mean", "std", "p5", "p25", "p50", "p75", "p95", "count"]:
            assert field in stats, f"Missing {field} in {key}"
        assert stats["count"] > 0


def test_landuse_speed_prior_values_plausible():
    """Speed values should be in reasonable range (10-130 km/h)."""
    prior_path = "data/processed/landuse_speed_prior.pkl"
    if not os.path.exists(prior_path):
        pytest.skip("landuse_speed_prior.pkl not built yet")
    
    with open(prior_path, "rb") as f:
        prior = pickle.load(f)
    
    for key, stats in prior["by_road_landuse"].items():
        assert 10 <= stats["p50"] <= 130, f"Unreasonable p50={stats['p50']} for {key}"
        assert stats["p5"] <= stats["p50"] <= stats["p95"], f"Percentile order wrong for {key}"


def test_landuse_edge_map_coverage():
    """At least some edges should have landuse assigned."""
    edge_map_path = "data/processed/edge_landuse_map.pkl"
    if not os.path.exists(edge_map_path):
        pytest.skip("edge_landuse_map.pkl not built yet")
    
    with open(edge_map_path, "rb") as f:
        edge_map = pickle.load(f)
    
    total = len(edge_map)
    assigned = sum(1 for v in edge_map.values() if v is not None)
    coverage = assigned / total if total > 0 else 0
    # Even 5% coverage is useful — OSM landuse is sparse
    assert coverage > 0.01, f"Landuse coverage too low: {coverage:.2%}"
    print(f"Landuse coverage: {coverage:.1%} ({assigned}/{total} edges)")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_landuse_speed_prior.py -v`
Expected: All tests SKIP (files don't exist yet)

- [ ] **Step 3: Write `tools/build_landuse_speed_prior.py`**

```python
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


def download_landuse_polygons(bbox, cache_path):
    """Download OSM landuse polygons for bbox via osmnx. Returns GeoDataFrame."""
    import osmnx as ox
    print("[1/5] Downloading OSM landuse polygons via osmnx...")
    tags = {"landuse": True}
    try:
        gdf = ox.geometries_from_bbox(
            bbox["north"], bbox["south"], bbox["east"], bbox["west"], tags=tags
        )
    except Exception as e:
        print(f"  osmnx download failed: {e}")
        print("  Trying with smaller timeout...")
        gdf = ox.geometries_from_bbox(
            bbox["north"], bbox["south"], bbox["east"], bbox["west"],
            tags=tags
        )
    
    # Filter to only Polygon/MultiPolygon geometries
    from shapely.geometry import Polygon, MultiPolygon
    gdf = gdf[gdf.geometry.apply(lambda g: isinstance(g, (Polygon, MultiPolygon)))]
    
    # Normalize landuse values
    gdf["landuse_coarse"] = gdf["landuse"].apply(normalize_landuse)
    gdf = gdf[gdf["landuse_coarse"].notna()].copy()
    
    os.makedirs(os.path.dirname(cache_path), exist_ok=True)
    with open(cache_path, "wb") as f:
        pickle.dump(gdf, f)
    print(f"  Downloaded {len(gdf)} landuse polygons → {cache_path}")
    return gdf


def load_or_download_landuse(cache_path="data/processed/landuse_polygons.pkl"):
    """Load cached landuse polygons, or download if missing."""
    if os.path.exists(cache_path):
        print(f"[1/5] Loading cached landuse polygons from {cache_path}")
        with open(cache_path, "rb") as f:
            return pickle.load(f)
    return download_landuse_polygons(D12_BBOX, cache_path)


def build_edge_landuse_map(road_graph, landuse_gdf, cache_path="data/processed/edge_landuse_map.pkl"):
    """Map each road edge to its landuse type via point-in-polygon spatial join."""
    from shapely.geometry import Point
    from shapely import STRtree
    
    print("[2/5] Building edge → landuse spatial join...")
    
    # Build STRtree index over landuse polygon centroids for fast candidate filtering
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
        
        # Find containing landuse polygon
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
    with open(meta_path) as f:
        header = f.readline().strip().split("\t")
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
    
    # Per-sensor speed accumulation
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
    
    # Map sensors to (road_type, landuse) via nearest edges
    # Use the existing edge_sensor_map if available
    print("[4/5] Computing per-(road_type, landuse) speed statistics...")
    
    osm_highway_types = [
        "motorway", "motorway_link", "trunk", "trunk_link",
        "primary", "primary_link", "secondary", "secondary_link",
        "tertiary", "tertiary_link", "residential", "living_street",
        "service", "unclassified",
    ]
    
    # Build (road_type, landuse) -> [speeds]
    group_speeds = defaultdict(list)
    
    # For edges with sensors nearby, assign sensor speeds
    edge_sensor_map_path = "data/processed/edge_sensor_map.pkl"
    if os.path.exists(edge_sensor_map_path):
        with open(edge_sensor_map_path, "rb") as f:
            edge_sensor_map = pickle.load(f)
        
        for (u, v, key), nearest_list in edge_sensor_map.items():
            highway = G.edges[u, v, key].get("highway", "unclassified")
            if isinstance(highway, list):
                highway = highway[0]
            landuse = edge_landuse.get((u, v, key))
            
            for sid, dist in nearest_list:
                if dist <= 0.5 and sid in sensor_speeds:
                    key_2d = (str(highway), landuse or "unknown")
                    group_speeds[key_2d].extend(sensor_speeds[sid])
                    # Also contribute to highway-only group
                    key_1d = (str(highway), "*")
                    group_speeds[key_1d].extend(sensor_speeds[sid])
    
    # Compute statistics
    def compute_stats(speeds):
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
    
    by_road_landuse = {}
    for key, speeds in sorted(group_speeds.items()):
        if len(speeds) >= 30:  # minimum sample threshold
            by_road_landuse[key] = compute_stats(speeds)
    
    # Build road-only fallback (landuse="*")
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
    
    # Print summary
    print("\n[5/5] Landuse Speed Prior Summary:")
    print(f"  Landuse types: {landuse_types}")
    print(f"  (road_type, landuse) groups: {len(by_road_landuse)}")
    for key, stats in sorted(by_road_landuse.items()):
        if key[1] == "*":
            continue
        print(f"  {str(key[0]):<20} x {str(key[1]):<15} p50={stats['p50']:>6.1f} km/h  (n={stats['count']:>8,})")
    
    print(f"\n  Saved → {cache_path}")
    return prior


def main():
    t0 = time.time()
    print("=" * 60)
    print("  OSM Landuse → Road Speed Prior")
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
    
    # We need the RoadGraph wrapper to get edge attributes, but for spatial join
    # we just need the raw networkx graph
    from backend.graph.road_graph import RoadGraph
    road_graph = RoadGraph.build_from_osm(
        graph_path=graph_path,
        region_name="Orange County",
        bbox=(33.38, -118.10, 33.95, -117.41),
    )
    
    # 3. Build edge→landuse map
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
```

- [ ] **Step 4: Run tests to verify they now skip (output files need real run first)**

Run: `pytest tests/test_landuse_speed_prior.py -v`
Expected: All SKIP

- [ ] **Step 5: Commit**

```bash
git add tools/build_landuse_speed_prior.py tests/test_landuse_speed_prior.py
git commit -m "feat: add OSM landuse speed prior builder tool"
```

---

### Task 2: Modify `road_graph.py` to use landuse speed prior

**Files:**
- Modify: `backend/graph/road_graph.py:130-160`

- [ ] **Step 1: Write failing test for landuse-aware speed lookup**

```python
# Append to tests/test_landuse_speed_prior.py

def test_road_graph_loads_landuse_prior():
    """RoadGraph should load landuse_speed_prior.pkl when available."""
    from backend.graph.road_graph import RoadGraph
    
    rg = RoadGraph.build_from_osm(
        graph_path="data/processed/road_graph.pkl",
        region_name="Orange County",
        bbox=(33.38, -118.10, 33.95, -117.41),
    )
    
    # If the prior file exists, it should be loaded
    prior_path = "data/processed/landuse_speed_prior.pkl"
    if os.path.exists(prior_path):
        assert rg.landuse_prior is not None
        assert "by_road_landuse" in rg.landuse_prior
    else:
        assert rg.landuse_prior is None or rg.landuse_prior == {}


def test_get_edge_speed_falls_back_when_no_landuse():
    """When landuse is unknown, fall back to 1D highway-based default."""
    from backend.graph.road_graph import RoadGraph
    
    rg = RoadGraph.build_from_osm(
        graph_path="data/processed/road_graph.pkl",
        region_name="Orange County",
        bbox=(33.38, -118.10, 33.95, -117.41),
    )
    
    speed = rg._default_speed_by_highway("residential", landuse_type=None)
    assert speed == 35.0  # existing default for residential


def test_get_edge_speed_with_landuse_returns_plausible_value():
    """When landuse prior exists, speed should be in valid range."""
    from backend.graph.road_graph import RoadGraph
    
    prior_path = "data/processed/landuse_speed_prior.pkl"
    if not os.path.exists(prior_path):
        pytest.skip("landuse_speed_prior.pkl not built yet")
    
    rg = RoadGraph.build_from_osm(
        graph_path="data/processed/road_graph.pkl",
        region_name="Orange County",
        bbox=(33.38, -118.10, 33.95, -117.41),
    )
    
    # Test with a known landuse type
    speed = rg._default_speed_by_highway("motorway", landuse_type="commercial")
    assert 30 <= speed <= 130, f"Unreasonable speed: {speed}"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_landuse_speed_prior.py::test_road_graph_loads_landuse_prior -v`
Expected: FAIL (landuse_prior attribute not found)

- [ ] **Step 3: Modify `road_graph.py` — add landuse prior loading in `build_from_osm()`**

In `build_from_osm()` (line 44), add landuse prior + edge_landuse map loading after graph is loaded and before returning:

```python
# In build_from_osm(), after cls._cached_instance = cls(G) in each branch,
# add _load_landuse_data() call. Best pattern: add after line 56 (pickle cache branch),
# line 74 (XML branch), line 101 (online download branch).
# Or better: add a single _load_landuse_data() call at the end of build_from_osm():

    @classmethod
    def build_from_osm(cls, force_download=False):
        # ... existing loading logic ...
        # At the end, before returning cls._cached_instance:
        cls._cached_instance._load_landuse_data()
        return cls._cached_instance

def _load_landuse_data(self):
    """Load landuse speed prior and edge→landuse map if available."""
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
```

- [ ] **Step 4: Modify `_default_speed_by_highway()` — remove @staticmethod, add landuse parameter**

The current method (line 139) is a `@staticmethod`. Change it to an instance method and add landuse lookup:

```python
def _default_speed_by_highway(self, highway, landuse_type=None):
    """Return default speed (km/h) for a highway type, optionally adjusted by landuse."""
    if isinstance(highway, (list, tuple, set)):
        highway = next(iter(highway), None)
    
    # Try 2D lookup first
    if landuse_type and self.landuse_prior:
        key = (str(highway), landuse_type)
        if key in self.landuse_prior.get("by_road_landuse", {}):
            return self.landuse_prior["by_road_landuse"][key]["p50"]
    
    # Fall back to 1D highway-based table (original logic)
    defaults = {
        "motorway": 105.0, "motorway_link": 55.0, "trunk": 90.0,
        "trunk_link": 50.0, "primary": 65.0, "primary_link": 45.0,
        "secondary": 55.0, "secondary_link": 40.0, "tertiary": 45.0,
        "tertiary_link": 35.0, "residential": 35.0, "unclassified": 35.0,
        "service": 20.0, "living_street": 15.0,
    }
    return defaults.get(highway, 35.0)
```

- [ ] **Step 5: Modify `get_edge_speed()` (line 130) to pass landuse context to `_default_speed_by_highway()`**

```python
def get_edge_speed(self, u, v, key=0):
    """Get speed limit for edge (km/h)."""
    data = self.G.edges[u, v, key]
    speed = data.get("maxspeed", None)
    if speed:
        return self._parse_speed(speed)
    
    highway = data.get("highway")
    
    # Look up landuse for this edge if prior is loaded
    landuse_type = None
    if self.landuse_prior and self.edge_landuse:
        landuse_type = self.edge_landuse.get((u, v, key))
    
    return self._default_speed_by_highway(highway, landuse_type)
```

- [ ] **Step 6: Run tests**

Run: `pytest tests/test_landuse_speed_prior.py -v`
Expected: 
- `test_road_graph_loads_landuse_prior` → PASS or SKIP
- `test_get_edge_speed_falls_back_when_no_landuse` → PASS
- `test_get_edge_speed_with_landuse_returns_plausible_value` → SKIP if prior not built

- [ ] **Step 7: Commit**

```bash
git add backend/graph/road_graph.py tests/test_landuse_speed_prior.py
git commit -m "feat: integrate landuse speed prior into RoadGraph speed lookup"
```

---

### Task 3: Run the full pipeline end-to-end

**Files:** None new

- [ ] **Step 1: Run the landuse prior builder**

Run: `python tools/build_landuse_speed_prior.py`
Expected: Downloads OSM landuse, builds edge map, computes prior, saves output files
Note: Requires network access for OSM download. May take 5-15 minutes.

- [ ] **Step 2: Verify outputs**

Run: `ls -la data/processed/landuse_*.pkl`
Expected: Three files exist — `landuse_polygons.pkl`, `edge_landuse_map.pkl`, `landuse_speed_prior.pkl`

- [ ] **Step 3: Run full test suite**

Run: `pytest tests/test_landuse_speed_prior.py -v`
Expected: All tests PASS (no SKIPs)

- [ ] **Step 4: Smoke test — start Flask and verify speed lookup works**

Run: `python backend/app.py` (background)
Run: `curl -s http://localhost:5000/api/graph/stats | python -m json.tool`
Expected: Returns graph stats successfully (RoadGraph initialized with landuse prior loaded)

- [ ] **Step 5: Commit**

```bash
git add data/processed/landuse_polygons.pkl data/processed/edge_landuse_map.pkl data/processed/landuse_speed_prior.pkl
git commit -m "data: add OSM landuse speed prior outputs for D12 region"
```
