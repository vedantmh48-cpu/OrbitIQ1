"""Imagery inventory & retrieval for the change-analysis feature.

Two honest tiers:

1. **Real inventory** — queries STAC Earth Search (AWS, key-free, same
   endpoint as ``services/satellite.py``) for Sentinel-2 L2A scenes covering
   the AOI near the requested date and returns genuine scene metadata
   (id, datetime, cloud cover, platform).
2. **Raster processing** — pixel-level analysis runs on the deterministic
   synthetic demo scenes produced by ``raster.build_scene``; results are
   labelled ``simulated``. If the optional rasterio/GDAL stack is ever
   installed, real COG assets can be downloaded; the app's data policy always
   reports which tier produced the numbers.
"""
from __future__ import annotations

from datetime import date, timedelta
from typing import Optional

import httpx

from ...config import settings
from ..satellite import STAC_ENDPOINT


def stac_scenes(
    bbox: dict,
    day: date,
    days_window: int = 45,
    cloud_lt: float = 30.0,
    limit: int = 4,
    timeout: float = 12.0,
) -> list[dict]:
    """Best-effort STAC search for Sentinel-2 L2A scenes near ``day``."""
    d0 = day - timedelta(days=days_window)
    d1 = day + timedelta(days=days_window)
    body = {
        "collections": ["sentinel-2-l2a"],
        "bbox": [bbox["min_lng"], bbox["min_lat"], bbox["max_lng"], bbox["max_lat"]],
        "datetime": f"{d0.isoformat()}T00:00:00Z/{d1.isoformat()}T23:59:59Z",
        "limit": limit,
        "query": {"eo:cloud_cover": {"lt": cloud_lt}},
        "sortby": [{"field": "properties.eo:cloud_cover", "direction": "asc"}],
    }
    try:
        with httpx.Client(timeout=timeout) as client:
            r = client.post(STAC_ENDPOINT, json=body)
            r.raise_for_status()
            features = r.json().get("features", [])
    except Exception:
        features = []
        try:  # retry once without the sort/query clauses (some catalogs reject them)
            with httpx.Client(timeout=timeout) as client:
                body.pop("query", None)
                body.pop("sortby", None)
                body["limit"] = 3
                r = client.post(STAC_ENDPOINT, json=body)
                r.raise_for_status()
                features = r.json().get("features", [])
        except Exception:
            features = []
    return [_minimal_scene(f) for f in features]


def _minimal_scene(feature: dict) -> dict:
    props = feature.get("properties", {}) or {}
    assets = feature.get("assets", {}) or {}
    preview = ""
    for key in ("visual", "thumbnail", "rendered_preview"):
        if key in assets:
            preview = (assets[key] or {}).get("href", "")
            break
    return {
        "id": feature.get("id", ""),
        "collection": feature.get("collection", ""),
        "datetime": props.get("datetime", ""),
        "cloud_cover": props.get("eo:cloud_cover"),
        "platform": props.get("platform", ""),
        "instrument": props.get("instruments", [None])[0] if props.get("instruments") else "",
        "preview_href": preview,
    }


def fetch_inventory(
    bbox: dict,
    day: date,
    mode: Optional[str] = None,
) -> dict:
    """Return the imagery inventory for one acquisition date.

    ``mode``: auto (prefer real STAC metadata) | demo (synthetic only).
    """
    mode = (mode or settings.CHANGE_IMAGERY_MODE or "auto").lower()
    real_scenes: list[dict] = []
    note = ""
    if mode in ("auto", "stac"):
        try:
            real_scenes = stac_scenes(bbox, day)
        except Exception:
            real_scenes = []
        if real_scenes:
            note = (
                f"Real Sentinel-2 catalog matched {len(real_scenes)} scene(s) near "
                f"{day.isoformat()} (lowest cloud cover retained)."
            )
    raster_processed = False  # disabled until the optional rasterio/GDAL tier is installed
    if raster_processed:
        # Reserved for the COG-download tier (requires rasterio + GDAL wheels).
        note = note or "Scene assets downloaded for raster processing."
    return {
        "date": day.isoformat(),
        "mode": mode,
        "scenes": real_scenes,
        "raster_processed": raster_processed,
        "synthetic": mode == "demo" or not real_scenes,
        "note": note or (
            "No low-cloud real scenes near this date in the open STAC catalog; "
            "pixel analysis uses the deterministic synthetic scene (simulated)."
        ),
    }


def scene_badge(inventory: dict) -> dict:
    """Small provenance badge for UIs / reports."""
    real = bool(inventory.get("scenes"))
    return {
        "real": real,
        "simulated": inventory.get("synthetic", True),
        "source": "STAC Earth Search" if real else "Demo (synthetic)",
        "count": len(inventory.get("scenes", []) or []),
        "note": inventory.get("note", ""),
    }