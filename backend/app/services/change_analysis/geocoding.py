"""Location geocoding for the change-analysis feature.

Resolves a free-form input into an area-of-interest (AOI) bounding box:

1. **GPS coordinates** — a square AOI of ``buffer_km`` radius around the point.
2. **Place name / address** — the built-in gazetteer first (offline, instant,
   Indian + global coverage), then Nominatim (OSM) when reachable for arbitrary
   addresses. Nominatim is best-effort and never blocks the pipeline.
3. Unknown names raise a clear ``LocationError``.

Every resolver returns ``{name, kind, bbox, geojson, center, area_km2, source}``.
"""
from __future__ import annotations

import math
from typing import Optional

from ...geo import bbox_area_km2, bbox_center

M_PER_DEG_LAT = 110_574.0


class LocationError(ValueError):
    pass


def _bbox_from_center(lat: float, lng: float, buffer_km: float) -> dict:
    """Build a square bbox around a point (correct lon scaling by latitude)."""
    m_per_deg_lng = 111_320.0 * math.cos(math.radians(lat)) or 111_320.0
    d_lat = (buffer_km * 1000.0) / M_PER_DEG_LAT
    d_lng = (buffer_km * 1000.0) / m_per_deg_lng
    return {
        "min_lng": round(lng - d_lng, 6),
        "min_lat": round(lat - d_lat, 6),
        "max_lng": round(lng + d_lng, 6),
        "max_lat": round(lat + d_lat, 6),
    }


def _bbox_geojson(bb: dict) -> dict:
    coords = [
        [bb["min_lng"], bb["min_lat"]],
        [bb["max_lng"], bb["min_lat"]],
        [bb["max_lng"], bb["max_lat"]],
        [bb["min_lng"], bb["max_lat"]],
        [bb["min_lng"], bb["min_lat"]],
    ]
    return {"type": "Polygon", "coordinates": [coords]}


def _aoi_payload(name: str, kind: str, bb: dict, source: str) -> dict:
    lat, lng = bbox_center(bb)
    return {
        "name": name,
        "kind": kind,
        "bbox": bb,
        "geojson": _bbox_geojson(bb),
        "center": {"lat": round(lat, 5), "lng": round(lng, 5)},
        "area_km2": round(bbox_area_km2(bb), 3),
        "source": source,
    }


def geocode_coordinates(lat: float, lng: float, buffer_km: float) -> dict:
    """Resolve GPS coordinates into a square AOI around the point."""
    if not (-90 <= lat <= 90) or not (-180 <= lng <= 180):
        raise LocationError("Coordinates out of range (lat ∈ [-90, 90], lng ∈ [-180, 180]).")
    buffer_km = max(0.1, min(50.0, float(buffer_km or 1.0)))
    bb = _bbox_from_center(lat, lng, buffer_km)
    return _aoi_payload(
        f"{lat:.5f}, {lng:.5f}", "gps-point",
        bb, "coordinates",
    )


def geocode_gazetteer(text: str) -> Optional[dict]:
    """Resolve a place name through the offline gazetteer."""
    from ..gazetteer import resolve_location

    entry = resolve_location(text.strip().lower())
    if not entry:
        return None
    bb = entry["bbox"]
    return _aoi_payload(entry["name"], entry.get("kind", "place"), bb, "gazetteer")


def geocode_nominatim(text: str, timeout: float = 4.0) -> Optional[dict]:
    """Best-effort Nominatim (OpenStreetMap) lookup for arbitrary addresses."""
    import httpx

    from ...config import settings

    try:
        r = httpx.get(
            "https://nominatim.openstreetmap.org/search",
            params={
                "q": text,
                "format": "json",
                "polygon_geojson": 1,
                "limit": 1,
            },
            headers={"User-Agent": getattr(settings, "APP_NAME", "SatQuery AI") + "/1.0"},
            timeout=timeout,
        )
        r.raise_for_status()
        results = r.json()
        if not results:
            return None
        hit = results[0]
        bb = {
            "min_lng": float(hit["boundingbox"][2]),
            "min_lat": float(hit["boundingbox"][0]),
            "max_lng": float(hit["boundingbox"][3]),
            "max_lat": float(hit["boundingbox"][1]),
        }
        return _aoi_payload(
            hit.get("display_name", text), hit.get("type", "place"), bb, "nominatim"
        )
    except Exception:
        return None


def geocode(text: str, fallback: bool = True) -> Optional[dict]:
    """Resolve a place name: gazetteer first, Nominatim as a fallback."""
    aoi = geocode_gazetteer(text)
    if aoi is not None:
        return aoi
    if fallback:
        return geocode_nominatim(text)
    return None


def resolve_location(
    location,
    buffer_km: Optional[float] = None,
) -> dict:
    """Turn a validated ChangeLocation schema into a change-analysis AOI."""
    from ...config import settings

    if getattr(location, "latitude", None) is not None:
        return geocode_coordinates(
            location.latitude, location.longitude,
            buffer_km if buffer_km else settings.CHANGE_DEFAULT_BUFFER_KM,
        )
    text = (location.text or "").strip()
    if not text:
        raise LocationError("No location provided.")
    aoi = geocode(text)
    if aoi is None:
        raise LocationError(
            f"Could not resolve location '{text}'. Try GPS coordinates instead."
        )
    return aoi


def grid_params(bbox: dict, max_cells: int):
    """Compute a cols/rows grid respecting an aspect-ratio-correct cell budget."""
    from ...config import settings

    max_cells = max(576, min(90000, int(max_cells or settings.CHANGE_MAX_CELLS)))
    w = bbox["max_lng"] - bbox["min_lng"]
    h = bbox["max_lat"] - bbox["min_lat"]
    if w <= 0 or h <= 0:
        raise LocationError("AOI has zero spatial extent.")
    aspect = max(0.2, min(5.0, w / h))
    cols = int(math.sqrt(max_cells * aspect))
    rows = int(max_cells / max(cols, 1))
    cols, rows = max(24, cols), max(24, rows)
    # Re-fit to the budget while keeping >= 24 cells in each direction.
    while cols * rows > max_cells and cols > 32 and rows > 32:
        if cols > rows:
            cols -= 1
        else:
            rows -= 1
    return cols, rows