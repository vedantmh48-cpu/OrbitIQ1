"""Change-analysis engine: scenes -> techniques -> stats, charts, artifacts.

Wires together the raster engine, the technique catalogue and a GeoJSON
detector grid. Produces per-technique statistics (gain/loss areas, mean
deltas), clustered **hotspots** (top change locations), before/after
composites, a signed direction heatmap, an unsigned magnitude overlay, a
change-mask overlay and a change-intensity GeoTIFF, plus an honest provenance
block that states whether pixel output is simulated.
"""
from __future__ import annotations

import math
from datetime import date
from pathlib import Path
from typing import Optional

from ...geo import as_feature_collection
from . import raster as rx
from .geocoding import grid_params


# ---------------------------------------------------------------------------
# Query interpretation -> technique selection
# ---------------------------------------------------------------------------


def select_techniques(query: str, requested: Optional[list] = None) -> list:
    """Choose change-detection techniques from the user's query prompt."""
    if requested:
        chosen = [t for t in requested if t in rx.TECHNIQUES]
        if not chosen:
            chosen = ["ndvi", "ndbi", "ndwi"]
        out = list(dict.fromkeys(chosen))
        return out + ["cva"] if "cva" not in out else out
    words = (query or "").lower()
    scored = sorted(
        (
            (
                sum(1 for w in spec["query_words"] if w in words),
                tech,
            )
            for tech, spec in rx.TECHNIQUES.items()
            if tech != "cva"
        ),
        key=lambda kv: (-kv[0], kv[1]),
    )
    selected = [tech for score, tech in scored if score > 0]
    if len(selected) < 2:
        selected = ["ndvi", "ndbi", "ndwi"]
    return (selected + ["cva"])[:4]


# ---------------------------------------------------------------------------
# Area helpers
# ---------------------------------------------------------------------------


def _cell_area_km2(lat: float, lng_step: float, lat_step: float) -> float:
    m_lng = 111_320.0 * math.cos(math.radians(lat)) or 111_320.0
    return (lng_step * m_lng * lat_step * 110_574.0) / 1_000_000.0


def _cells_area(cells, scene, lng_step: float, lat_step: float) -> float:
    seen = set()
    total = 0.0
    for r, c in cells:
        key = r * 100_000 + c
        if key in seen:
            continue
        seen.add(key)
        total += _cell_area_km2(scene["lats"][r][c], lng_step, lat_step)
    return total


# ---------------------------------------------------------------------------
# Main analysis
# ---------------------------------------------------------------------------


