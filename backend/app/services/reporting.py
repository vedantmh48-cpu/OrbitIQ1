"""Report generation: GeoJSON, CSV, Markdown/HTML, PDF (reportlab) and a
Google-Docs-compatible DOCX export (pure OOXML via the standard library)."""
from __future__ import annotations

import base64
import csv
import html as _html
import io
import json
import zipfile
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path

from ..storage import datetime_now

# Brand artwork shipped with the API: inlined into the HTML export and placed on
# the first page of the PDF export. Every use degrades gracefully to text when
# the asset is unavailable, so exports never fail because of branding.
LOGO_PATH = Path(__file__).resolve().parent.parent / "assets" / "logo.png"


@lru_cache(maxsize=1)
def _logo_data_uri() -> str | None:
    """Base64 data URI of the logo, or ``None`` when the asset is missing."""
    try:
        raw = LOGO_PATH.read_bytes()
    except OSError:
        return None
    return "data:image/png;base64," + base64.b64encode(raw).decode("ascii")


def report_brand_html() -> str:
    """Header brand block: the logo artwork when present, text otherwise."""
    data_uri = _logo_data_uri()
    if data_uri:
        return f'<img class="brand-logo" src="{data_uri}" alt="SatQuery AI">'
    return '<div class="brand">&#128752; SatQuery AI</div>'

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
    "real-events": "live observations",
}


def _simulated(result: dict) -> bool:
    return bool((result.get("metadata") or {}).get("simulated", True))


def _fmt(value) -> str:
    if isinstance(value, float):
        if abs(value) >= 1000:
            return f"{value:,.1f}"
        return f"{value:.3f}".rstrip("0").rstrip(".")
    if isinstance(value, bool):
        return "Yes" if value else "No"
    return str(value)


def _stats_rows(result: dict, max_depth: int = 1) -> list[tuple[str, str]]:
    """Flatten the stats dict into printable (label, value) pairs."""
    out: list[tuple[str, str]] = []
    stats = result.get("stats", {}) or {}
    for k, v in stats.items():
        label = k.replace("_", " ").title()
        if isinstance(v, dict) and max_depth > 0:
            for kk, vv in v.items():
                out.append((f"{label} · {kk.replace('_', ' ').title()}", _fmt(vv)))
        elif isinstance(v, (list, tuple)):
            out.append((label, ", ".join(str(x) for x in v[:6])))
        elif v is None:
            continue
        else:
            out.append((label, _fmt(v)))
    return out


def _bucket_summary(result: dict) -> dict:
    """Content shared by markdown / html / pdf / docx exporters."""
    understanding = result.get("understanding", {}) or {}
    sim = _simulated(result)
    return {
        "title": result.get("label") or "SatQuery Analysis",
        "op": result.get("op"),
        "op_label": OP_LABELS.get(result.get("op"), result.get("op") or "analysis"),
        "model": (result.get("metadata") or {}).get("model", "—"),
        "satellite": (result.get("metadata") or {}).get("satellite", "—"),
        "data_type": (result.get("metadata") or {}).get("data_type", "—"),
        "resolution": (result.get("metadata") or {}).get("resolution", "—"),
        "source": (result.get("metadata") or {}).get("source", "—"),
        "confidence": result.get("confidence", 0.0),
        "simulated": sim,
        "created_at": result.get("created_at") or datetime_now(),
        "location": understanding.get("location") or "the region",
        "date_start": understanding.get("date_start") or "available period",
        "date_end": understanding.get("date_end") or "recent",
        "phenomenon": (understanding.get("phenomenon") or "—").replace("_", " ").title(),
        "query": (understanding.get("query_text") or result.get("query_text") or ""),
        "narrative": (result.get("summary") or {}).get("narrative", "Analysis complete."),
        "highlights": (result.get("summary") or {}).get("highlights", []),
        "findings": (result.get("summary") or {}).get("findings", []),
        "stats": _stats_rows(result),
        "feature_count": len((result.get("geojson") or {}).get("features", [])),
        "verification": result.get("verification", {}),
        "execution_trace": result.get("execution_trace") or {},
        "modality": result.get("modality") or {},
    }

# ---------------------------------------------------------------------------
# GeoJSON / CSV
# ---------------------------------------------------------------------------


def build_geojson(result: dict) -> dict:
    """Enrich the result GeoJSON with metadata (exportable file)."""
    geojson = result.get("geojson") or {"type": "FeatureCollection", "features": []}
    geojson["properties"] = {
        **(geojson.get("properties") or {}),
        "created_by": "SatQuery AI",
        "generated_at": datetime_now(),
        "op": result.get("op"),
        "label": result.get("label"),
        "confidence": result.get("confidence"),
        "query": (result.get("understanding") or {}).get("query_text", ""),
        "simulated": _simulated(result),
        "stats": result.get("stats", {}),
    }
    return geojson


