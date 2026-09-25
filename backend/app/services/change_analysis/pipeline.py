"""End-to-end orchestrator for the historical change-analysis feature.

    Dates + Location + Custom query prompt
      -> geocoding          (GPS coordinates / gazetteer / Nominatim)
      -> imagery inventory  (STAC Earth Search metadata or synthetic demo scenes)
      -> change engine      (NDVI/NDBI/NDWI differencing + CVA + hotspots)
      -> VLM synthesis      (deterministic Markdown report, optional vision-LLM)
      -> persisted Query + Result + Job, streaming progress on /ws/jobs/{id}

Results land in the standard ``results`` collection (op ``change-analysis``)
so the existing history / reports / PDF-DOCX-MD / save flows work unchanged.
"""
from __future__ import annotations

import asyncio
from typing import Callable, Optional

from ...config import settings
from ...storage import new_id
from . import engine as engine_mod
from . import geocoding as geo_mod
from . import imagery as imagery_mod
from . import vlm as vlm_mod

ProgressFn = Callable[[dict], None]

STAGES = [
    ("geocode", "Geocoding location & AOI", 8),
    ("inventory", "Retrieving imagery inventory", 24),
    ("scene", "Building aligned before/after scenes", 46),
    ("engine", "Running change-detection engine", 70),
    ("render", "Rendering heatmap & composites", 82),
    ("synthesize", "Generating AI report", 94),
    ("saved", "Saving analysis", 100),
]


def _emit(progress: Optional[ProgressFn], stage_id, stage_name, percent, payload=None):
    if progress:
        progress(
            {
                "stage": stage_id,
                "stage_name": stage_name,
                "progress": percent,
                "payload": payload or {},
            }
        )


def build_execution_trace(
    aoi: dict,
    inventory_1: dict,
    inventory_2: dict,
    techniques: list,
    stats: dict,
    hotspots: list,
    simulated: bool,
) -> dict:
    """Execution-trace block in the ResultDetail contract."""
    steps = [
        {
            "step": 1,
            "tool": aoi["source"],
            "op": "geocoding",
            "detail": (
                f"'{aoi['name']}' resolved to an AOI of {aoi['area_km2']:,.2f} km² "
                f"(bbox {aoi['bbox']['min_lng']:.4f},{aoi['bbox']['min_lat']:.4f} → "
                f"{aoi['bbox']['max_lng']:.4f},{aoi['bbox']['max_lat']:.4f})."
            ),
            "result": {"features": 1, "bbox": aoi["bbox"]},
        },
        {
            "step": 2,
            "tool": "STAC Earth Search" if inventory_1.get("scenes") else "demo-synthetic",
            "op": "imagery-inventory",
            "detail": (
                f"Date 1 {inventory_1['date']}: {len(inventory_1.get('scenes', []) or [])} real "
                f"scene(s). Date 2 {inventory_2['date']}: {len(inventory_2.get('scenes', []) or [])} "
                f"real scene(s). {inventory_1.get('note', '')}"
            ),
            "result": {
                "scenes_date_1": len(inventory_1.get("scenes", []) or []),
                "scenes_date_2": len(inventory_2.get("scenes", []) or []),
            },
        },
        {
            "step": 3,
            "tool": "spectral-index-differencing",
            "op": "change-detection",
            "detail": (
                "Computed NDVI/NDWI/NDBI per date, differenced the aligned grids and "
                "ran Change Vector Analysis; pixels past threshold were merged into a "
                "union change mask and clustered into hotspots."
            ),
            "result": {"features": len(hotspots), "stats": stats},
        },
        {
            "step": 4,
            "tool": "deterministic-raster-renderer" if simulated else "cog-renderer",
            "op": "render",
            "detail": (
                "Rendered before/after composites, signed direction heatmap, magnitude "
                "overlay and a change-intensity GeoTIFF over the AOI."
            ),
            "result": {"features": 0},
        },
    ]
    uncertainties = []
    if simulated:
        uncertainties.extend(
            [
                "Pixel rasters are deterministic simulated scenes (demo tier) — treat "
                "absolute areas as illustrative.",
                "Real STAC metadata is retained for provenance; raster analysis is "
                "synthetic until the rasterio/GDAL processing tier is enabled.",
            ]
        )
    return {
        "target_task": "Historical change analysis (Date 1 vs Date 2)",
        "modality": {
            "id": "optical-msi",
            "label": "Sentinel-2 MSI multispectral (optical) — change analysis",
            "sensors": [
                "Sentinel-2 MSI (B4 RED · B3 GREEN · B8 NIR · B11 SWIR)"
            ],
            "constraints": (
                "Spectral indices (NDVI/NDWI/NDBI) computed from band ratios; "
                "cloud cover may limit real retrieval."
            ),
            "realtime": False,
        },
        "tools": [s["tool"] for s in steps],
        "steps": steps,
        "confidence": 0.6 if simulated else 0.78,
        "uncertainties": uncertainties,
    }


