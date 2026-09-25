"""GeoSpatial & remote-sensing tool routes.

GeoTIFF / GIS header parsing, spectral-index definitions and computation,
and capability introspection — all grounded in real header bytes or clearly
labelled simulated demo output.
"""
from __future__ import annotations

import io
from typing import Optional

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import Response

from ..deps import get_current_user
from ..services import geotools
from ..services.processing import SPECTRAL_SPECS, _spectral_index
from ..storage import get_db

router = APIRouter(prefix="/api/geospatial", tags=["geospatial"])


@router.get("/capabilities")
def capabilities(user: dict = Depends(get_current_user)):
    """Advertise the available geospatial tooling (agent discovery handshake)."""
    return geotools.capability_flags()


@router.get("/indexes")
def index_definitions(user: dict = Depends(get_current_user)):
    """Return the band-ratio spectral-index catalogue with formulas."""
    out = []
    for key, spec in SPECTRAL_SPECS.items():
        out.append({
            "id": key,
            "name": spec["label"],
            "formula": spec["formula"],
            "bands": list(spec["bands"]),
            "threshold": spec["threshold"],
            "positive_label": spec["positive_label"],
            "negative_label": spec["negative_label"],
        })
    return {"indexes": out}


@router.get("/demo")
def demo_geotiff(user: dict = Depends(get_current_user)):
    """Download a synthetic demo GeoTIFF (clearly labelled simulated)."""
    data = geotools.make_demo_geotiff(epsg=4326, width=96, height=96,
                                      min_lng=74.5, min_lat=8.0, max_lng=77.5, max_lat=12.5)
    return Response(
        data,
        media_type="image/tiff",
        headers={"Content-Disposition": 'attachment; filename="demo-kerala.tif"'},
    )


@router.get("/demo/parse")
def demo_parse(user: dict = Depends(get_current_user)):
    """Parse the built-in demo GeoTIFF and return full header/CRS/footprint."""
    data = geotools.make_demo_geotiff(epsg=4326, width=96, height=96,
                                      min_lng=74.5, min_lat=8.0, max_lng=77.5, max_lat=12.5)
    info = geotools.parse_geotiff(data)
    info["simulated"] = True
    info["note"] = "Demo GeoTIFF generated locally for offline exploration — simulated raster."
    return info


@router.post("/parse")
async def parse_geotiff_upload(
    file: UploadFile = File(...),
    user: dict = Depends(get_current_user),
):
    """Parse an uploaded GeoTIFF and return CRS / EPSG / bounds / footprint.

    Works on the raw header bytes — no GDAL needed. Accepts any file; a
    clear validation error is returned for non-TIFF content.
    """
    raw = await file.read()
    if not raw:
        raise HTTPException(status_code=400, detail="Empty upload.")
    if len(raw) > 25_000_000:
        raise HTTPException(status_code=413, detail="File too large (max 25 MB).")
    try:
        info = geotools.parse_geotiff(raw)
    except geotools.GeoTiffError as exc:
        raise HTTPException(status_code=422, detail=f"Not a valid GeoTIFF: {exc}")
    info["filename"] = file.filename
    return info


@router.post("/indexes/run")
def run_index(
    index: str = "ndvi",
    location: str = "Punjab",
    user: dict = Depends(get_current_user),
    db=Depends(get_db),
):
    """Compute a spectral index over a known gazetteer location (demo engine)."""
    from ..services.gazetteer import resolve_location
    from ..services.nlp_understanding import understand_query

    idx = (index or "ndvi").lower()
    if idx not in SPECTRAL_SPECS:
        raise HTTPException(status_code=422, detail=f"Unknown index '{idx}'. "
                                                    f"Supported: {', '.join(SPECTRAL_SPECS)}")
    text = f"Compute {idx} for {location} using Sentinel-2 optical data"
    understanding = understand_query(text)
    if not understanding.get("bbox"):
        loc = resolve_location(location.lower())
        if not loc:
            raise HTTPException(status_code=422, detail=f"Unknown location '{location}'.")
        understanding["bbox"] = loc["bbox"]
        understanding["location"] = loc["name"]

    datasets = db.find("datasets", {})
    demo = next((d for d in datasets if d.get("source") == "DEMO"), {})
    result = _spectral_index(demo, understanding, {"index": idx})
    return {
        "requested_index": idx,
        "location": understanding.get("location"),
        "bbox": understanding.get("bbox"),
        "stats": result["stats"],
        "charts": result["charts"],
        "summary": result["summary"] if False else None,
        "confidence": result["confidence"],
        "formula": SPECTRAL_SPECS[idx]["formula"],
        "geojson": result["geojson"],
        "simulated": True,
    }