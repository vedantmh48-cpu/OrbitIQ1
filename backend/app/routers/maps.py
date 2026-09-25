"""Map Type Catalog & dynamic cartographic layer routes.

* ``GET /api/v1/maps/catalog``      - the 32+ entry catalog (searchable,
                                      category-filterable, permission-aware).
* ``GET /api/v1/maps/layers/{type}``- layer config + dynamic GeoJSON data
                                      (dots / flow arcs / choropleth cells /
                                      contour isolines / DEM grids).
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query

from ..deps import get_current_user
from ..map_catalog import (
    CATEGORY_LABELS,
    MAP_CATEGORIES,
    get_entry,
    layer_response,
    permission_gate,
    public_catalog,
)

router = APIRouter(prefix="/api/v1/maps", tags=["maps"])


@router.get("/catalog")
def catalog(
    category: str | None = Query(default=None, description="Filter by MAP_CATEGORIES"),
    q: str | None = Query(default=None, max_length=80, description="Search title/key"),
    user: dict = Depends(get_current_user),
):
    if category and category not in MAP_CATEGORIES:
        raise HTTPException(status_code=422, detail=f"Unknown category '{category}'. Valid: {MAP_CATEGORIES}")
    entries = public_catalog(filter_category=category, query=q)
    entries = [e for e in entries if permission_gate_from_entry(e, user)]

    grouped = {cat: [e for e in entries if e["category"] == cat] for cat in MAP_CATEGORIES}
    return {
        "maps": entries,
        "categories": [
            {"id": cat, "label": CATEGORY_LABELS.get(cat, cat), "count": len(grouped[cat])}
            for cat in MAP_CATEGORIES
        ],
        "total": len(entries),
        "note": "layer_config.overlay.type drives the MapLibre/Deck.gl renderer.",
    }


def permission_gate_from_entry(public: dict, user: dict) -> bool:
    """Apply the tier gate to an already-public entry dict."""
    return permission_gate(_to_catalog_entry(public), user)


def _to_catalog_entry(public: dict) -> dict:
    return {"permission_tier": public.get("permission_tier", "all")}


@router.get("/layers/{key}")
def layers(
    key: str,
    bbox: str | None = Query(default=None, description="min_lng,min_lat,max_lng,max_lat"),
    count: int = Query(default=240, ge=1, le=2000),
    time_index: int = Query(default=0, ge=0),
    dynamic: bool = Query(default=True, description="Attach generated GeoJSON data"),
    user: dict = Depends(get_current_user),
):
    entry = get_entry(key)
    if not entry:
        raise HTTPException(status_code=404, detail=f"Unknown map type: {key}")
    if not permission_gate(entry, user):
        raise HTTPException(status_code=403, detail="Your account tier cannot use this map layer.")
    response = layer_response(key, bbox, count, time_index, dynamic)
    if response.get("error"):
        raise HTTPException(status_code=404, detail=response["detail"])
    return response