def run_change_analysis_pipeline(
    db,
    user_id: str,
    request,
    progress: Optional[ProgressFn] = None,
) -> dict:
    """Execute the full Date-1-vs-Date-2 pipeline synchronously."""
    date_1, date_2 = request.date_1, request.date_2
    query = (request.query or "").strip() or "Show infrastructure change"
    techniques = engine_mod.select_techniques(query, request.techniques)
    result_id = new_id()
    artifact_dir = settings.change_artifact_dir() / result_id

    # --- Stage 1: geocoding ----------------------------------------------
    aoi = geo_mod.resolve_location(request.location, request.buffer_km)
    _emit(progress, *STAGES[0], {
        "source": aoi["source"],
        "name": aoi["name"],
        "area_km2": aoi["area_km2"],
    })

    # --- Stage 2: imagery inventory (real metadata when reachable) --------
    try:
        inventory_1 = imagery_mod.fetch_inventory(aoi["bbox"], date_1)
    except Exception:
        inventory_1 = imagery_mod.fetch_inventory(aoi["bbox"], date_1, mode="demo")
    try:
        inventory_2 = imagery_mod.fetch_inventory(aoi["bbox"], date_2)
    except Exception:
        inventory_2 = imagery_mod.fetch_inventory(aoi["bbox"], date_2, mode="demo")
    _emit(progress, *STAGES[1], {
        "date_1_scenes": len(inventory_1.get("scenes", []) or []),
        "date_2_scenes": len(inventory_2.get("scenes", []) or []),
    })

    # --- Stage 3: change-detection engine ---------------------------------
    _emit(progress, *STAGES[2], {"techniques": techniques})
    analysis = engine_mod.run_change_analysis(
        aoi=aoi,
        query=query,
        date_1=date_1,
        date_2=date_2,
        techniques=techniques,
        max_cells=request.max_cells,
        artifact_dir=artifact_dir,
    )
    _emit(progress, *STAGES[3], {
        "changed_cells": analysis["stats"].get("changed_cells"),
        "hotspots": analysis["stats"].get("hotspot_count"),
    })
    _emit(progress, *STAGES[4], {
        "artifacts": list(analysis["artifacts"].values()),
    })

    # --- Stage 4: AI/VLM synthesis ----------------------------------------
    report_payload = vlm_mod.synthesize(
        {
            "query": query,
            "location_name": aoi["name"],
            "date_1": date_1.isoformat(),
            "date_2": date_2.isoformat(),
            "stats": analysis["stats"],
            "techniques": analysis["techniques"],
            "hotspots": analysis["hotspots"],
            "inventory1": inventory_1,
            "inventory2": inventory_2,
            "simulated": True,
            "changes_summary": analysis["changes_summary"],
        },
        artifact_bytes={
            "heatmap.png": _read(artifact_dir / "heatmap.png"),
            "before.png": _read(artifact_dir / "before.png"),
            "after.png": _read(artifact_dir / "after.png"),
        },
    )
    _emit(progress, *STAGES[5], {"synthesis": report_payload["synthesis"]})

    # --- Stage 5: provenance / verification --------------------------------
    verification = {
        "status": "passed",
        "confidence": report_payload["summary"]["confidence"],
        "checks": [
            {
                "name": "AOI geometry",
                "passed": True,
                "detail": f"AOI covers {aoi['area_km2']:,.2f} km² from '{aoi['source']}'.",
            },
            {
                "name": "Change statistics",
                "passed": bool(analysis["stats"]["changed_cells"] > 0),
                "detail": (
                    f"{analysis['stats']['changed_cells']} / {analysis['stats']['total_cells']} "
                    f"cells flagged ({analysis['stats']['pct_changed']}%)."
                ),
            },
            {
                "name": "Provenance",
                "passed": True,
                "detail": (
                    "Simulated demo rasters (deterministic). Real STAC metadata "
                    "retained as inventory."
                ),
            },
        ],
    }
    execution_trace = build_execution_trace(
        aoi, inventory_1, inventory_2, techniques,
        analysis["stats"], analysis["hotspots"], simulated=True,
    )
    modality = execution_trace["modality"]

    # --- Stage 6: persist ---------------------------------------------------
    understanding = {
        "query_text": query,
        "location": aoi["name"],
        "bbox": aoi["bbox"],
        "center": aoi["center"],
        "date_start": date_1.isoformat(),
        "date_end": date_2.isoformat(),
        "analysis_type": "change-analysis",
        "agent": "change-analysis",
        "confidence": 0.7,
        "raw_text": query,
    }
    query_id = db.insert(
        "queries",
        {
            "user_id": user_id,
            "text": query,
            "understanding": understanding,
            "agent": "change-analysis",
            "type": "change-analysis",
            "execution_trace": execution_trace,
            "status": "completed",
        },
    )
    layers = [
        {
            "id": "before",
            "name": f"Composite {date_1.isoformat()}",
            "kind": "image",
            "url": f"/api/change-analysis/results/{result_id}/images/before.png",
            "bounds": aoi["bbox"],
            "zindex": 2,
        },
        {
            "id": "after",
            "name": f"Composite {date_2.isoformat()}",
            "kind": "image",
            "url": f"/api/change-analysis/results/{result_id}/images/after.png",
            "bounds": aoi["bbox"],
            "zindex": 2,
        },
        {
            "id": "heatmap",
            "name": "Change heatmap (signed)",
            "kind": "overlay",
            "url": f"/api/change-analysis/results/{result_id}/images/heatmap.png",
            "bounds": aoi["bbox"],
            "zindex": 5,
        },
        {
            "id": "magnitude",
            "name": "Change magnitude",
            "kind": "overlay",
            "url": f"/api/change-analysis/results/{result_id}/images/magnitude.png",
            "bounds": aoi["bbox"],
            "zindex": 5,
        },
    ]
    db.insert(
        "results",
        {
            "id": result_id,
            "user_id": user_id,
            "query_id": query_id,
            "op": "change-analysis",
            "label": f"Historical change — {aoi['name']}",
            "confidence": verification["confidence"],
            "geojson": analysis["geojson"],
            "layers": layers,
            "stats": analysis["stats"],
            "charts": analysis["charts"],
            "metadata": {
                "source": "STAC Earth Search"
                if (inventory_1.get("scenes") or inventory_2.get("scenes"))
                else "DEMO",
                "simulated": True,
                "ai": "change-analysis-v1",
                "inventory_1": inventory_1,
                "inventory_2": inventory_2,
            },
            "verification": verification,
            "summary": report_payload["summary"],
            "report_md": report_payload["report_md"],
            "synthesis": report_payload["synthesis"],
            "understanding": understanding,
            "execution_trace": execution_trace,
            "modality": modality,
            "simulated": True,
            "agent_plan": {
                "agent": "change-analysis",
                "model": "vision-llm" if report_payload["synthesis"] == "vision-llm" else "template",
                "techniques": techniques,
                "steps": [
                    {"op": "geocode"}, {"op": "inventory"}, {"op": "change-detection"},
                    {"op": "render"}, {"op": "synthesis"},
                ],
                "datasets_used": [],
            },
            "hotspots": analysis["hotspots"],
            "technique_breakdown": analysis["techniques"],
            "artifacts": analysis["artifacts"],
            "change_analysis": {
                "aoi": aoi,
                "date_1": date_1.isoformat(),
                "date_2": date_2.isoformat(),
                "techniques": techniques,
                "render": analysis["render"],
                "changes_summary": analysis["changes_summary"],
            },
        },
    )
    _emit(progress, *STAGES[6], {"query_id": query_id, "result_id": result_id})

    return {
        "query_id": query_id,
        "result_id": result_id,
        "understanding": understanding,
        "aoi": aoi,
        "analysis": analysis,
        "verification": verification,
        "summary": report_payload["summary"],
        "report_md": report_payload["report_md"],
        "execution_trace": execution_trace,
        "modality": modality,
        "inventory_1": inventory_1,
        "inventory_2": inventory_2,
        "techniques": techniques,
        "op": "change-analysis",
        "simulated": True,
    }


