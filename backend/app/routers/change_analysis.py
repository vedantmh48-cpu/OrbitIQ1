"""Historical change analysis routes (Date 1 vs Date 2).

* ``POST /api/change-analysis``        — run a change-analysis job (async).
* ``GET  /api/change-analysis/capabilities`` — engine/techniques/provider flags.
* ``GET  /api/change-analysis/geocode`` — AOI preview for a place/coordinate.
* ``GET  /api/change-analysis/jobs/{job_id}`` — live job status.
* ``GET  /api/change-analysis/results/{result_id}`` — full result bundle.
* ``GET  /api/change-analysis/results/{id}/images/{kind}.png`` — before/after/
  heatmap/magnitude/change-mask renders.
* ``GET  /api/change-analysis/results/{id}/raster.tif`` — change-intensity GeoTIFF.
* ``GET  /api/change-analysis/results/{id}/masks.geojson`` — changed-cell grid.
* ``GET  /api/change-analysis/results/{id}/report.md`` — structured Markdown.

Results are stored in the standard ``results`` collection (op
``change-analysis``), so the existing history / reports / PDF-DOCX-MD / save
flows all work without changes.
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import JSONResponse, PlainTextResponse, Response

from ..config import settings
from ..deps import get_current_user
from ..schemas import ChangeAnalysisRequest, ChangeLocation
from ..services.change_analysis import geocoding as geo_mod
from ..services.change_analysis import imagery as imagery_mod
from ..services.change_analysis import pipeline as pipeline_mod
from ..services.change_analysis import vlm as vlm_mod
from ..storage import get_db

router = APIRouter(prefix="/api/change-analysis", tags=["change-analysis"])

_IMAGE_KINDS = {
    "before": "before.png",
    "after": "after.png",
    "heatmap": "heatmap.png",
    "magnitude": "magnitude.png",
    "change-mask": "change-mask.png",
}


def _require_enabled() -> None:
    if not settings.CHANGE_ANALYSIS_ENABLED:
        raise HTTPException(
            status_code=404,
            detail="Change analysis is disabled on this deployment "
                   "(CHANGE_ANALYSIS_ENABLED=false).",
        )


def _owner_result(result_id: str, user: dict, db):
    result = db.find_one("results", {"id": result_id})
    if not result:
        raise HTTPException(status_code=404, detail="Result not found.")
    if result.get("user_id") != user["id"] and user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Not your result.")
    if result.get("op") != "change-analysis":
        raise HTTPException(
            status_code=422, detail="This result is not a change-analysis result."
        )
    return result


@router.post("", status_code=202)
async def run_change_analysis(
    body: ChangeAnalysisRequest,
    user: dict = Depends(get_current_user),
    db=Depends(get_db),
):
    """Enqueue a historical change-analysis job and return immediately.

    The pipeline runs in the background and streams progress to
    ``/ws/jobs/{job_id}``; poll ``GET /api/change-analysis/jobs/{job_id}``
    for the terminal state.
    """
    import asyncio

    _require_enabled()
    job_id = db.insert(
        "jobs",
        {
            "user_id": user["id"],
            "text": body.query or "Change analysis",
            "status": "pending",
            "progress": 0,
            "stage": "queued",
            "stage_name": "Queued for analysis.",
            "message": "Queued for analysis.",
            "kind": "change-analysis",
            "type": "change-analysis",
        },
    )

    async def _runner():
        return await pipeline_mod.run_change_analysis_as_job(
            db, user["id"], body, job_id=job_id
        )

    task = asyncio.create_task(_runner())

    def _done(t):
        if t.cancelled():
            return
        exc = t.exception()
        if exc is not None:
            from ..middleware import logger

            logger.warning("Change-analysis job %s failed: %s", job_id, exc)

    task.add_done_callback(_done)
    return {
        "job_id": job_id,
        "status": "running",
        "op": "change-analysis",
        "message": "Change analysis job queued.",
    }


@router.get("/capabilities")
def capabilities(user: dict = Depends(get_current_user)):
    """Advertise available change-analysis techniques and imagery tiers."""
    from ..services.change_analysis import engine as engine_mod

    _require_enabled()
    return {
        "enabled": True,
        "techniques": [
            {
                "id": tid,
                "label": spec["label"],
                "gain": spec["gain"],
                "loss": spec["loss"],
                "signal": spec["signal"],
            }
            for tid, spec in engine_mod.rx.TECHNIQUES.items()
        ],
        "imagery_modes": ["auto", "demo"],
        "imagery_default": (settings.CHANGE_IMAGERY_MODE or "auto"),
        "stac_endpoint": imagery_mod.STAC_ENDPOINT,
        "raster_processing": "synthetic-demo",
        "llm_synthesis": "vision-llm" if vlm_mod._llm_enabled() else "deterministic-template",
        "model": settings.CHANGE_LLM_MODEL,
    }


@router.get("/geocode")
def geocode_preview(
    q: Optional[str] = Query(default=None, max_length=200),
    coordinates: Optional[str] = Query(default=None, description="latitude,longitude"),
    buffer_km: Optional[float] = Query(default=None, ge=0.1, le=50),
    user: dict = Depends(get_current_user),
):
    """Resolve a place name or ``lat,lng`` into an AOI preview (no processing)."""
    _require_enabled()
    if (q or "").strip():
        location = ChangeLocation(text=q)
    elif coordinates:
        try:
            lat_part, lng_part = coordinates.split(",")
            location = ChangeLocation(
                latitude=float(lat_part.strip()), longitude=float(lng_part.strip())
            )
        except (ValueError, AttributeError):
            raise HTTPException(
                status_code=422, detail="coordinates must be 'latitude,longitude'."
            )
    else:
        raise HTTPException(
            status_code=422, detail="Provide ?q=place name or ?coordinates=lat,lng."
        )
    try:
        aoi = geo_mod.resolve_location(location, buffer_km)
    except geo_mod.LocationError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    return {"aoi": aoi, "buffer_km": buffer_km or settings.CHANGE_DEFAULT_BUFFER_KM}


@router.get("/jobs/{job_id}")
def get_job(job_id: str, user: dict = Depends(get_current_user), db=Depends(get_db)):
    """Return live job status for the change-analysis progress UI."""
    job = db.find_one("jobs", {"id": job_id})
    if not job:
        raise HTTPException(status_code=404, detail="Job not found.")
    if job.get("user_id") != user["id"] and user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Not your job.")
    return {
        "id": job["id"],
        "status": job.get("status"),
        "progress": job.get("progress", 0),
        "stage": job.get("stage"),
        "stage_name": job.get("stage_name"),
        "message": job.get("message"),
        "result_id": job.get("result_id"),
        "query_id": job.get("query_id"),
        "created_at": job.get("created_at"),
        "updated_at": job.get("updated_at"),
    }


# ---------------------------------------------------------------------------
# Result artifact + bundle endpoints
# ---------------------------------------------------------------------------


@router.get("/results/{result_id}")
def get_result(result_id: str, user: dict = Depends(get_current_user), db=Depends(get_db)):
    """Full change-analysis result bundle (map overlays, report, hotspots)."""
    result = _owner_result(result_id, user, db)
    return {
        "id": result["id"],
        "op": result.get("op"),
        "label": result.get("label"),
        "confidence": result.get("confidence"),
        "stats": result.get("stats"),
        "charts": result.get("charts"),
        "metadata": result.get("metadata"),
        "verification": result.get("verification"),
        "summary": result.get("summary"),
        "report_md": result.get("report_md"),
        "understanding": result.get("understanding"),
        "execution_trace": result.get("execution_trace"),
        "modality": result.get("modality"),
        "layers": result.get("layers", []),
        "geojson": result.get("geojson"),
        "hotspots": result.get("hotspots"),
        "technique_breakdown": result.get("technique_breakdown"),
        "artifacts": result.get("artifacts"),
        "simulated": result.get("simulated", True),
        "created_at": result.get("created_at"),
    }


@router.get("/results/{result_id}/images/{kind}.png")
def get_image(
    result_id: str,
    kind: str,
    token: Optional[str] = Query(default=None, description="Access token for <img> elements"),
    request: Request = None,
    db=Depends(get_db),
):
    """Serve rendered PNGs (before/after/heatmap/magnitude/change-mask).

    Accepts either a ``Bearer`` header (API clients) or a ``?token=`` query
    parameter so plain ``<img>``/``ImageOverlay`` tags on the map can load the
    protected renders. Mirrors the existing WebSocket auth pattern.
    """
    if kind not in _IMAGE_KINDS:
        raise HTTPException(
            status_code=422,
            detail=f"Unknown image kind '{kind}'. Valid: {', '.join(_IMAGE_KINDS)}",
        )
    user = _resolve_request_user(request, token, db)
    if user is None:
        raise HTTPException(
            status_code=401,
            detail="Not authenticated.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    _owner_result(result_id, user, db)
    path = settings.change_artifact_dir() / result_id / _IMAGE_KINDS[kind]
    if not path.exists():
        raise HTTPException(status_code=404, detail="Render not found on disk.")
    return Response(
        path.read_bytes(),
        media_type="image/png",
        headers={"Cache-Control": "private, max-age=3600"},
    )


def _resolve_request_user(request, token: Optional[str], db):
    """Resolve the caller from a Bearer header OR the ``?token=`` query."""
    from ..security import decode_token

    candidates = []
    if request is not None:
        auth = request.headers.get("Authorization", "")
        if auth.lower().startswith("bearer "):
            candidates.append(auth[7:])
    if token:
        candidates.append(token)
    for value in candidates:
        try:
            payload = decode_token(value, "access")
            user = db.find_one("users", {"id": payload.get("sub")})
            if user and user.get("active", True):
                return user
        except Exception:
            continue
    return None


@router.get("/results/{result_id}/raster.tif")
def get_raster(
    result_id: str,
    user: dict = Depends(get_current_user),
    db=Depends(get_db),
):
    """Change-intensity single-band GeoTIFF (EPSG:4326) for GIS workflows."""
    _owner_result(result_id, user, db)
    path = settings.change_artifact_dir() / result_id / "change-intensity.tif"
    if not path.exists():
        raise HTTPException(status_code=404, detail="Raster not found on disk.")
    return Response(
        path.read_bytes(),
        media_type="image/tiff",
        headers={
            "Content-Disposition": f'attachment; filename="change-intensity-{result_id[:8]}.tif"',
            "Cache-Control": "private, max-age=3600",
        },
    )


@router.get("/results/{result_id}/masks.geojson")
def get_masks(
    result_id: str,
    user: dict = Depends(get_current_user),
    db=Depends(get_db),
):
    """Changed-cell detector grid as GeoJSON (gain/loss polycells)."""
    result = _owner_result(result_id, user, db)
    geojson = result.get("geojson") or {"type": "FeatureCollection", "features": []}
    return JSONResponse(geojson)


@router.get("/results/{result_id}/report.md")
def get_report(
    result_id: str,
    user: dict = Depends(get_current_user),
    db=Depends(get_db),
):
    """Structured Markdown analytical report."""
    result = _owner_result(result_id, user, db)
    report = result.get("report_md") or ""
    return PlainTextResponse(report, media_type="text/markdown")