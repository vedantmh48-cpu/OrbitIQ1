"""Query routes: run a natural-language query and browse history."""
from __future__ import annotations

import time

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from fastapi.responses import Response

from ..deps import get_current_user
from ..middleware import logger
from ..schemas import QueryRequest
from ..services.pipeline import run_pipeline_as_job
from ..storage import get_db

router = APIRouter(prefix="/api/queries", tags=["queries"])


@router.post("")
async def run_query(
    body: QueryRequest,
    user: dict = Depends(get_current_user),
    db=Depends(get_db),
):
    ensure_datasets(db)
    try:
        bundle = await run_pipeline_as_job(
            db,
            user["id"],
            body.text,
            dataset_ids=body.dataset_ids,
            params=body.params,
        )
    except Exception as exc:
        logger.exception("Query failed for user %s", user["id"])
        raise HTTPException(status_code=422, detail=str(exc))
    return {
        "job_id": bundle["job_id"],
        "query_id": bundle.get("query_id"),
        "result_id": bundle.get("result_id"),
        "status": "completed",
    }


@router.get("/history")
def query_history(
    limit: int = Query(50, ge=1, le=200),
    user: dict = Depends(get_current_user),
    db=Depends(get_db),
):
    rows = db.find("queries", {"user_id": user["id"]}, sort=[("created_at", -1)], limit=limit)
    return rows


@router.get("/history/{query_id}")
def query_detail(query_id: str, user: dict = Depends(get_current_user), db=Depends(get_db)):
    q = db.find_one("queries", {"id": query_id, "user_id": user["id"]})
    if not q:
        raise HTTPException(status_code=404, detail="Query not found.")
    result = db.find_one("results", {"query_id": query_id})
    return {"query": q, "result": result}


def ensure_datasets(db):
    """Guarantee the demo catalog exists for instant out-of-the-box use."""
    if db.count("datasets", {"source": "DEMO"}) == 0:
        from ..config import settings

        if settings.demo_enabled():
            from ..seed_data import seed_demo_data

            seed_demo_data(db)


@router.post("/understand")
async def understand(
    body: QueryRequest,
    user: dict = Depends(get_current_user),
    db=Depends(get_db),
):
    """Pure NLP extraction (no processing) — powers the understanding panel.

    The response also includes a research brief (phenomenon facts, location
    context, live evidence, imagery availability) so the user sees detailed
    context about their query immediately.
    """
    from ..services.nlp_understanding import understand_query

    parsed = understand_query(body.text)
    if db is not None:
        try:
            from ..services.research import build_research_brief

            parsed["research"] = build_research_brief(parsed, db)
        except Exception as exc:  # research must never break understanding
            logger.warning("Research enrichment skipped: %s", exc)
            parsed["research"] = None
    return parsed


@router.post("/research")
async def deep_research(
    body: QueryRequest,
    user: dict = Depends(get_current_user),
    db=Depends(get_db),
):
    """Detailed research brief for any query (facts + live evidence + STAC)."""
    from ..services.nlp_understanding import understand_query
    from ..services.research import build_research_brief

    parsed = understand_query(body.text)
    brief = build_research_brief(parsed, db)
    return {"query_text": body.text, "research": brief, "understanding": parsed}


@router.post("/upload")
async def upload_image_query(
    file: UploadFile = File(...),
    text: str = "",
    user: dict = Depends(get_current_user),
    db=Depends(get_db),
):
    """Ask a question about a satellite photo uploaded from the user's device.

    Multipart form: ``file`` (JPEG/PNG/WebP/TIFF/BMP/GIF, ≤ 25 MB) plus
    ``text`` (the natural-language question). Real pixel statistics are
    measured from the image and the full research pipeline runs on the query.
    """
    from ..services.image_analysis import ImageError, run_image_query

    raw = await file.read()
    if not raw:
        raise HTTPException(status_code=400, detail="Empty upload.")
    if len(raw) > 25_000_000:
        raise HTTPException(status_code=413, detail="File too large (max 25 MB).")
    if len(text.strip()) < 3:
        text = f"Analyse the satellite photo {file.filename or 'upload'}"
    try:
        bundle = run_image_query(db, user["id"], raw,
                                 file.filename or "photo.img", text.strip())
    except ImageError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    except Exception as exc:
        logger.exception("Image query failed for user %s", user["id"])
        raise HTTPException(status_code=422, detail=f"Image analysis failed: {exc}")
    return {
        "job_id": bundle["job_id"],
        "query_id": bundle["query_id"],
        "result_id": bundle["result_id"],
        "upload_id": bundle["upload_id"],
        "status": "completed",
        "op": "image-analysis",
    }


@router.get("/upload/{upload_id}/meta")
def upload_meta(upload_id: str, user: dict = Depends(get_current_user),
                db=Depends(get_db)):
    """Return the stored metadata of an uploaded image (owner only)."""
    rec = db.find_one("uploads", {"id": upload_id, "user_id": user["id"]})
    if not rec:
        raise HTTPException(status_code=404, detail="Upload not found.")
    return rec


@router.get("/upload/{upload_id}/raw")
def upload_raw(upload_id: str, user: dict = Depends(get_current_user),
               db=Depends(get_db)):
    """Serve the original uploaded image bytes (owner only)."""
    from ..services.image_analysis import read_upload_bytes

    rec = db.find_one("uploads", {"id": upload_id, "user_id": user["id"]})
    if not rec:
        raise HTTPException(status_code=404, detail="Upload not found.")
    data = read_upload_bytes(upload_id)
    if data is None:
        raise HTTPException(status_code=404, detail="Image file missing on disk.")
    media = {
        "JPEG": "image/jpeg", "PNG": "image/png", "WEBP": "image/webp",
        "GIF": "image/gif", "BMP": "image/bmp", "TIFF": "image/tiff",
    }.get(str(rec.get("format", "")).upper(), "application/octet-stream")
    return Response(
        data,
        media_type=media,
        headers={"Cache-Control": "private, max-age=3600"},
    )