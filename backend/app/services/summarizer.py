"""AI summary generation.

Produces a readable, structured executive summary of an analysis result.
An optional LLM (LLM_API_KEY) can be wired in; until then a deterministic
explainer renders the same facts clearly, including the simulated-data notice
so the UI never misrepresents demo output as real.
"""
from __future__ import annotations

import datetime as dt


def format_pct(v) -> str:
    try:
        return f"{round(float(v) * 100)}%"
    except (TypeError, ValueError):
        return "—"


OP_LABELS = {
    "flood-mapping": "flood extent",
    "change-detection": "land change",
    "classification": "land cover",
    "object-detection": "detected objects",
    "time-series": "time-series trend",
    "fusion": "multi-source consensus",
    "terrain": "terrain / elevation",
    "image-search": "scene retrieval",
    "image-analysis": "uploaded-photo analysis",
}


def build_summary(result: dict, understanding: dict, dataset: dict | None = None, agent_name: str = "") -> dict:
    op = result.get("op", "analysis")
    stats = result.get("stats", {})
    loc = understanding.get("location") or (dataset or {}).get("location", {}).get("name", "the region")
    phenom = understanding.get("phenomenon")
    simulated = bool((result.get("metadata") or {}).get("simulated", True))

    highlights = []
    if stats.get("affected_area_km2") is not None:
        highlights.append(
            f"Estimated {stats['affected_area_km2']:,.0f} km² of {loc} flagged "
            f"for {OP_LABELS.get(op, op)}."
        )
    if stats.get("estimated_population") is not None:
        highlights.append(
            f"Approximately {stats['estimated_population']:,} people reside in the "
            f"affected extent (based on reference density)."
        )
    if stats.get("decline") is None and stats.get("peak_date"):
        highlights.append(f"Event activity peaked around {stats['peak_date']}.")
    if stats.get("changed_area_km2") is not None:
        highlights.append(
            f"Change footprint covers {stats['changed_area_km2']:,.0f} km² "
            f"({stats.get('expansion_cells', 0)} expansion cells, "
            f"{stats.get('reduction_cells', 0)} reduction cells)."
        )
    if stats.get("linear_slope") is not None:
        highlights.append(
            f"The observed index trend is {stats['trend']} (slope "
            f"{stats['linear_slope']:+.5f}/step across {stats.get('points', 0)} samples)."
        )
    if stats.get("dominant_class"):
        highlights.append(
            f"Dominant class: {stats['dominant_class']} "
            f"({stats.get('dominant_area_km2', 0):,.0f} km²)."
        )
    if stats.get("consensus_area_km2") is not None:
        highlights.append(
            f"Multi-source consensus flagged {stats['consensus_area_km2']:,.0f} km² "
            f"across {stats.get('sources_fused', 0)} co-registered sources."
        )
    if stats.get("scenes_found") is not None:
        highlights.append(
            f"Retrieved {stats['scenes_found']} scenes from live catalogues "
            f"(sensors: {', '.join(stats.get('sensors', []))})."
        )
    if stats.get("mean_index") is not None:
        idx = stats.get("index", op.upper())
        thresh = stats.get("threshold", 0.0)
        highlights.append(
            f"Mean {idx} over the AOI is {stats['mean_index']:+.3f} "
            f"(threshold {thresh}) — {stats.get('positive_cells', 0)} of "
            f"{stats.get('total_cells', 0)} cells above the {idx} threshold."
        )
    if stats.get("mean_sigma_db") is not None:
        highlights.append(
            f"Mean SAR backscatter σ⁰ is {stats['mean_sigma_db']} dB "
            f"({stats.get('water_cells', 0)} low-σ⁰ water cells, "
            f"{stats.get('built_up_cells', 0)} high-σ⁰ built-up cells)."
        )
    if op == "image-analysis":
        kind_label = (((result.get("metadata") or {}).get("image") or {})
                      .get("kind") or {}).get("label")
        if stats.get("width"):
            highlights.append(
                f"Uploaded photo is {stats['width']}×{stats['height']} px "
                f"({stats.get('format')}) — classified as "
                f"{kind_label or 'imagery'}."
            )
        if stats.get("dominant_surface"):
            highlights.append(
                f"Approximate dominant surface in the photo: "
                f"{stats['dominant_surface']} "
                f"({format_pct(stats.get('dominant_share', 0))} of pixels)."
            )
        if (stats.get("area_by_class_km2") or {}).get("water"):
            highlights.append(
                f"Water-like pixels cover an estimated "
                f"{stats['area_by_class_km2'].get('water'):,.0f} km² of the "
                f"query AOI (photo-pixel estimate)."
            )
        if stats.get("colorfulness") is not None:
            highlights.append(
                f"Measured colourfulness {stats['colorfulness']}, texture "
                f"entropy {stats.get('texture_entropy')} — these are real "
                f"pixel statistics from your file."
            )

    narrative = _narrative(understanding, result, highlights)
    findings = [h for h in highlights] or [f"Analysis of {loc} completed."]

    return {
        "highlights": highlights or [f"Analysis of {loc} completed."],
        "narrative": narrative,
        "findings": findings,
        "confidence": result.get("confidence", 0.5),
        "agent": agent_name or "SatQuery AI",
        "simulated": simulated,
        "generated_at": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
        "disclaimer": (
            "These results are based on DEMO/simulated data and must NOT be used "
            "for operational decisions. Connect real providers for actual "
            "satellite processing." if simulated else
            "Real catalogue data used; validate derived statistics before decisions."
        ),
    }


def _narrative(understanding, result, highlights):
    op = result.get("op", "analysis")
    loc = understanding.get("location") or "the region"
    phenom = understanding.get("phenomenon")
    date_s = understanding.get("date_start") or "available period"
    date_e = understanding.get("date_end") or "recent"
    conf = result.get("confidence", 0.5)
    if op == "image-analysis":
        head = (
            f"SatQuery AI analysed your uploaded photo"
            + (f" of {loc}" if loc and loc != "the region" else "")
            + f" using the {OP_LABELS.get(op, op)} workflow."
        )
    else:
        head = f"SatQuery AI analysed {loc}"
        if phenom:
            head += f" for {phenom.replace('_', ' ')} indicators"
        head += f" between {date_s} and {date_e}"
        head += f" using the {OP_LABELS.get(op, op)} workflow."
    body = " " + " ".join(highlights) if highlights else ""
    tail = (
        f" Overall model confidence is {conf:.0%}. Data provenance is "
        f"{'simulated demo' if result.get('metadata', {}).get('simulated', True) else 'real catalogue'}."
    )
    return head + body + tail