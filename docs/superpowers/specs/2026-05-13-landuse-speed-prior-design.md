# Land Use-Aware Road Speed Prior

**Date:** 2026-05-13
**Status:** approved
**Ref:** Acharya et al. (2024), Journal of Transport Geography

## Scope

Enrich the road speed prior system by incorporating OSM land use data, changing the current 1D `road_type -> speed` mapping into a 2D `(road_type, landuse) -> speed` mapping. This allows roads of the same OSM highway type to receive different speed estimates based on their urban context (commercial, residential, industrial, etc.).

## Data Flow

```
OSM Overpass API
  -> osmnx.geometries_from_bbox(tags={'landuse': True})
    -> data/processed/landuse_polygons.pkl
      -> Shapely STRtree spatial index + Point-in-Polygon for edge midpoints
        -> data/processed/edge_landuse_map.pkl
          -> Join with PeMS speed statistics, group by (road_type, landuse)
            -> data/processed/landuse_speed_prior.pkl
              -> road_graph.py: _default_speed_by_highway(highway_type, landuse_type=None)
```

## Files

| File | Action | Purpose |
|------|--------|---------|
| `tools/build_landuse_speed_prior.py` | New | Download landuse, spatial join, group stats, export |
| `backend/graph/road_graph.py` | Modify | Load landuse prior, add `landuse_type` param to speed lookup |
| `tools/build_road_speed_prior.py` | No change | Kept as 1D fallback |

## Key Decisions

- **Speed statistic:** p50 (median) — robust against congestion skew
- **Fallback:** 1D road_type prior when edge midpoint falls outside all landuse polygons
- **Difference from Acharya (2024):** statistical prior + rule-based mapping instead of XGBoost, zero inference overhead
