"""Query-aware AI/VLM synthesis for change-analysis reports.

Two tiers, always honest about which one produced the output:

1. **Deterministic template** — always available; builds a structured Markdown
   report from the quantitative evidence (stats, per-technique deltas,
   hotspots, imagery provenance) and responds to the user's custom query
   prompt by selecting an interpretive lens.
2. **Vision-Language Model** — when ``CHANGE_LLM_API_KEY`` is configured, an
   OpenAI-compatible chat-completions endpoint (works with OpenAI / Azure /
   OpenRouter / local vLLM-Ollama gateways) receives the metrics JSON *and*
   the rendered heatmap + before/after composites, and returns a richer
   paragraph-level narrative. Any failure degrades silently to the template.
"""
from __future__ import annotations

import base64
from typing import Optional

from ...config import settings
from ...middleware import logger
from . import raster as rx


# ---------------------------------------------------------------------------
# Query interpretation
# ---------------------------------------------------------------------------


def interpret_query(query: str, techniques: list) -> dict:
    """Map the user's prompt to a human-readable analysis lens."""
    words = (query or "").lower()
    theme: Optional[str] = None
    for tech_key in ("ndbi", "ndwi", "ndvi"):
        if tech_key in techniques and any(
            w in words for w in rx.TECHNIQUES[tech_key]["query_words"]
        ):
            theme = rx.TECHNIQUES[tech_key]["signal"]
            break
    if theme is None:
        theme = "compound land-surface change"
    return {
        "lens": theme,
        "question": query,
        "technique_labels": [
            rx.TECHNIQUES[t]["label"] for t in techniques if t in rx.TECHNIQUES
        ],
    }


def _fmt_km2(v) -> str:
    try:
        return f"{float(v):,.3f} km²"
    except (TypeError, ValueError):
        return "—"


# ---------------------------------------------------------------------------
# Deterministic report
# ---------------------------------------------------------------------------


def build_deterministic_report(evidence: dict) -> str:
    """Render a complete Markdown analysis report from the evidence block."""
    q = interpret_query(evidence["query"], [t["id"] for t in evidence["techniques"]])
    stats = evidence["stats"]
    loc = evidence.get("location_name") or "the AOI"
    d1, d2 = evidence["date_1"], evidence["date_2"]
    inv1, inv2 = evidence.get("inventory1", {}), evidence.get("inventory2", {})
    simulated = evidence.get("simulated", True)
    gain = evidence.get("changes_summary", {}).get("gain_area_km2", 0)
    loss = evidence.get("changes_summary", {}).get("loss_area_km2", 0)

    lines = [
        f"# Historical Change Analysis — {loc}",
        "",
        f"**Period:** {d1} → {d2}  ",
        f"**Query:** “{evidence.get('query', '')}”  ",
        f"**Analysis lens:** {q['lens']}  ",
        f"**Change footprint:** {_fmt_km2(stats.get('changed_area_km2'))} "
        f"({stats.get('pct_changed', 0)}% of {_fmt_km2(stats.get('aoi_area_km2'))})",
        "",
        "## What changed",
        "",
        f"- **Net expansion / gain:** {_fmt_km2(gain)}",
        f"- **Net reduction / loss:** {_fmt_km2(loss)}",
        f"- **Hotspots detected:** {stats.get('hotspot_count', 0)} "
        "(ranked by size and intensity)",
        f"- **Mean change intensity:** {stats.get('mean_abs_heat', 0)} "
        f"(max {stats.get('max_heat', 0)})",
        f"- **Scene-level index drift:** NDVI {stats.get('net_ndvi_delta', 0):+.4f} · "
        f"NDBI {stats.get('net_ndbi_delta', 0):+.4f} · "
        f"NDWI {stats.get('net_ndwi_delta', 0):+.4f}",
        "",
        "## Evidence by technique",
        "",
        "| Technique | Threshold | Gain | Loss | Mean Δ |",
        "|---|---|---|---|---|",
    ]
    for t in evidence["techniques"]:
        lines.append(
            f"| {t['label']} | {t['threshold']} | {_fmt_km2(t['gain_km2'])} "
            f"({t['gain_cells']} px) | {_fmt_km2(t['loss_km2'])} ({t['loss_cells']} px) "
            f"| {t['mean_delta']:+.4f} |"
        )
    lines.append("")

    if evidence.get("hotspots"):
        lines += ["## Top change hotspots", ""]
        for h in evidence["hotspots"][:8]:
            c = h["center"]
            lines.append(
                f"{h['rank']}. **{h['signal'].capitalize()}** — "
                f"{_fmt_km2(h['area_km2'])} at "
                f"({c['lat']:.5f}, {c['lng']:.5f}), intensity {h['intensity']}"
            )
        lines.append("")

    lines += [
        "## Imagery provenance",
        "",
        "| Date | Source | Status |",
        "|---|---|---|",
    ]
    for inv in (inv1, inv2):
        src = ", ".join(s.get("id", "") for s in inv.get("scenes", [])) or "synthetic demo scene"
        status = "real catalog metadata" if inv.get("scenes") else "simulated (demo raster)"
        lines.append(f"| {inv.get('date', '')} | {src} | {status} |")
    lines += [
        "",
        "## Methodology",
        "",
        f"Geocoded the AOI of {_fmt_km2(stats.get('aoi_area_km2'))}, aligned "
        f"{stats.get('total_cells', 0)} raster cells, and applied "
        f"{', '.join(q['technique_labels'])} after per-date spectral-index "
        "computation. Change pixels were thresholded, clustered into hotspots "
        "with 8-connectivity, and rendered into composites, a signed heatmap "
        "and a change-intensity GeoTIFF.",
    ]
    if simulated:
        lines += [
            "",
            "> **Honesty notice:** real STAC scene metadata was retained when available, "
            "but pixel-level rasters in this demo deployment are deterministic "
            "synthetics — treat absolute areas as illustrative, not operational.",
        ]
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Optional VLM refinement
# ---------------------------------------------------------------------------


