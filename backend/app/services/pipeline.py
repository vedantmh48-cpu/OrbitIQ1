"""The end-to-end query pipeline.

User Query -> NLP Understanding -> Agent/Model Selection -> Data Retrieval
-> Processing -> Verification -> AI Summary -> Persisted Query, Job & Result.

Progress callbacks stream stage events to the WebSocket manager so the UI can
render a live pipeline view; results are always stored and returned in full.
"""
from __future__ import annotations

import asyncio
from typing import Callable, Optional

from ..geo import expand_bbox
from ..storage import datetime_now
from . import agents as agents_mod
from . import processing as proc
from .indexing import SemanticIndex, search_datasets
from .nlp_understanding import understand_query
from .satellite import get_provider
from .summarizer import build_summary
from .verification import verify_result

ProgressFn = Callable[[dict], None]
STAGES = [
    ("nlp", "Parsing query (NLP understanding)", 12),
    ("agent", "Selecting AI agent & model", 26),
    ("retrieval", "Retrieving satellite datasets", 48),
    ("process", "Running spatial/temporal analysis", 72),
    ("verify", "Verifying results", 88),
    ("summary", "Generating AI summary", 96),
    ("saved", "Saving analysis", 100),
]

_semantic_cache: Optional[SemanticIndex] = None


def _get_semantic(db) -> Optional[SemanticIndex]:
    global _semantic_cache
    datasets = db.find("datasets", {})
    if not datasets:
        return None
    if _semantic_cache is None:
        _semantic_cache = SemanticIndex(datasets)
    return _semantic_cache


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


# Real-time phenomena backed by key-free public APIs. Earthquake -> USGS;
# cyclone/drought/weather -> Open-Meteo (live + historical climate).
REALTIME_QUERY = {
    "earthquake": "earthquake",
    "cyclone": "weather",
    "drought": "climate",
    "weather": "weather",
}


def _em_default_bbox(understanding):
    bb = understanding.get("bbox")
    if bb:
        return bb["min_lat"], bb["min_lng"]
    return 19.076, 72.8777  # Mumbai default


def _try_realtime(op, understanding, params):
    """Return a live-data bundle or None when realtime is not applicable."""
    phenom = (understanding.get("phenomenon") or "").lower()
    kind = REALTIME_QUERY.get(phenom)
    if not kind:
        return None
    from . import realtime as _rt

    try:
        if kind == "earthquake":
            data = _rt.fetch_earthquakes(hours=48, min_magnitude=2.5, limit=80)
            events = data.get("events", [])
            if not events:
                return None
            lat, lng = _em_default_bbox(understanding)
            bbox = understanding.get("bbox") or {
                "min_lng": lng - 20, "min_lat": lat - 20, "max_lng": lng + 20, "max_lat": lat + 20
            }
            dataset = {
                "id": "live_usgs_earthquakes",
                "name": "Live earthquakes (USGS)",
                "source": "REAL",
                "observed_at": data.get("observed_at"),
            }
            exec_params = dict(params)
            exec_params["live_events"] = events
            exec_params["event_label"] = "Earthquake"
            exec_params["live_series"] = []
            return dataset, "real-events", exec_params, "Live USGS earthquake feed.", True

        if kind == "weather":
            data = _rt.fetch_weather()
            events = data.get("cities", [])
            if not events:
                return None
            bbox = understanding.get("bbox") or {
                "min_lng": -125, "min_lat": -34, "max_lng": 140, "max_lat": 61
            }
            dataset = {
                "id": "live_weather_cities",
                "name": "Live weather stations (Open-Meteo)",
                "source": "REAL",
                "observed_at": data.get("observed_at"),
            }
            exec_params = dict(params)
            exec_params["live_events"] = events
            exec_params["event_label"] = "Weather station"
            exec_params["live_series"] = events[0].get("hourly", []) if events else []
            return dataset, "real-events", exec_params, "Live Open-Meteo weather feed.", True

        if kind == "climate":
            lat, lng = _em_default_bbox(understanding)
            data = _rt.fetch_climate(lat, lng, understanding.get("date_start"),
                                     understanding.get("date_end"), days=30)
            series = data.get("series", [])
            if not series:
                return None
            live_series = [
                {"date": s.get("date"), "value": s.get("temperature_c")}
                for s in series if s.get("temperature_c") is not None
            ]
            dataset = {
                "id": "live_climate_archive",
                "name": f"Historical climate archive ({lat:.1f},{lng:.1f})",
                "source": "REAL",
                "observed_at": data.get("observed_at"),
                "data_type": "Time-Series",
                "series": live_series,
            }
            exec_params = dict(params)
            exec_params["live_events"] = []
            exec_params["event_label"] = "Climate"
            exec_params["live_series"] = live_series
            return dataset, "time-series", exec_params, "Live Open-Meteo climate archive.", True
    except Exception:
        return None
    return None