def geojson_bytes(result: dict) -> bytes:
    return json.dumps(build_geojson(result), indent=2, default=str).encode("utf-8")


def csv_bytes(result: dict) -> bytes:
    stats = result.get("stats", {})
    out = io.StringIO()
    writer = csv.writer(out)
    writer.writerow(["metric", "value"])
    for k, v in stats.items():
        if isinstance(v, dict):
            for kk, vv in v.items():
                writer.writerow([f"{k}.{kk}", vv])
        elif isinstance(v, (list, tuple)):
            writer.writerow([k, ", ".join(str(x) for x in v)])
        elif v is not None:
            writer.writerow([k, v])
    writer.writerow([])
    writer.writerow(["feature_index", "type", "lat", "lng", "value", "class"])
    features = (result.get("geojson") or {}).get("features", [])
    for i, f in enumerate(features):
        props = f.get("properties", {}) or {}
        geom = f.get("geometry", {})
        coords = geom.get("coordinates")
        writer.writerow(
            [
                i,
                geom.get("type", ""),
                props.get("lat"),
                props.get("lng"),
                props.get("value"),
                props.get("class", ""),
            ]
        )
    return out.getvalue().encode("utf-8")
# ---------------------------------------------------------------------------
# Markdown
# ---------------------------------------------------------------------------


def markdown_report(result: dict, summary: dict, understanding: dict, dataset: dict | None = None) -> str:
    ctx = _bucket_summary(result)
    sim = ctx["simulated"]
    lines = [
        f"# SatQuery AI — {ctx['title']}",
        "",
        f"**Generated:** {ctx['created_at'].replace('T', ' ')[:19]} UTC  ",
        f"**Workflow:** {ctx['title']}  ",
        f"**Model:** {ctx['model']}  ",
        f"**Confidence:** {ctx['confidence']:.0%}  ",
        f"**Area of interest:** {ctx['location']}  ",
        f"**Period:** {ctx['date_start']} → {ctx['date_end']}  ",
        f"**Features:** {ctx['feature_count']}  ",
        f"**Provenance:** {'⚠ Demo / simulated' if sim else 'Real catalogue'}",
        "",
    ]
    if ctx["query"]:
        lines += ["---", "", "## Original query", "", f"> {ctx['query']}", ""]
    lines += ["## Executive summary", "", ctx["narrative"], ""]
    if ctx["findings"]:
        lines += ["### Key findings", ""]
        lines += [f"- {h}" for h in ctx["findings"]]
        lines += [""]
    elif ctx["highlights"]:
        lines += ["### Key findings", ""]
        lines += [f"- {h}" for h in ctx["highlights"]]
        lines += [""]
    # --- execution trace (modality + multi-tool chain) ---
    trace = ctx.get("execution_trace") or {}
    modality = ctx.get("modality") or {}
    if modality or trace.get("steps"):
        lines += ["## Execution trace", ""]
        lines += [f"- **Target task:** {trace.get('target_task') or ctx['title']}"]
        if modality.get("label"):
            lines += [f"- **Modality:** {modality.get('label')}"]
        if modality.get("sensors"):
            lines += [f"- **Sensors:** {', '.join(modality.get('sensors'))}"]
        if trace.get("uncertainties"):
            lines += ["", "### Uncertainty & limitations"]
            lines += [f"- {u}" for u in trace["uncertainties"]]
        steps = trace.get("steps") or []
        if steps:
            lines += ["", "### Tool chain", ""]
            for s in steps:
                ok = "✓" if s.get("result") is not None else "✕"
                lines += [f"- {ok} **Step {s.get('step')} — {s.get('tool')}:** {s.get('detail')}"]
                if s.get("result"):
                    lines += [f"  - Features: {s['result'].get('features', 0)} · {s['result'].get('label', '')}"]
        lines += [""]
    if ctx["stats"]:
        lines += ["## Key statistics", "", "| Metric | Value |", "| --- | --- |"]
        lines += [f"| {_esc_md(k)} | {_esc_md(v)} |" for k, v in ctx["stats"]]
        lines += [""]
    checks = ctx["verification"].get("checks", [])
    if checks:
        lines += ["## Verification", ""]
        for c in checks:
            icon = {"passed": "✅", "warning": "⚠️", "failed": "❌"}.get(c.get("level"), "•")
            lines.append(f"- {icon} **{c.get('name')}:** {c.get('detail')}")
        lines += [""]
    lines += [
        "## Methodology",
        "",
        "1. **Query understanding** — natural-language parsing into location / time / "
        "phenomenon / data-type slots.",
        "2. **Agent selection** — automatic model routing (SAR / Optical / Temporal / Fusion).",
        "3. **Data retrieval** — provider adapters (demo, STAC, Sentinel, Landsat, live feeds).",
        "4. **Spatial & temporal analysis** — feature extraction over the area of interest.",
        "5. **Verification** — geometric, statistical and provenance checks.",
        "6. **AI summary** — deterministic explainer over the computed statistics.",
        "",
    ]
    if sim:
        lines.append(
            "> **Important:** this report used DEMO simulated data and is illustrative only. "
            "Connect real providers for operational analysis."
        )
    else:
        lines.append("> Generated from real catalogue data; validate derived statistics before decisions.")
    return "\n".join(lines)


