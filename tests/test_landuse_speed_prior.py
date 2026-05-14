import os
import sys
import pickle
import pytest

# Allow importing from tools/
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "tools"))

from build_landuse_speed_prior import normalize_landuse, compute_speed_stats

# Only the integration tests are slow
pytestmark = pytest.mark.slow


# --- Unit tests (fast, no data dependency) ---

def test_normalize_landuse_commercial():
    assert normalize_landuse("commercial") == "commercial"


def test_normalize_landuse_retail_maps_to_commercial():
    assert normalize_landuse("retail") == "commercial"


def test_normalize_landuse_residential():
    assert normalize_landuse("residential") == "residential"


def test_normalize_landuse_none_returns_none():
    assert normalize_landuse(None) is None


def test_normalize_landuse_unknown_tag_returns_other():
    assert normalize_landuse("nonexistent_tag") == "other"


def test_normalize_landuse_case_insensitive():
    assert normalize_landuse("INDUSTRIAL") == "industrial"


def test_compute_speed_stats_basic():
    speeds = [50.0, 60.0, 70.0]
    stats = compute_speed_stats(speeds)
    assert stats["count"] == 3
    assert stats["mean"] == 60.0
    assert stats["p50"] == 60.0
    assert stats["p5"] == 51.0
    assert stats["p95"] == 69.0


def test_compute_speed_stats_single_value():
    stats = compute_speed_stats([42.0])
    assert stats["count"] == 1
    assert stats["mean"] == 42.0
    assert stats["p50"] == 42.0


# --- Integration tests (slow, require pre-built data) ---

def test_build_landuse_speed_prior_output_structure():
    """Test that the output file has the expected structure."""
    prior_path = "data/processed/landuse_speed_prior.pkl"
    if not os.path.exists(prior_path):
        pytest.skip("landuse_speed_prior.pkl not built yet")

    with open(prior_path, "rb") as f:
        prior = pickle.load(f)

    assert "by_road_landuse" in prior
    assert "by_road_only" in prior
    assert "landuse_types" in prior

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
    assert coverage > 0.01, f"Landuse coverage too low: {coverage:.2%}"
    print(f"Landuse coverage: {coverage:.1%} ({assigned}/{total} edges)")


def test_road_graph_loads_landuse_prior():
    """RoadGraph should load landuse_speed_prior.pkl when available."""
    from backend.graph.road_graph import RoadGraph

    rg = RoadGraph.build_from_osm()

    prior_path = "data/processed/landuse_speed_prior.pkl"
    if os.path.exists(prior_path):
        assert rg.landuse_prior is not None
        assert "by_road_landuse" in rg.landuse_prior
    else:
        assert rg.landuse_prior is None


def test_get_edge_speed_falls_back_when_no_landuse():
    """When landuse prior is unavailable, fall back to 1D highway-based default."""
    from backend.graph.road_graph import RoadGraph

    rg = RoadGraph.build_from_osm()

    # Test the method directly — residential defaults to 35 km/h
    speed = rg._default_speed_by_highway("residential", landuse_type=None)
    assert speed == 35.0

    speed = rg._default_speed_by_highway("motorway", landuse_type=None)
    assert speed == 105.0