def run_change_analysis(
    aoi: dict,
    query: str,
    date_1: date,
    date_2: date,
    techniques: Optional[list] = None,
    max_cells: Optional[int] = None,
    artifact_dir: Path = None,
    image_size: int = 360,
) -> dict:
    """Run the full change-detection engine for one AOI + date pair."""
    from ...config import settings

    artifact_dir = Path(artifact_dir or settings.change_artifact_dir())
    artifact_dir.mkdir(parents=True, exist_ok=True)
    image_size = int(image_size or settings.CHANGE_IMAGE_SIZE)
    bbox = aoi["bbox"]

    cols, rows = grid_params(bbox, max_cells or settings.CHANGE_MAX_CELLS)
    scene1 = rx.build_scene(date_1, bbox, cols, rows, evolution=0.0)
    scene2 = rx.build_scene(date_2, bbox, cols, rows, evolution=1.0)
    a = rx.analyze_change(scene1, scene2, techniques)
    selected = a["selected"]

    per_tech = []
    for tech in selected:
        delta = a["techniques"][tech]["delta"]
        mask = a["techniques"][tech]["mask"]
        thr = rx.TECHNIQUES[tech]["threshold"]
        gain_cells = [(r, c) for r in range(rows) for c in range(cols)
                      if mask[r][c] and delta[r][c] > thr]
        loss_cells = [(r, c) for r in range(rows) for c in range(cols)
                      if mask[r][c] and delta[r][c] < -thr]
        deltas = [delta[r][c] for r in range(rows) for c in range(cols) if mask[r][c]]
        mean_delta = (sum(deltas) / len(deltas)) if deltas else 0.0
        per_tech.append({
            "id": tech,
            "label": rx.TECHNIQUES[tech]["label"],
            "gain_label": rx.TECHNIQUES[tech]["gain"],
            "loss_label": rx.TECHNIQUES[tech]["loss"],
            "gain_cells": len(gain_cells),
            "loss_cells": len(loss_cells),
            "gain_km2": round(_cells_area(gain_cells, scene1, scene1["lng_step"], scene1["lat_step"]), 4),
            "loss_km2": round(_cells_area(loss_cells, scene1, scene1["lng_step"], scene1["lat_step"]), 4),
            "mean_delta": round(mean_delta, 4),
            "threshold": thr,
        })

    union_cells = [(r, c) for r in range(rows) for c in range(cols) if a["union"][r][c]]
    total_cells = cols * rows
    changed_area = _cells_area(union_cells, scene1, scene1["lng_step"], scene1["lat_step"])
    aoi_area = sum(
        _cell_area_km2(scene1["lats"][r][c], scene1["lng_step"], scene1["lat_step"])
        for r in range(rows) for c in range(cols)
    )

    clusters = rx.cluster_mask(a["union"], min_cluster=6)
    hotspots = []
    for i, cluster in enumerate(clusters[:12]):
        heats = [a["heat"][r][c] for r, c in cluster]
        lats = [scene1["lats"][r][c] for r, c in cluster]
        lngs = [scene1["lngs"][r][c] for r, c in cluster]
        gains = sum(1 for r, c in cluster if a["heat"][r][c] > 0)
        hotspots.append({
            "rank": i + 1,
            "cells": len(cluster),
            "area_km2": round(_cells_area(cluster, scene1, scene1["lng_step"], scene1["lat_step"]), 4),
            "center": {
                "lat": round(sum(lats) / len(lats), 5),
                "lng": round(sum(lngs) / len(lngs), 5),
            },
            "signal": "gain" if gains >= len(cluster) / 2 else "loss",
            "intensity": round(abs(sum(heats) / len(heats)), 3),
        })

    stats = _build_stats(scene1, scene2, a, union_cells, changed_area,
                         aoi_area, total_cells, per_tech, date_1, date_2,
                         hotspots)
    charts = _build_charts(a, per_tech, rows, cols)
    geojson = _build_geojson(scene1, a, union_cells)

    # Render artifacts (deterministic; row 0 of the GeoTIFF = northern edge).
    _write(artifact_dir / "before.png", rx.render_scene_rgb(scene1, image_size))
    _write(artifact_dir / "after.png", rx.render_scene_rgb(scene2, image_size))
    _write(artifact_dir / "heatmap.png", rx.render_heatmap(a["heat"], image_size))
    _write(artifact_dir / "magnitude.png", rx.render_magnitude(a["heat"], image_size))
    _write(artifact_dir / "change-mask.png", rx.render_mask(a["union"], image_size))
    intensity_rows = [
        [max(0, min(255, int(round(abs(v) * 255.0)))) for v in row]
        for row in reversed(a["heat"])
    ]
    _write(
        artifact_dir / "change-intensity.tif",
        rx.write_geotiff(
            intensity_rows,
            min_lng=bbox["min_lng"],
            max_lat=bbox["max_lat"],
            pixel_w=scene1["lng_step"],
            pixel_h=scene1["lat_step"],
        ),
    )

    gain_area = sum(t["gain_km2"] for t in per_tech)
    loss_area = sum(t["loss_km2"] for t in per_tech)
    return {
        "stats": stats,
        "charts": charts,
        "hotspots": hotspots,
        "techniques": per_tech,
        "geojson": geojson,
        "artifacts": {
            "before": "before.png",
            "after": "after.png",
            "heatmap": "heatmap.png",
            "magnitude": "magnitude.png",
            "change_mask": "change-mask.png",
            "intensity_tif": "change-intensity.tif",
        },
        "render": {
            "scene1": {"date": scene1["date"], "simulated": True},
            "scene2": {"date": scene2["date"], "simulated": True},
            "image_size": image_size,
        },
        "changes_summary": {
            "gain_area_km2": round(gain_area, 3),
            "loss_area_km2": round(loss_area, 3),
        },
    }