def _esc_md(value: str) -> str:
    return str(value).replace("|", "\\|").replace("\n", " ")
# ---------------------------------------------------------------------------
# HTML (self-contained, print-friendly)
# ---------------------------------------------------------------------------


def html_report(result: dict, summary: dict, understanding: dict) -> str:
    ctx = _bucket_summary(result)
    sim = ctx["simulated"]
    rows = "".join(
        f"<tr><td>{_html.escape(k)}</td><td class='num'>{_html.escape(v)}</td></tr>"
        for k, v in ctx["stats"]
    ) or "<tr><td colspan='2'>No statistics recorded.</td></tr>"
    checks_html = ""
    for c in ctx["verification"].get("checks", []):
        lvl = c.get("level", "passed")
        icon = {"passed": "✓", "warning": "!", "failed": "✕"}.get(lvl, "•")
        checks_html += (
            f"<li class='check {lvl}'><b>{icon} {_html.escape(c.get('name',''))}</b> — "
            f"{_html.escape(c.get('detail',''))}</li>"
        )
    highlights = "".join(f"<li>{_html.escape(h)}</li>" for h in ctx["highlights"]) if ctx["highlights"] else ""
    findings = "".join(f"<li>{_html.escape(h)}</li>" for h in ctx["findings"]) if ctx["findings"] else ""
    trace = ctx.get("execution_trace") or {}
    modality = ctx.get("modality") or {}
    steps_html = ""
    for s in (trace.get("steps") or []):
        ok = "✓" if s.get("result") is not None else "✕"
        steps_html += (f"<li><b>{ok} Step {s.get('step')} — {_html.escape(str(s.get('tool','')))}:</b> "
                       f"{_html.escape(str(s.get('detail','')))}</li>")
    trace_html = ""
    if modality or steps_html or trace.get("uncertainties"):
        trace_html = "<section><h2>Execution trace</h2><table class='meta'><tbody>"
        trace_html += f"<tr><th>Target task</th><td>{_html.escape(str(trace.get('target_task') or ctx['title']))}</td></tr>"
        if modality.get("label"):
            trace_html += f"<tr><th>Modality</th><td>{_html.escape(str(modality.get('label'))) }</td></tr>"
        if modality.get("sensors"):
            trace_html += f"<tr><th>Sensors</th><td>{_html.escape(', '.join(map(str, modality.get('sensors'))))}</td></tr>"
        trace_html += "</tbody></table>"
        if steps_html:
            trace_html += f"<ul class='checks'>{steps_html}</ul>"
        if trace.get("uncertainties"):
            trace_html += "<h3>Uncertainty &amp; limitations</h3><ul>"
            trace_html += "".join(f"<li>{_html.escape(u)}</li>" for u in trace["uncertainties"])
            trace_html += "</ul>"
        trace_html += "</section>"
    banner = (
        "<div class='banner warn'><b>Data-provenance notice:</b> this analysis used "
        "<b>DEMO / simulated</b> data and is illustrative only.</div>"
        if sim else
        "<div class='banner ok'>Real catalogue data was used.</div>"
    )
    css = _REPORT_CSS
    brand = report_brand_html()
    page = f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<title>SatQuery AI — {_html.escape(ctx['title'])}</title>