def _detect_modality(understanding: dict, plan: dict, dataset: dict) -> dict:
    """Modalità/sensor inference for the execution trace (optical/SAR/fusion/live)."""
    data_type = (understanding.get("data_type") or "").lower()
    agent = (plan.get("agent") or "").lower()
    phenom = (understanding.get("phenomenon") or "").lower()
    analysis = (understanding.get("analysis_type") or "").lower()

    if str(dataset.get("source", "")).upper() == "REAL" or phenom in ("earthquake", "weather", "climate"):
        return {
            "id": "live-api",
            "label": "Live observational API",
            "sensors": [dataset.get("satellite") or dataset.get("source") or "USGS / Open-Meteo"],
            "constraints": "In-situ and observational feeds; no imagery acquisition.",
            "realtime": True,
        }
    if agent == "fusion" or analysis == "fusion":
        return {
            "id": "sar-optical-fusion",
            "label": "Sentinel-1 SAR + Sentinel-2 Optical (cross-modal fusion)",
            "sensors": ["Sentinel-1 C-SAR", "Sentinel-2 MSI"],
            "constraints": "SAR anchors geometry in cloud/rain; optical NIR/SWIR bands supply spectral detail. "
                           "Cross-modal consistency is verified before acceptance.",
        }
    if agent == "sar" or data_type in ("sar", "radar") or analysis in ("sar-backscatter", "flood-mapping"):
        return {
            "id": "sar",
            "label": "Sentinel-1 C-band SAR (all-weather, day/night)",
            "sensors": ["Sentinel-1 C-SAR (VV/VH)"],
            "constraints": "Backscatter σ⁰ signatures decoded from intensity envelope; specular water ~ low σ⁰.",
        }
    return {
        "id": "optical-msi",
        "label": "Sentinel-2 MSI multispectral (optical)",
        "sensors": ["Sentinel-2 MSI (B4 RED·B3 GREEN·B8 NIR·B11 SWIR)"],
        "constraints": "Spectral indices (NDVI/NDWI/NDBI) computed from band ratios; cloud cover may limit retrieval.",
    }


def run_query_pipeline(
    db,
    user_id: str,
    text: str,
    dataset_ids: list[str] | None = None,
    params: dict | None = None,
    progress: Optional[ProgressFn] = None,
) -> dict:
    """Execute the full pipeline synchronously. Returns the result bundle."""
    params = params or {}

    # --- Stage 1: NLP understanding --------------------------------------
    understanding = understand_query(text)
    if understanding.get("bbox") and params.get("buffer_km"):
        understanding["bbox"] = expand_bbox(understanding["bbox"], params.get("buffer_km"))
    _emit(progress, *STAGES[0], {"confidence": understanding.get("confidence")})

    # --- Stage 2: agent selection ----------------------------------------
    semantic = _get_semantic(db)
    candidates = search_datasets(db, understanding, limit=6, semantic_index=semantic)
    if dataset_ids:
        wanted = set(dataset_ids)
        restrict = [d for d in candidates if d["id"] in wanted]
        if restrict:
            candidates = restrict
    if not candidates:
        from ..config import settings

        if not settings.demo_enabled():
            raise RuntimeError(
                "No matching datasets found and demo mode is disabled. "
                "Connect a real provider or enable DEMO_MODE=on."
            )
        raise RuntimeError(
            "No matching datasets were found for this query. Try a different "
            "location, period or data type."
        )
    plan = agents_mod.build_plan(understanding, candidates)
    _emit(progress, *STAGES[1], {"agent": plan.get("agent_name"), "model": plan.get("model")})