# ---------------------------------------------------------------------------
# Payload builders
# ---------------------------------------------------------------------------


def _build_stats(scene1, scene2, a, union_cells, changed_area, aoi_area,
                 total_cells, per_tech, date_1, date_2, hotspots) -> dict:
    mean_abs_heat = sum(abs(v) for row in a["heat"] for v in row) / total_cells
    heat_max = max((abs(v) for row in a["heat"] for v in row), default=0.0)
    dominant = max(per_tech, key=lambda t: t["gain_km2"] + t["loss_km2"])
    return {
        "changed_cells": len(union_cells),
        "total_cells": total_cells,
        "changed_area_km2": round(changed_area, 4),
        "aoi_area_km2": round(aoi_area, 3),
        "pct_changed": round(100.0 * changed_area / max(aoi_area, 1e-9), 2),
        "net_ndvi_delta": round(_mean_delta(scene1["ndvi"], scene2["ndvi"]), 4),
        "net_ndbi_delta": round(_mean_delta(scene1["ndbi"], scene2["ndbi"]), 4),
        "net_ndwi_delta": round(_mean_delta(scene1["ndwi"], scene2["ndwi"]), 4),
        "mean_abs_heat": round(mean_abs_heat, 4),
        "max_heat": round(heat_max, 3),
        "hotspot_count": len(hotspots),
        "window": f"{date_1.isoformat()} → {date_2.isoformat()}",
        "dominant_signal": dominant["id"] if per_tech else "ndvi",
    }


def _build_charts(a: dict, per_tech: list, rows: int, cols: int) -> dict:
    gain_area = sum(t["gain_km2"] for t in per_tech)
    loss_area = sum(t["loss_km2"] for t in per_tech)
    return {
        "categories": [
            {"name": "Expansion / gain", "value": round(gain_area, 3)},
            {"name": "Reduction / loss", "value": round(loss_area, 3)},
        ],
        "technique_bars": [
            {"id": t["id"], "gain_km2": t["gain_km2"], "loss_km2": t["loss_km2"],
             "label": t["label"]}
            for t in per_tech
        ],
        "histogram": _histogram(
            [abs(a["heat"][r][c]) for r in range(rows) for c in range(cols)
             if a["union"][r][c]]
        ),
    }


def _build_geojson(scene1: dict, a: dict, union_cells: list) -> dict:
    features = []
    for r, c in union_cells:
        lam, lo = scene1["lats"][r][c], scene1["lngs"][r][c]
        hl, hb = scene1["lng_step"] / 2.0, scene1["lat_step"] / 2.0
        heat_v = round(a["heat"][r][c], 4)
        features.append({
            "type": "Feature",
            "properties": {
                "value": heat_v,
                "sign": "gain" if heat_v > 0 else "loss",
                "intensity": round(abs(heat_v), 4),
            },
            "geometry": {
                "type": "Polygon",
                "coordinates": [[
                    [lo - hl, lam - hb], [lo + hl, lam - hb],
                    [lo + hl, lam + hb], [lo - hl, lam + hb],
                    [lo - hl, lam - hb],
                ]],
            },
        })
    return as_feature_collection(
        features,
        {"title": "Detected change cells (Date 1 vs Date 2)",
         "op": "change-analysis", "simulated": True},
    )


def _mean_delta(a: list, b: list) -> float:
    vals = [b[r][c] - a[r][c] for r in range(len(a)) for c in range(len(a[r]))]
    return (sum(vals) / len(vals)) if vals else 0.0


def _histogram(values, bins: int = 8) -> list:
    if not values:
        return []
    lo, hi = min(values), max(values)
    step = (hi - lo) / bins or 1.0
    counts = [0] * bins
    for v in values:
        idx = min(bins - 1, int((v - lo) / step))
        counts[idx] += 1
    return [
        {"bucket": round(lo + i * step, 3), "count": counts[i]}
        for i in range(bins)
    ]


def _write(path: Path, data: bytes) -> None:
    path.write_bytes(data)