<style>{css}</style></head><body>
<div class="page">
  <header>
    {brand}
    <div class="doc-title">{_html.escape(ctx['title'])}</div>
    <div class="meta">
      Generated {_html.escape(ctx['created_at'].replace('T',' ')[:16])} UTC ·
      Confidence <b>{ctx['confidence']:.0%}</b> ·
      {_html.escape(str(ctx['feature_count']))} features
    </div>
    {banner}
  </header>
  {f'<section><h2>Original query</h2><p class="query">{_html.escape(ctx["query"]) or "—"}</p></section>' if ctx["query"] else ''}
  <section>
    <h2>Executive summary</h2>
    <p>{_html.escape(ctx['narrative'])}</p>
    {f"<ul class='highlights'>{findings or highlights}</ul>" if (findings or highlights) else ""}
  </section>
  {trace_html}
  <section>
    <h2>Key statistics</h2>
    <table><thead><tr><th>Metric</th><th>Value</th></tr></thead><tbody>{rows}</tbody></table>
  </section>
  <section>
    <h2>Analysis metadata</h2>
    <table class="meta"><tbody>
      <tr><th>Model</th><td>{_html.escape(ctx['model'])}</td></tr>
      <tr><th>Satellite</th><td>{_html.escape(ctx['satellite'])}</td></tr>
      <tr><th>Data type</th><td>{_html.escape(ctx['data_type'])}</td></tr>
      <tr><th>Resolution</th><td>{_html.escape(ctx['resolution'])}</td></tr>
      <tr><th>Source</th><td>{_html.escape(ctx['source'])}</td></tr>
      <tr><th>Area of interest</th><td>{_html.escape(ctx['location'])}</td></tr>
      <tr><th>Period</th><td>{_html.escape(ctx['date_start'])} → {_html.escape(ctx['date_end'])}</td></tr>
    </tbody></table>
  </section>
  {f"<section><h2>Verification report</h2><ul class='checks'>{checks_html}</ul></section>" if checks_html else ""}
  <section><h2>Methodology</h2>
    <ol>
      <li>Natural-language query understanding into structured slots.</li>
      <li>Automatic AI agent selection (SAR / Optical / Temporal / Fusion).</li>
      <li>Data retrieval through provider adapters.</li>
      <li>Spatial &amp; temporal feature extraction over the AOI.</li>
      <li>Geometric, statistical and provenance verification.</li>
      <li>Deterministic AI summary of computed statistics.</li>
    </ol>
  </section>
  <footer>Generated by SatQuery AI · {_html.escape(ctx['created_at'][:10])} · The map, charts and GeoJSON for this analysis are available in the web app.</footer>
