"""Pure-Python geospatial helpers (no GDAL/Rasterio required).

Kept dependency-free on purpose so the entire pipeline runs anywhere, while
still producing real, verifiable geometry (GeoJSON) that can be rendered by
any GIS. Optional raster/vector libraries are used only when installed.
"""
from __future__ import annotations

import math
import random
from typing import Any, Iterable

# ---------------------------------------------------------------------------
# Basic geometry
# ---------------------------------------------------------------------------


def haversine_km(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """Great-circle distance between two points, in kilometres."""
    r = 6371.0088
    p1, p2 = math.radians(lat1), math.radians(lng1)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lng2 - lng1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def bbox_center(bb: dict) -> tuple[float, float]:
    return ((bb["min_lat"] + bb["max_lat"]) / 2.0, (bb["min_lng"] + bb["max_lng"]) / 2.0)


def bbox_area_km2(bb: dict) -> float:
    """Approximate planar-ish area using mid-latitude cell scaling."""
    lat_c = (bb["min_lat"] + bb["max_lat"]) / 2.0
    m_per_deg_lat = 110_574.0
    m_per_deg_lng = 111_320.0 * math.cos(math.radians(lat_c)) or 111_320.0
    w = (bb["max_lng"] - bb["min_lng"]) * m_per_deg_lng
    h = (bb["max_lat"] - bb["min_lat"]) * m_per_deg_lat
    return (w * h) / 1_000_000.0


def cell_area_km2(lat: float, res_deg: float) -> float:
    """Area of a degenerate grid cell of side res_deg degrees."""
    m_per_deg_lng = 111_320.0 * math.cos(math.radians(lat)) or 111_320.0
    w = res_deg * m_per_deg_lng
    h = res_deg * 110_574.0
    return (w * h) / 1_000_000.0


def bbox_overlap(a: dict, b: dict) -> bool:
    return not (
        a["max_lng"] < b["min_lng"]
        or a["min_lng"] > b["max_lng"]
        or a["max_lat"] < b["min_lat"]
        or a["min_lat"] > b["max_lat"]
    )


def bbox_intersection(a: dict, b: dict) -> dict | None:
    if not bbox_overlap(a, b):
        return None
    return {
        "min_lng": max(a["min_lng"], b["min_lng"]),
        "min_lat": max(a["min_lat"], b["min_lat"]),
        "max_lng": min(a["max_lng"], b["max_lng"]),
        "max_lat": min(a["max_lat"], b["max_lat"]),
    }


def point_in_bbox(lat: float, lng: float, bb: dict) -> bool:
    return bb["min_lat"] <= lat <= bb["max_lat"] and bb["min_lng"] <= lng <= bb["max_lng"]


def expand_bbox(bb: dict, km_pad: float) -> dict:
    """Grow a bounding box by an approximate distance on all sides."""
    lat = (bb["min_lat"] + bb["max_lat"]) / 2.0
    m_per_deg_lat = 110_574.0
    m_per_deg_lng = 111_320.0 * math.cos(math.radians(lat)) or 111_320.0
    d_lat = (km_pad * 1000.0) / m_per_deg_lat
    d_lng = (km_pad * 1000.0) / m_per_deg_lng
    return {
        "min_lng": bb["min_lng"] - d_lng,
        "min_lat": bb["min_lat"] - d_lat,
        "max_lng": bb["max_lng"] + d_lng,
        "max_lat": bb["max_lat"] + d_lat,
    }
# ---------------------------------------------------------------------------
# Simulated raster / grid generation (deterministic per seed)
# ---------------------------------------------------------------------------


def grid_cell_centers(bb: dict, res_deg: float) -> Iterable[tuple[float, float]]:
    """Yields (lat, lng) centres at resolution res_deg inside the bbox."""
    lat = bb["min_lat"] + res_deg / 2.0
    while lat < bb["max_lat"]:
        lng = bb["min_lng"] + res_deg / 2.0
        while lng < bb["max_lng"]:
            yield (round(lat, 6), round(lng, 6))
            lng += res_deg
        lat += res_deg


def _det_hash(*parts: float) -> int:
    """Deterministic 32-bit integer hash (FNV-1a) for reproducible rasters.

    Python's built-in ``hash()`` is not guaranteed stable across interpreter
    versions, so demo rasters use this explicit hash to stay byte-for-byte
    reproducible between requests, reports and export downloads.
    """
    h = 2166136261
    for part in parts:
        h ^= int(round(part, 6) * 1_000_000)
        h = (h * 16777619) & 0xFFFFFFFF
    return h


def _field_value(seed: int, lat: float, lng: float, freq: float = 1.0) -> float:
    """Deterministic, spatially-smooth noise field in [0, 1].

    Uses low-frequency sinusoids plus a deterministic hash of the raw
    coordinate so the same seed always reproduces the same "scene" --
    required for reproducible demo results across requests and report
    downloads.
    """
    smooth = (
        0.35
        + 0.30 * math.sin(lat / freq * 1.8 + seed % 7)
        + 0.25 * math.sin(lng / freq * 1.4 + seed % 11)
        + 0.10 * math.sin((lat + lng) / freq * 2.2)
    )
    base = ((_det_hash(seed, lat, lng) % 1000) + 1000) / 2000.0
    v = 0.6 * smooth + 0.4 * base
    return max(0.0, min(1.0, v))


def sample_layer(
    seed: int,
    bb: dict,
    res_deg: float,
    frequency: float = 1.0,
    threshold: float | None = None,
) -> list[dict]:
    """Sample a synthetic continuous field onto a grid of GeoJSON polygons.

    Each returned cell: {"feature": Feature, "lat","lng","value"}.
    If ``threshold`` is given only cells above it are returned.
    """
    out: list[dict] = []
    for lat, lng in grid_cell_centers(bb, res_deg):
        value = _field_value(seed, lat, lng, frequency)
        if threshold is not None and value < threshold:
            continue
        half = res_deg / 2.0
        feature = {
            "type": "Feature",
            "properties": {"lat": lat, "lng": lng, "value": round(value, 4)},
            "geometry": {
                "type": "Polygon",
                "coordinates": [
                    [
                        [lng - half, lat - half],
                        [lng + half, lat - half],
                        [lng + half, lat + half],
                        [lng - half, lat + half],
                        [lng - half, lat - half],
                    ]
                ],
            },
        }
        out.append({"lat": lat, "lng": lng, "value": value, "feature": feature})
    return out


def gaussian_blob(seed: int, lat: float, lng: float, sigma_deg: float) -> float:
    """Radial falloff helper (kept for future feature-localisation use)."""
    return math.exp(-(lat ** 2 + lng ** 2) / (2 * sigma_deg ** 2))


def as_feature_collection(features: list[dict], properties: dict | None = None) -> dict:
    return {
        "type": "FeatureCollection",
        "properties": properties or {},
        "features": features,
    }


def cluster_centers(seed: int, bb: dict, n_clusters: int) -> list[tuple[float, float]]:
    """Deterministic cluster centres within a bbox."""
    rng = random.Random(seed)
    out = []
    for _ in range(n_clusters):
        lat = bb["min_lat"] + rng.random() * (bb["max_lat"] - bb["min_lat"])
        lng = bb["min_lng"] + rng.random() * (bb["max_lng"] - bb["min_lng"])
        out.append((round(lat, 5), round(lng, 5)))
    return out