def _llm_enabled() -> bool:
    provider = (settings.CHANGE_LLM_PROVIDER or "auto").lower()
    return provider not in ("none", "off", "false", "no", "0") and bool(settings.CHANGE_LLM_API_KEY)


def _call_vision_llm(system: str, user_text: str, images: list[dict]) -> Optional[str]:
    """OpenAI-compatible chat/completions call with inline base64 images."""
    import httpx

    content: list = [{"type": "text", "text": user_text}]
    for img in images:
        content.append({"type": "image_url", "image_url": {"url": img["data_url"]}})
    payload = {
        "model": settings.CHANGE_LLM_MODEL,
        "temperature": 0.2,
        "max_tokens": 1400,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": content},
        ],
    }
    with httpx.Client(timeout=settings.CHANGE_LLM_TIMEOUT_SECONDS) as client:
        r = client.post(
            f"{settings.CHANGE_LLM_BASE_URL}/chat/completions",
            json=payload,
            headers={"Authorization": f"Bearer {settings.CHANGE_LLM_API_KEY}"},
        )
        r.raise_for_status()
        data = r.json()
        return (data["choices"][0]["message"]["content"] or "").strip()


def synthesize(evidence: dict, artifact_bytes: Optional[dict] = None) -> dict:
    """Produce ``{report_md, summary, synthesis}`` for the pipeline.

    ``artifact_bytes`` maps filenames -> PNG bytes so the vision tier can
    inspect the rendered heatmap + before/after composites.
    """
    report = build_deterministic_report(evidence)
    used_llm = False
    if _llm_enabled():
        try:
            images = []
            for fname in ("heatmap.png", "before.png", "after.png"):
                raw = (artifact_bytes or {}).get(fname)
                if raw:
                    images.append({
                        "data_url": "data:image/png;base64,"
                                    + base64.b64encode(raw).decode(),
                        "kind": fname,
                    })
            narrative = _call_vision_llm(
                system=(
                    "You are a senior remote-sensing analyst. Interpret the change "
                    "detection evidence (metrics JSON + heatmap + before/after "
                    "composites) for the user's question. Return 3-5 concise "
                    "Markdown paragraphs: what changed, how confident to be, "
                    "hotspot-level detail, and follow-up recommendations. Do NOT "
                    "invent numbers; only reference the provided metrics."
                ),
                user_text=(
                    f"Question: {evidence['query']}\n"
                    f"Location: {evidence.get('location_name')}\n"
                    f"Period: {evidence['date_1']} → {evidence['date_2']}\n"
                    f"Metrics (JSON):\n{_compact_stats(evidence)}"
                ),
                images=images,
            )
            if narrative:
                report = _insert_vlm_section(report, narrative)
                used_llm = True
        except Exception as exc:  # never break the pipeline for LLM flakiness
            logger.warning("Change-analysis VLM refinement skipped: %s", exc)

    return {
        "report_md": report,
        "summary": build_summary_block(evidence),
        "synthesis": "vision-llm" if used_llm else "deterministic-template",
    }