</div></body></html>"""
    return page


_REPORT_CSS = """
  :root { color-scheme: light; }
  * { box-sizing: border-box; }
  body { font-family:'Segoe UI', system-ui, -apple-system, sans-serif; background:#f1f5f9; margin:0; color:#0f172a; }
  .page { max-width:820px; margin:0 auto; background:#fff; padding:40px 48px; min-height:100vh; }
  header { border-bottom:3px solid #0891b2; padding-bottom:14px; margin-bottom:22px; }
  .brand { color:#0891b2; font-weight:800; letter-spacing:.4px; }
  .brand span { color:#0f172a; }
  .brand-logo { display:block; height:44px; width:auto; margin-bottom:8px; border-radius:6px; }
  .doc-title { font-size:26px; font-weight:800; margin-top:8px; letter-spacing:-.3px; }
  .meta { color:#64748b; font-size:12.5px; margin-top:6px; }
  .banner { border-radius:10px; padding:10px 14px; font-size:13px; margin-top:12px; }
  .banner.warn { background:#fef3c7; border:1px solid #f59e0b; color:#92400e; }
  .banner.ok { background:#d1fae5; border:1px solid #10b981; color:#065f46; }
  h2 { color:#0e7490; font-size:17px; margin:24px 0 10px; border-bottom:1px solid #e2e8f0; padding-bottom:6px; }
  .query { background:#f8fafc; border-left:3px solid #0891b2; padding:10px 14px; border-radius:6px; color:#334155; font-style:italic; }
  p { line-height:1.65; color:#334155; }
  table { width:100%; border-collapse:collapse; font-size:13px; }
  th { background:#0e7490; color:#fff; text-align:left; padding:8px 10px; }
  td { padding:7px 10px; border-bottom:1px solid #e2e8f0; }
  tr:nth-child(even) td { background:#f8fafc; }
  td.num { font-weight:600; font-variant-numeric:tabular-nums; }
  ul.checks { list-style:none; padding:0; }
  .check { padding:7px 10px; border-radius:8px; margin:5px 0; font-size:13px; }
  .check.passed { background:#ecfdf5; color:#065f46; }
  .check.warning { background:#fffbeb; color:#92400e; }
  .check.failed { background:#fef2f2; color:#991b1b; }
  footer { margin-top:34px; padding-top:12px; border-top:1px solid #e2e8f0; color:#94a3b8; font-size:11.5px; }
  @media print { body { background:#fff; } .page { max-width:none; padding:20px; } }
"""
# ---------------------------------------------------------------------------
# PDF (reportlab)
# ---------------------------------------------------------------------------


def _esc_pdf(value: str) -> str:
    return str(value).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def pdf_bytes(result: dict, summary: dict, understanding: dict) -> bytes | None:
    """ReportLab-based PDF; returns None when the optional library is missing."""
    try:
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
        from reportlab.lib.units import mm
        from reportlab.lib import colors
        from reportlab.platypus import (
            Image as ReportImage, Paragraph, SimpleDocTemplate, Spacer, Table,
            TableStyle, ListFlowable, ListItem,
        )
    except Exception:
        return None

    ctx = _bucket_summary(result)
    sim = ctx["simulated"]
    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=A4, leftMargin=20 * mm, rightMargin=20 * mm,
        topMargin=18 * mm, bottomMargin=18 * mm,
        title=f"SatQuery AI — {ctx['title']}",
        author="SatQuery AI",
    )
    styles = getSampleStyleSheet()
    TEAL = colors.HexColor("#0e7490")
    GREY = colors.HexColor("#64748b")
    title = ParagraphStyle("TitleX", parent=styles["Title"], textColor=TEAL, fontSize=22, spaceAfter=2)
    h2 = ParagraphStyle("H2X", parent=styles["Heading2"], textColor=TEAL, fontSize=13, spaceBefore=10, spaceAfter=5)
    body = ParagraphStyle("BodyX", parent=styles["BodyText"], fontSize=9.5, leading=14, textColor=colors.HexColor("#0f172a"))
    small = ParagraphStyle("SmallX", parent=styles["BodyText"], fontSize=8, leading=11, textColor=GREY)
    mono = ParagraphStyle("MonoX", parent=body, fontName="Courier", fontSize=8.5)

    # Brand logo on page 1. The artwork is a transparent PNG, which ``reportlab``
    # only decodes (through Pillow) while it is being drawn, so the asset is
    # probed eagerly here: a missing or unreadable artwork degrades to a
    # text-only report instead of failing the whole PDF export.
    brand_block: list = []
    try:
        from reportlab.lib.utils import ImageReader

        ImageReader(str(LOGO_PATH)).getSize()
        brand_block = [
            ReportImage(str(LOGO_PATH), width=51 * mm, height=17 * mm),
            Spacer(1, 3 * mm),
        ]
    except Exception:
        brand_block = []

    story = [
        *brand_block,
        Paragraph(f"SatQuery AI — {_esc_pdf(ctx['title'])}", title),
        Paragraph(
            f"Generated {ctx['created_at'].replace('T', ' ')[:19]} UTC · Confidence "
            f"<b>{ctx['confidence']:.0%}</b> · {ctx['feature_count']} features", small),
        Spacer(1, 3 * mm),
    ]
    if sim:
        story.append(Paragraph(
            "<b>&#9888; Data-provenance notice:</b> this analysis used DEMO / simulated data "
            "and is illustrative only.", ParagraphStyle("Warn", parent=body, textColor=colors.HexColor("#92400e"),
            backColor=colors.HexColor("#fef3c7"), borderPadding=5)))
    else:
        story.append(Paragraph(
            "Real catalogue data was used; validate derived statistics before decisions.",
            ParagraphStyle("Ok", parent=body, textColor=colors.HexColor("#065f46"),
            backColor=colors.HexColor("#d1fae5"), borderPadding=5)))

    if ctx["query"]:
        story += [Spacer(1, 2 * mm), Paragraph("Original query", h2),
                  Paragraph(_esc_pdf(ctx["query"]), mono)]

    story += [Paragraph("Executive summary", h2),
              Paragraph(_esc_pdf(ctx["narrative"]), body)]
    if ctx["highlights"]:
        story += [Paragraph("Key findings", h2),
                  ListFlowable(
                      [ListItem(Paragraph(_esc_pdf(h), body), leftIndent=6) for h in ctx["highlights"]],
                      bulletType="bullet", start="•")]

    trace = ctx.get("execution_trace") or {}
    modality = ctx.get("modality") or {}
    if modality or trace.get("steps") or trace.get("uncertainties"):
        story.append(Paragraph("Execution trace", h2))
        if modality.get("label"):
            story.append(Paragraph(f"<b>Modality:</b> {_esc_pdf(str(modality.get('label')))}", body))
        if modality.get("sensors"):
            story.append(Paragraph(f"<b>Sensors:</b> {_esc_pdf(', '.join(map(str, modality.get('sensors'))))}", small))
        for s in (trace.get("steps") or []):
            ok = "✓" if s.get("result") is not None else "✕"
            story.append(Paragraph(
                f"<b>{ok} Step {s.get('step')} — {_esc_pdf(str(s.get('tool','')))}</b> — "
                f"{_esc_pdf(str(s.get('detail','')))}", small))
        if trace.get("uncertainties"):
            story.append(Paragraph("Uncertainty & limitations", h2))
            story.extend(Paragraph(f"• {_esc_pdf(u)}", small) for u in trace["uncertainties"])

    if ctx["stats"]:
        data = [["Metric", "Value"]] + [[k, v] for k, v in ctx["stats"]]
        table = Table(data, colWidths=[95 * mm, 55 * mm],
                      repeatRows=1,
                      splitByRow=1)
        table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), TEAL),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, -1), 8),
            ("GRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#cbd5e1")),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.HexColor("#f8fafc"), colors.white]),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("TOPPADDING", (0, 0), (-1, -1), 3),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ]))
        story += [Paragraph("Key statistics", h2), table]

    checks = ctx["verification"].get("checks", [])
    if checks:
        story.append(Paragraph("Verification report", h2))
        for c in checks:
            lvl = c.get("level", "passed")
            icon = {"passed": "&#10003;", "warning": "&#9888;", "failed": "&#10007;"}.get(lvl, "•")
            color = {"passed": "#065f46", "warning": "#92400e", "failed": "#991b1b"}.get(lvl, "#334155")
            story.append(Paragraph(
                f"<font color='{color}'><b>{icon} {_esc_pdf(c.get('name',''))}</b></font>"
                f" — {_esc_pdf(c.get('detail',''))}", small))

    story += [
        Paragraph("Methodology", h2),
        ListFlowable(
            [ListItem(Paragraph(t, body), leftIndent=4) for t in [
                "Natural-language query understanding into structured slots.",
                "Automatic AI agent selection (SAR / Optical / Temporal / Fusion).",
                "Data retrieval through provider adapters.",
                "Spatial & temporal feature extraction over the AOI.",
                "Geometric, statistical and provenance verification.",
                "Deterministic AI summary of computed statistics.",
            ]],
            bulletType="1"),
        Spacer(1, 4 * mm),
        Paragraph(f"Generated by SatQuery AI · {ctx['created_at'][:10]} · Open the web app for the interactive map and charts.", small),
    ]
    doc.build(story)
    return buf.getvalue()
# ---------------------------------------------------------------------------
# DOCX (Google Docs / MS Word compatible) — pure OOXML, no external deps
# ---------------------------------------------------------------------------


def docx_bytes(result: dict, summary: dict, understanding: dict) -> bytes:
    ctx = _bucket_summary(result)
    sim = ctx["simulated"]

    def _xml(v) -> str:
        return str(v).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

    paras = []
    paras.append(
        '<w:p><w:pPr><w:pStyle w:val="Title"/></w:pPr><w:r><w:t>SatQuery AI — %s</w:t></w:r></w:p>'
        % _xml(ctx["title"])
    )
    paras.append(
        '<w:p><w:pPr><w:rPr><w:i/><w:sz w:val="18"/></w:rPr></w:pPr><w:r><w:t xml:space="preserve">'
        f"Generated {_xml(ctx['created_at'].replace('T', ' ')[:19])} UTC · Confidence "
        f"{ctx['confidence']:.0%} · {ctx['feature_count']} features"
        "</w:t></w:r></w:p>"
    )
    if sim:
        paras.append(
            '<w:p><w:pPr><w:shd w:val="clear" w:color="auto" w:fill="FEF3C7"/></w:pPr>'
            '<w:r><w:b>&#9888; Data-provenance notice:</w:b>'
            '<w:t xml:space="preserve"> this analysis used DEMO / simulated data and is illustrative only.</w:t></w:r></w:p>'
        )
    else:
        paras.append(
            '<w:p><w:pPr><w:shd w:val="clear" w:color="auto" w:fill="D1FAE5"/></w:pPr>'
            '<w:r><w:b>Real catalogue data.</w:b>'
            '<w:t xml:space="preserve"> Validate derived statistics before decisions.</w:t></w:r></w:p>'
        )
    if ctx["query"]:
        paras.append(
            '<w:p><w:pPr><w:pStyle w:val="Quote"/></w:pPr><w:r><w:t xml:space="preserve">'
            f"{_xml(ctx['query'])}</w:t></w:r></w:p>"
        )
    paras.append(
        '<w:p><w:pPr><w:pStyle w:val="Heading1"/></w:pPr><w:r><w:t>Executive summary</w:t></w:r></w:p>'
    )
    paras.append(
        '<w:p><w:r><w:t xml:space="preserve">' + _xml(ctx["narrative"]) + "</w:t></w:r></w:p>"
    )
    if ctx["highlights"]:
        paras.append(
            '<w:p><w:pPr><w:pStyle w:val="Heading2"/></w:pPr><w:r><w:t>Key findings</w:t></w:r></w:p>'
        )
        for h in ctx["highlights"]:
            paras.append(
                f'<w:p><w:pPr><w:ind w:left="360"/></w:pPr><w:r><w:t>{_xml(h)}</w:t></w:r></w:p>'
            )
    trace = ctx.get("execution_trace") or {}
    modality = ctx.get("modality") or {}
    if modality or trace.get("steps") or trace.get("uncertainties"):
        paras.append(
            '<w:p><w:pPr><w:pStyle w:val="Heading1"/></w:pPr><w:r><w:t>Execution trace</w:t></w:r></w:p>'
        )
        if modality.get("label"):
            paras.append(f'<w:p><w:r><w:b>Modality:</w:b><w:t xml:space="preserve"> {_xml(modality.get("label"))}</w:t></w:r></w:p>')
        if modality.get("sensors"):
            paras.append(f'<w:p><w:r><w:b>Sensors:</w:b><w:t xml:space="preserve"> {_xml(", ".join(map(str, modality.get("sensors"))))}</w:t></w:r></w:p>')
        for s in (trace.get("steps") or []):
            ok = "✓" if s.get("result") is not None else "✕"
            paras.append(
                f'<w:p><w:pPr><w:ind w:left="360"/></w:pPr><w:r><w:t xml:space="preserve">{ok} Step {_xml(str(s.get("step","")))} — {_xml(str(s.get("tool","")))}: {_xml(str(s.get("detail","")))}</w:t></w:r></w:p>'
            )
        if trace.get("uncertainties"):
            paras.append(
                '<w:p><w:pPr><w:pStyle w:val="Heading2"/></w:pPr><w:r><w:t>Uncertainty &amp; limitations</w:t></w:r></w:p>'
            )
            for u in trace["uncertainties"]:
                paras.append(f'<w:p><w:pPr><w:ind w:left="360"/></w:pPr><w:r><w:t>{_xml(u)}</w:t></w:r></w:p>')
    paras.append(
        '<w:p><w:pPr><w:pStyle w:val="Heading1"/></w:pPr><w:r><w:t>Key statistics</w:t></w:r></w:p>'
    )
    if ctx["stats"]:
        def cell(text, fill=""):
            shd = f'<w:tcPr><w:shd w:val="clear" w:color="auto" w:fill="{fill}"/></w:tcPr>' if fill else "<w:tcPr/>"
            return f'<w:tc>{shd}<w:p><w:r><w:t xml:space="preserve">{_xml(text)}</w:t></w:r></w:p></w:tc>'

        header = "".join(cell(h, "0E7490") for h in ("Metric", "Value"))
        rows = "".join(f"<w:tr>{header}</w:tr>" + "".join(
            f"<w:tr>{cell(k)}{cell(v)}</w:tr>" for k, v in ctx["stats"]
        ))
        paras.append('<w:tbl><w:tblPr><w:tblStyle w:val="TableGrid"/><w:tblW w:w="0" w:type="auto"/></w:tblPr>' + rows + "</w:tbl>")
    else:
        paras.append("<w:p><w:r><w:t>No statistics recorded.</w:t></w:r></w:p>")

    checks = ctx["verification"].get("checks", [])
    if checks:
        paras.append(
            '<w:p><w:pPr><w:pStyle w:val="Heading1"/></w:pPr><w:r><w:t>Verification report</w:t></w:r></w:p>'
        )
        for c in checks:
            paras.append(
                f'<w:p><w:pPr><w:ind w:left="360"/></w:pPr><w:r><w:b>{_xml(c.get("name",""))}:</w:b>'
                f'<w:t xml:space="preserve"> {_xml(c.get("detail",""))}</w:t></w:r></w:p>'
            )
    paras.append(
        '<w:p><w:pPr><w:pStyle w:val="Heading1"/></w:pPr><w:r><w:t>Methodology</w:t></w:r></w:p>'
    )
    steps = [
        "Natural-language query understanding into structured slots.",
        "Automatic AI agent selection (SAR / Optical / Temporal / Fusion).",
        "Data retrieval through provider adapters.",
        "Spatial & temporal feature extraction over the AOI.",
        "Geometric, statistical and provenance verification.",
        "Deterministic AI summary of computed statistics.",
    ]
    for i, s in enumerate(steps, 1):
        paras.append(
            f'<w:p><w:pPr><w:ind w:left="360"/></w:pPr><w:r><w:t xml:space="preserve">{i}. {_xml(s)}</w:t></w:r></w:p>'
        )
    if sim:
        paras.append(
            '<w:p><w:r><w:i><w:t xml:space="preserve">Important: this report used DEMO simulated data '
            "and is illustrative only. Connect real providers for operational analysis.</w:t></w:i></w:r></w:p>"
        )
    body_xml = "".join(paras)
    document_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
        f"<w:body>{body_xml}"
        '<w:sectPr><w:pgSz w:w="11906" w:h="16838"/><w:pgMar w:top="1134" w:right="1134" w:bottom="1134" w:left="1134"/></w:sectPr>'
        "</w:body></w:document>"
    )
    content_types = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
        '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
        '<Default Extension="xml" ContentType="application/xml"/>'
        f'<Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>'
        f'<Override PartName="/word/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.styles+xml"/>'
        '<Override PartName="/docProps/core.xml" ContentType="application/vnd.openxmlformats-package.core-properties+xml"/>'
        "</Types>"
    )
    rels = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>'
        '<Relationship Id="rId2" Type="http://schemas.openxmlformats.org/package/2006/relationships/metadata/core-properties" Target="docProps/core.xml"/>'
        "</Relationships>"
    )
    styles_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<w:styles xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
        '<w:style w:type="paragraph" w:styleId="Title"><w:name w:val="Title"/><w:pPr><w:spacing w:after="240"/></w:pPr>'
        '<w:rPr><w:b/><w:color w:val="0E7490"/><w:sz w:val="36"/></w:rPr></w:style>'
        '<w:style w:type="paragraph" w:styleId="Heading1"><w:name w:val="heading 1"/><w:pPr><w:keepNext/><w:spacing w:before="240" w:after="120"/><w:outlineLvl w:val="0"/></w:pPr>'
        '<w:rPr><w:b/><w:color w:val="0E7490"/><w:sz w:val="28"/></w:rPr></w:style>'
        '<w:style w:type="paragraph" w:styleId="Heading2"><w:name w:val="heading 2"/><w:pPr><w:keepNext/><w:spacing w:before="200" w:after="100"/><w:outlineLvl w:val="1"/></w:pPr>'
        '<w:rPr><w:b/><w:color w:val="155E75"/><w:sz w:val="24"/></w:rPr></w:style>'
        '<w:style w:type="paragraph" w:styleId="Quote"><w:name w:val="Quote"/><w:pPr><w:ind w:left="360"/><w:spacing w:before="120" w:after="120"/></w:pPr>'
        '<w:rPr><w:i/><w:color w:val="64748B"/></w:rPr></w:style>'
        '<w:style w:type="table" w:styleId="TableGrid"><w:name w:val="Table Grid"/><w:tblPr><w:tblBorders>'
        '<w:top w:val="single" w:sz="4" w:color="CBD5E1"/><w:left w:val="single" w:sz="4" w:color="CBD5E1"/>'
        '<w:bottom w:val="single" w:sz="4" w:color="CBD5E1"/><w:right w:val="single" w:sz="4" w:color="CBD5E1"/>'
        '<w:insideH w:val="single" w:sz="4" w:color="CBD5E1"/><w:insideV w:val="single" w:sz="4" w:color="CBD5E1"/>'
        "</w:tblBorders></w:tblPr></w:style>"
        '<w:style w:type="paragraph" w:default="1" w:styleId="Normal"><w:name w:val="Normal"/><w:rPr><w:sz w:val="22"/></w:rPr></w:style>'
        "</w:styles>"
    )
    core = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<cp:coreProperties xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/core-properties" '
        'xmlns:dc="http://purl.org/dc/elements/1.1/" xmlns:dcterms="http://purl.org/dc/terms/" '
        'xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">'
        f"<dc:title>{_xml(ctx['title'])}</dc:title><dc:creator>SatQuery AI</dc:creator>"
        f"<dcterms:created xsi:type=\"dcterms:W3CDTF\">{datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')}</dcterms:created>"
        "</cp:coreProperties>"
    )

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("[Content_Types].xml", content_types)
        zf.writestr("_rels/.rels", rels)
        zf.writestr("word/document.xml", document_xml)
        zf.writestr("word/styles.xml", styles_xml)
        zf.writestr("docProps/core.xml", core)
    return buf.getvalue()