# --- Stage 3: retrieval ----------------------------------------------
    steps = plan.get("steps") or []
    op = (
        steps[0]["op"]
        if steps
        else understanding.get("analysis_type") or "classification"
    )
    dataset = candidates[0]
    scenes = []
    retrieval_note = None
    real_retrieval = False

    if op == "image-search":
        try:
            provider = get_provider("stac", db)
            if provider.available():
                res = provider.search(
                    dataset.get("bbox"),
                    understanding.get("date_start"),
                    understanding.get("date_end"),
                    understanding.get("data_type") or "Any",
                    limit=params.get("scene_limit", 30),
                )
                scenes, retrieval_note, real_retrieval = res["scenes"], res["note"], res["real"]
        except Exception as exc:
            retrieval_note = f"Live STAC unavailable ({exc}); using demo catalogue."
        if not scenes:
            provider = get_provider("demo", db)
            demo_res = provider.search(
                dataset.get("bbox"),
                understanding.get("date_start"),
                understanding.get("date_end"),
                understanding.get("data_type") or "Any",
            )
            scenes = demo_res.get("scenes", [])
            retrieval_note = retrieval_note or demo_res.get("note")
            real_retrieval = False
    _emit(progress, *STAGES[2], {"dataset": dataset["id"], "real": real_retrieval})

    modality = _detect_modality(understanding, plan, dataset)
    trace_steps: list[dict] = []
    analysis = None

    # Stage 4a: real-time branch — single live operation, trace is one step.
    live_bundle = _try_realtime(op, understanding, params)
    if live_bundle is not None:
        dataset, op, exec_params, retrieval_note, real_retrieval = live_bundle
        modality = _detect_modality(understanding, plan, dataset)
        _emit(progress, *STAGES[3], {"op": op, "real": True,
                                     "features": len(exec_params.get("live_events", []))})
        analysis = proc.run_operation(op, dataset, understanding, exec_params)
        analysis["metadata"]["note"] = retrieval_note
        trace_steps.append({
            "step": 1,
            "tool": "LiveDataFetcher",
            "op": op,
            "detail": f"Fetched real observations from {dataset.get('source', 'live API')}",
            "result": {"features": len(analysis.get("geojson", {}).get("features", [])),
                       "stats": analysis.get("stats", {})},
        })

    # Stage 4b: multi-tool model chaining — run every agent-planned tool and keep
    # the primary (or requested) analysis; each intermediate tool result is traced.
    else:
        exec_params = dict(params)
        exec_params["scenes"] = scenes
        primary_analysis = None
        for i, step in enumerate(steps or [{"op": op, "name": "analysis"}], 1):
            step_op = step.get("op", op)
            try:
                partial = proc.run_operation(step_op, dataset, understanding, dict(exec_params))
            except Exception as exc:
                trace_steps.append({
                    "step": i, "tool": step.get("name", step_op), "op": step_op,
                    "detail": f"Skipped — {exc}", "result": None,
                })
                continue
            if i == 1 or (understanding.get("analysis_type") and step_op == understanding.get("analysis_type")):
                primary_analysis = partial
            trace_steps.append({
                "step": i,
                "tool": step.get("name", step_op),
                "op": step_op,
                "detail": f"Executed on {dataset.get('name', dataset['id'])}",
                "result": {
                    "features": len(partial.get("geojson", {}).get("features", [])),
                    "stats": partial.get("stats", {}),
                    "label": partial.get("label"),
                },
            })
            _emit(progress, *STAGES[3], {"op": step_op,
                                         "step": i,
                                         "features": len(partial.get("geojson", {}).get("features", []))})
        # If the agent-chained secondary operations exist, attach them as overlay layers.
        if analysis is None:
            analysis = primary_analysis or proc.run_operation(op, dataset, understanding, exec_params)
        op = analysis.get("op", op)
        if scenes and real_retrieval:
            analysis["metadata"]["note"] = retrieval_note

    # --- Stage 5: verification -------------------------------------------
    # Cross-modal consistency checks run automatically for fused/spectral results.
    verification = verify_result(analysis, dataset, understanding,
                                 execution_trace=trace_steps, modality=modality)
    _emit(progress, *STAGES[4], {"status": verification["status"]})

    # --- Stage 6: summary ------------------------------------------------
    summary = build_summary(analysis, understanding, dataset, plan.get("agent_name"))
    execution_trace = {
        "target_task": analysis.get("label") or "Geospatial analysis",
        "modality": modality,
        "tools": [s["tool"] for s in trace_steps],
        "steps": trace_steps,
        "confidence": analysis.get("confidence", 0.5),
        "uncertainties": (analysis.get("metadata") or {}).get("simulated", True) and [
            "Simulated demo dataset — spatial features are illustrative placeholders, "
            "not real observations.",
            "Cross-modal verification carried out on simulated geometry.",
        ] or [],
    }
    _emit(progress, *STAGES[5], {"trace_steps": len(trace_steps)})

    # --- Stage 7: persist -------------------------------------------------
    query_id = db.insert(
        "queries",
        {
            "user_id": user_id,
            "text": text,
            "understanding": understanding,
            "agent": plan.get("agent_name"),
            "model": plan.get("model"),
            "datasets_used": plan.get("datasets_used") or [dataset["id"]],
            "execution_trace": execution_trace,
            "status": "completed",
        },
    )
    result_id = db.insert(
        "results",
        {
            "user_id": user_id,
            "query_id": query_id,
            "op": op,
            "label": analysis.get("label"),
            "confidence": analysis.get("confidence"),
            "geojson": analysis.get("geojson"),
            "layers": analysis.get("layers", []),
            "stats": analysis.get("stats"),
            "charts": analysis.get("charts"),
            "metadata": analysis.get("metadata"),
            "verification": verification,
            "summary": summary,
            "understanding": understanding,
            "execution_trace": execution_trace,
            "modality": modality,
            "simulated": bool(analysis.get("metadata", {}).get("simulated", True)),
            "agent_plan": plan,
        },
    )
    job_id = db.insert(
        "jobs",
        {
            "user_id": user_id,
            "query_id": query_id,
            "result_id": result_id,
            "status": "completed",
            "progress": 100,
            "stage": "saved",
            "message": "Analysis complete.",
            "op": op,
        },
    )
    _emit(progress, *STAGES[6], {"query_id": query_id, "result_id": result_id, "job_id": job_id})

    return {
        "query_id": query_id,
        "result_id": result_id,
        "job_id": job_id,
        "understanding": understanding,
        "agent_plan": plan,
        "dataset": dataset,
        "datasets_candidates": candidates,
        "op": op,
        "analysis": analysis,
        "verification": verification,
        "summary": summary,
        "execution_trace": execution_trace,
        "modality": modality,
        "scenes_retrieved": scenes,
        "real_retrieval": real_retrieval,
    }
async def run_pipeline_as_job(
    db, user_id: str, text: str, dataset_ids=None, params=None
) -> dict:
    """Enqueue and run the pipeline; returns job metadata for polling."""
    params = dict(params or {})
    job_id = db.insert(
        "jobs",
        {
            "user_id": user_id,
            "text": text,
            "status": "pending",
            "progress": 0,
            "stage": "queued",
            "message": "Queued for analysis.",
        },
    )

    loop = asyncio.get_event_loop()

    def _broadcast(msg: dict):
        from .websocket_manager import manager

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
            bundle = run_query_pipeline(db, user_id, text, dataset_ids, params, progress=_progress)
            db.update(
                "jobs",
                job_id,
                {
                    "status": "completed",
                    "progress": 100,
                    "stage": "saved",
                    "result_id": bundle["result_id"],
                    "query_id": bundle["query_id"],
                    "op": bundle["op"],
                },
            )
            from .websocket_manager import manager

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

    result_bundle = await loop.run_in_executor(None, _run)
    return result_bundle