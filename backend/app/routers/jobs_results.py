"""Jobs, results and saved-analyses routes."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query

from ..deps import get_current_user
from ..schemas import SaveAnalysisRequest
from ..storage import datetime_now, get_db

router = APIRouter(tags=["jobs-results"])


# ---------------------------------------------------------------------------
# Jobs
# ---------------------------------------------------------------------------


@router.get("/api/jobs/{job_id}")
def get_job(job_id: str, user: dict = Depends(get_current_user), db=Depends(get_db)):
    job = db.find_one("jobs", {"id": job_id})
    if not job:
        raise HTTPException(status_code=404, detail="Job not found.")
    if job["user_id"] != user["id"] and user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Not your job.")
    return job


@router.get("/api/jobs")
def list_jobs(
    limit: int = Query(20, ge=1, le=100),
    user: dict = Depends(get_current_user),
    db=Depends(get_db),
):
    return db.find("jobs", {"user_id": user["id"]}, sort=[("created_at", -1)], limit=limit)


# ---------------------------------------------------------------------------
# Results
# ---------------------------------------------------------------------------


def _result_bundle(result: dict) -> dict:
    return {
        "id": result["id"],
        "query_id": result.get("query_id"),
        "op": result.get("op"),
        "label": result.get("label"),
        "confidence": result.get("confidence"),
        "stats": result.get("stats"),
        "charts": result.get("charts"),
        "metadata": result.get("metadata"),
        "verification": result.get("verification"),
        "summary": result.get("summary"),
        "understanding": result.get("understanding"),
        "execution_trace": result.get("execution_trace"),
        "modality": result.get("modality"),
        "simulated": result.get("simulated", True),
        "google_doc_url": result.get("google_doc_url"),
        "created_at": result.get("created_at"),
        # change-analysis extras so generic Results/History views render the
        # full structured analysis (report, hotspots, technique evidence).
        "report_md": result.get("report_md"),
        "hotspots": result.get("hotspots"),
        "technique_breakdown": result.get("technique_breakdown"),
        "change_analysis": result.get("change_analysis"),
    }


@router.get("/api/results/{result_id}")
def get_result(result_id: str, user: dict = Depends(get_current_user), db=Depends(get_db)):
    result = db.find_one("results", {"id": result_id})
    if not result:
        raise HTTPException(status_code=404, detail="Result not found.")
    if result["user_id"] != user["id"] and user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Not your result.")
    bundle = _result_bundle(result)
    bundle["geojson"] = result.get("geojson")
    bundle["layers"] = result.get("layers", [])
    bundle["agent_plan"] = result.get("agent_plan")
    return bundle


@router.get("/api/results")
def list_results(
    limit: int = Query(30, ge=1, le=100),
    user: dict = Depends(get_current_user),
    db=Depends(get_db),
):
    rows = db.find("results", {"user_id": user["id"]}, sort=[("created_at", -1)], limit=limit)
    return [_result_bundle(r) for r in rows]


@router.delete("/api/results/{result_id}")
def delete_result(result_id: str, user: dict = Depends(get_current_user), db=Depends(get_db)):
    result = db.find_one("results", {"id": result_id})
    if not result:
        raise HTTPException(status_code=404, detail="Result not found.")
    if result["user_id"] != user["id"] and user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Not your result.")
    db.delete("results", result_id)
    for sa in db.find("saved_analyses", {"result_id": result_id}):
        db.delete("saved_analyses", sa["id"])
    return {"ok": True}


# ---------------------------------------------------------------------------
# Saved analyses
# ---------------------------------------------------------------------------


@router.post("/api/saved")
def save_analysis(
    body: SaveAnalysisRequest,
    user: dict = Depends(get_current_user),
    db=Depends(get_db),
):
    result = db.find_one("results", {"id": body.result_id})
    if not result:
        raise HTTPException(status_code=404, detail="Result not found.")
    if result["user_id"] != user["id"] and user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Not your result.")
    existing = db.find_one("saved_analyses", {"result_id": body.result_id, "user_id": user["id"]})
    if existing:
        db.update("saved_analyses", existing["id"], {"notes": body.notes or existing.get("notes", "")})
        return {"ok": True, "id": existing["id"]}
    sid = db.insert(
        "saved_analyses",
        {
            "user_id": user["id"],
            "result_id": body.result_id,
            "name": body.name or result.get("label", "Analysis"),
            "notes": body.notes or "",
            "created_at": datetime_now(),
        },
    )
    return {"ok": True, "id": sid}


@router.get("/api/saved")
def list_saved(user: dict = Depends(get_current_user), db=Depends(get_db)):
    saved = db.find("saved_analyses", {"user_id": user["id"]}, sort=[("created_at", -1)])
    out = []
    for s in saved:
        result = db.find_one("results", {"id": s.get("result_id")})
        if result:
            out.append({**s, "result_label": result.get("label"),
                        "confidence": result.get("confidence"),
                        "simulated": result.get("simulated", True)})
        else:
            out.append(s)
    return out


@router.delete("/api/saved/{saved_id}")
def delete_saved(saved_id: str, user: dict = Depends(get_current_user), db=Depends(get_db)):
    s = db.find_one("saved_analyses", {"id": saved_id})
    if not s:
        raise HTTPException(status_code=404, detail="Saved analysis not found.")
    if s["user_id"] != user["id"]:
        raise HTTPException(status_code=403, detail="Not your analysis.")
    db.delete("saved_analyses", saved_id)
    return {"ok": True}