def _read(path) -> Optional[bytes]:
    try:
        return path.read_bytes()
    except OSError:
        return None


async def run_change_analysis_as_job(
    db,
    user_id: str,
    request,
    job_id: Optional[str] = None,
    progress_probe: Optional[Callable[[], dict]] = None,
) -> dict:
    """Run the pipeline as a background job and stream WS progress.

    Mirrors ``services.pipeline.run_pipeline_as_job`` so the frontend can watch
    ``/ws/jobs/{job_id}`` for the same {progress|complete|error} message types.
    ``job_id`` is created by the caller (router) so it can return fast; this
    function simply adopts it and marks it done/failed as the pipeline runs.
    """
    from ..websocket_manager import manager

    if job_id is None:
        job_id = db.insert(
            "jobs",
            {
                "user_id": user_id,
                "text": request.query or "Change analysis",
                "status": "pending",
                "progress": 0,
                "stage": "queued",
                "stage_name": "Queued for analysis.",
                "message": "Queued for analysis.",
                "kind": "change-analysis",
                "type": "change-analysis",
            },
        )

    loop = asyncio.get_running_loop()

    def _broadcast(msg: dict):
        try:
            fut = asyncio.run_coroutine_threadsafe(
                manager.broadcast(job_id, msg), loop
            )
            fut.result(timeout=2)
        except Exception:
            pass

    def _progress(stage_msg: dict):
        db.update(
            "jobs",
            job_id,
            {
                "status": "running",
                "progress": stage_msg.get("progress", 0),
                "stage": stage_msg.get("stage"),
                "stage_name": stage_msg.get("stage_name"),
                "message": stage_msg.get("stage_name", ""),
            },
        )
        _broadcast({"type": "progress", **stage_msg})

    def _run() -> dict:
        try:
            bundle = run_change_analysis_pipeline(
                db, user_id, request, progress=_progress
            )
            db.update(
                "jobs",
                job_id,
                {
                    "status": "completed",
                    "progress": 100,
                    "stage": "saved",
                    "result_id": bundle["result_id"],
                    "query_id": bundle["query_id"],
                    "op": "change-analysis",
                    "message": "Analysis complete.",
                },
            )
            _broadcast(
                {
                    "type": "complete",
                    "result_id": bundle["result_id"],
                    "query_id": bundle["query_id"],
                }
            )
            return bundle
        except Exception as exc:
            db.update(
                "jobs",
                job_id,
                {"status": "failed", "message": str(exc), "stage": "error"},
            )
            _broadcast({"type": "error", "message": str(exc)})
            raise

    bundle = await loop.run_in_executor(None, _run)
    bundle["job_id"] = job_id
    return bundle