def _insert_vlm_section(report: str, narrative: str) -> str:
    marker = "## What changed"
    section = "## AI interpretation\n\n" + f"{narrative.strip()}\n\n---\n\n"
    if marker in report:
        return report.replace(marker, section + marker, 1)
    return report + "\n\n---\n\n" + section


def _compact_stats(evidence: dict) -> str:
    import json

    keys = (
        "changed_area_km2", "aoi_area_km2", "pct_changed", "hotspot_count",
        "mean_abs_heat", "net_ndvi_delta", "net_ndbi_delta", "net_ndwi_delta",
    )
    stats = {k: evidence["stats"].get(k) for k in keys}
    return json.dumps(
        {
            "stats": stats,
            "techniques": [
                {k: t[k] for k in ("id", "gain_km2", "loss_km2", "mean_delta")}
                for t in evidence["techniques"]
            ],
            "hotspots": evidence["hotspots"][:6],
        },
        default=str,
    )


def build_summary_block(evidence: dict) -> dict:
    """Summarizer-compatible block (highlights/narrative/findings/...)."""
    import datetime as dt

    stats = evidence["stats"]
    loc = evidence.get("location_name") or "the region"
    q = interpret_query(evidence["query"], [t["id"] for t in evidence["techniques"]])
    simulated = evidence.get("simulated", True)
    gain = evidence.get("changes_summary", {}).get("gain_area_km2", 0)
    loss = evidence.get("changes_summary", {}).get("loss_area_km2", 0)

    highlights = []
    if stats.get("changed_area_km2") is not None:
        highlights.append(
            f"Estimated {stats['changed_area_km2']:,.3f} km² of {loc} changed "
            f"({stats.get('pct_changed', 0)}% of the "
            f"{stats.get('aoi_area_km2', 0):,.2f} km² AOI)."
        )
    if gain > 0 or loss > 0:
        highlights.append(f"Net expansion ≈ {gain:,.3f} km² and net reduction ≈ {loss:,.3f} km².")
    if stats.get("hotspot_count") and evidence.get("hotspots"):
        top = evidence["hotspots"][0]
        highlights.append(
            f"{stats['hotspot_count']} change hotspot(s) clustered — the largest covers "
            f"{top['area_km2']:,.3f} km²."
        )
    highlights.append(
        f"Analysis lens: {q['lens']} (techniques: {', '.join(q['technique_labels'])})."
    )
    narrative = (
        f"SatQuery AI compared {evidence['date_1']} and {evidence['date_2']} over {loc}, "
        f"answering “{evidence.get('query', '')}”. The change signal is dominated by "
        f"{q['lens']}; pixel statistics were computed over a "
        f"{stats.get('total_cells', 0)}-cell raster grid."
    )
    return {
        "highlights": highlights,
        "narrative": narrative,
        "findings": highlights,
        "confidence": 0.6 if simulated else 0.75,
        "agent": "Change-Analysis (vision)" if _llm_enabled() else "Change-Analysis (template)",
        "simulated": simulated,
        "generated_at": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
        "disclaimer": (
            "Pixel rasters are deterministic simulated scenes in this deployment — "
            "validate against real imagery before operational use." if simulated else
            "Real catalogue metadata retained; validate derived statistics before decisions."
        ),
    }