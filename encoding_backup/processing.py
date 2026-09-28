"""Computational processing engine.

Executes the operations planned by the agents against retrieved datasets:

* flood-mapping, change-detection, classification, object-detection,
  time-series, fusion, terrain (DEM), image-search.

For demo datasets the engine builds deterministic synthetic rasters (seeded)
and computes *true statistics over that geometry* (areas in km2 computed from
cell sizes, zonal counts, trend fits). Every result payload is explicitly
labelled ``simulated`` so it can never be mistaken for real observations.
When real scene metadata is retrieved via STAC/Sentinel/Landsat the engine
returns the real retrieval (metadata) and clearly notes that raster-level
processing requires the optional rasterio/GDAL stack.
"""
from __future__ import annotations

import math
from datetime import date
from typing import Optional

from ..geo import (
    _field_value,
    as_feature_collection,
    bbox_intersection,
    cell_area_km2,
    cluster_centers,
    grid_cell_centers,
    sample_layer,
)

POPULATION_DENSITY = {
    "kerala": 819, "west bengal": 1028, "bihar": 1106, "uttar pradesh": 828,
    "tamil nadu": 555, "bangladesh": 1265, "myanmar": 83, "california": 98,
    "texas": 43, "florida": 165, "brazil": 25, "netherlands": 521,
    "india": 473, "punjab": 550, "gujarat": 308, "uttarakhand": 189,
}

TERRAIN_CLASSES = [
    ("Lowland (0-300m)", 0.10),
    ("Midland (300-900m)", 0.45),
    ("Highland (900-1800m)", 0.70),
    ("Alpine (1800m+)", 0.88),
]


def _window(dataset: dict, start: str | None, end: str | None) -> tuple[Optional[str], Optional[str]]:
    t = dataset.get("temporal") or {}
    s = start or t.get("start")
    e = end or t.get("end")
    return s, e


def _grid_params(dataset, bbox, max_cells: int = 2500):
    """Return a (res_deg, seed) tuned so cell count stays bounded."""
    res = float((dataset.get("grid") or {}).get("res_deg", 0.05))
    seed = int((dataset.get("grid") or {}).get("seed", 42))
    width = bbox["max_lng"] - bbox["min_lng"]
    height = bbox["max_lat"] - bbox["min_lat"]
    est = (width / res) * (height / res)
    while est > max_cells:
        res *= 2.0
        est = (width / res) * (height / res)
    return res, seed


def _work_bbox(dataset: dict, understanding: dict) -> dict:
    """Choose the analysis extent: query intersection, else dataset extent."""
    ds_bbox = dataset.get("bbox")
    q_bbox = understanding.get("bbox")
    if ds_bbox and q_bbox:
        inter = bbox_intersection(ds_bbox, q_bbox)
        if inter:
            return inter
    return ds_bbox or q_bbox or {
        "min_lng": 68.0, "min_lat": 6.0, "max_lng": 98.0, "max_lat": 38.0
    }


def _density(dataset: dict, params: dict | None) -> float:
    params = params or {}
    if params.get("population_density"):
        return float(params["population_density"])
    loc = (dataset.get("location") or {}).get("name", "").lower()
    return POPULATION_DENSITY.get(loc, 200.0)


def _filter_series(series: list[dict], start, end) -> list[dict]:
    out = []
    for pt in series:
        d = pt.get("date", "")
        if d and start and d < start:
            continue
        if d and end and d > end:
            continue
        out.append(pt)
    return out


def _series_area(series: list[dict], total_area: float, peak_value: float) -> list[dict]:
    if not peak_value:
        return [{"date": p.get("date"), "value": 0.0} for p in series]
    return [
        {
            "date": p.get("date"),
            "value": round(float(p.get("value", 0.0)) / peak_value * total_area, 2),
        }
        for p in series
    ]


def _severity_chart(cells: list[dict], buckets) -> list[dict]:
    counts = {name: 0 for name, _ in buckets}
    for c in cells:
        v = c["value"]
        for name, thr in buckets:
            if v >= thr:
                counts[name] += 1
                break
        else:
            counts[buckets[0][0]] += 1
    return [{"name": n, "value": counts[n]} for n, _ in buckets]


def _histogram(cells: list[dict], bins: int = 8) -> list[dict]:
    if not cells:
        return []
    values = [c["value"] for c in cells]
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


def _meta(dataset: dict, model: str, simulated: bool = True) -> dict:
    return {
        "source": dataset.get("source", "DEMO"),
        "simulated": simulated,
        "data_type": dataset.get("data_type"),
        "satellite": dataset.get("satellite"),
        "resolution": dataset.get("resolution"),
        "model": model,
        "license": dataset.get("license"),
    }


def _confidence(base: float, cells: list[dict], series: list[dict]) -> float:
    """Calibrate confidence from coverage and evidence."""
    bump = 0.0
    if cells:
        bump += 0.06 * min(1.0, len(cells) / 400)
    if series and len(series) >= 4:
        bump += 0.05
    return round(min(0.99, max(0.4, base + bump)), 2)


def run_operation(
    op: str,
    dataset: dict,
    understanding: dict,
    params: dict | None = None,
) -> dict:
    """Dispatch an agent-planned operation to its implementation."""
    handlers = {
        "flood-mapping": _flood_mapping,
        "change-detection": _change_detection,
        "classification": _classification,
        "object-detection": _object_detection,
        "time-series": _time_series,
        "fusion": _fusion,
        "terrain": _terrain,
        "image-search": _image_search,
        "real-events": _real_events,
        "ndvi": _spectral_index,
        "ndwi": _spectral_index,
        "ndbi": _spectral_index,
        "sar-backscatter": _sar_backscatter,
    }
    fn = handlers.get(op)
    if fn is None:
        raise ValueError(f"Unknown processing operation: {op}")
    return fn(dataset, understanding, params or {})
def _classification(dataset, understanding, params):
    bbox = _work_bbox(dataset, understanding)
    res, seed = _grid_params(dataset, bbox, max_cells=1800)
    cells = sample_layer(seed, bbox, res, frequency=0.9)
    is_sar = (dataset.get("data_type") or "").upper() == "SAR"
    classes = (
        [("Open water", 0.72), ("Flooded vegetation", 0.55), ("Dry land", 0.35), ("Built-up", 0.0)]
        if is_sar
        else [("Dense vegetation", 0.7), ("Moderate vegetation", 0.45), ("Barren / urban", 0.2), ("Water", 0.0)]
    )
    counts = {c[0]: 0 for c in classes}
    for c in cells:
        for name, thr in classes:
            if c["value"] >= thr:
                counts[name] += 1
                c["class"] = name
                break
        else:
            c["class"] = classes[-1][0]
            counts[classes[-1][0]] += 1

    area_per_class = {}
    for cell in cells:
        area_per_class[cell["class"]] = area_per_class.get(cell["class"], 0) + cell_area_km2(cell["lat"], res)
    dominant = max(counts, key=counts.get)
    geojson = as_feature_collection(
        [c["feature"] for c in cells],
        {"title": "Simulated thematic classification", "simulated": True},
    )
    stats = {
        "total_cells": len(cells),
        "dominant_class": dominant,
        "dominant_area_km2": round(area_per_class.get(dominant, 0.0), 2),
        "class_areas_km2": {k: round(v, 2) for k, v in area_per_class.items()},
    }
    return {
        "op": "classification",
        "label": "Classification",
        "geojson": geojson,
        "stats": stats,
        "confidence": _confidence(0.66 if cells else 0.3, cells, []),
        "charts": {
            "categories": [{"name": n, "value": counts[n]} for n, _ in classes],
            "histogram": _histogram(cells),
            "timeseries": [],
        },
        "metadata": _meta(dataset, "spectral-classifier-v1"),
    }


def _object_detection(dataset, understanding, params):
    bbox = _work_bbox(dataset, understanding)
    n = int(params.get("objects", 14))
    seeds = cluster_centers((dataset.get("grid") or {}).get("seed", 5) + 9, bbox, n)
    features = []
    for i, (lat, lng) in enumerate(seeds):
        size = round(20 + ((i * 37) % 180), 1)
        conf = round(0.6 + ((i * 13) % 30) / 100.0, 2)
        features.append(
            {
                "type": "Feature",
                "properties": {
                    "label": params.get("object_label", "Target"),
                    "confidence": conf,
                    "size_m": size,
                },
                "geometry": {"type": "Point", "coordinates": [lng, lat]},
            }
        )
    geojson = as_feature_collection(features, {"title": "Detected objects", "simulated": True})
    mean_conf = round(sum(f["properties"]["confidence"] for f in features) / max(len(features), 1), 2)
    stats = {
        "objects_detected": len(features),
        "mean_confidence": mean_conf,
        "size_range_m": [20.0, 200.0],
    }
    return {
        "op": "object-detection",
        "label": "Object Detection",
        "geojson": geojson,
        "stats": stats,
        "confidence": mean_conf,
        "charts": {
            "categories": [{"name": "Detected", "value": len(features)}],
            "histogram": [],
            "timeseries": [],
        },
        "metadata": _meta(dataset, "object-detector-v1"),
    }


def _time_series(dataset, understanding, params):
    start, end = _window(dataset, understanding.get("date_start"), understanding.get("date_end"))
    live = params.get("live_series") or []
    series = _filter_series(dataset.get("series", []), start, end)
    if not series and live:
        series = live
    if not series:
        series = dataset.get("series", [])
    values = [float(p.get("value", 0.0)) for p in series]
    n = len(values)
    mean = sum(values) / n if n else 0.0
    var = sum((v - mean) ** 2 for v in values) / n if n else 0.0
    std = math.sqrt(var)
    slope = 0.0
    if n >= 2:
        xs = list(range(n))
        mx = sum(xs) / n
        slope = sum((x - mx) * (v - mean) for x, v in zip(xs, values)) / sum((x - mx) ** 2 for x in xs)
    anomalies = [
        {"date": p.get("date"), "value": round(v, 3)}
        for p, v in zip(series, values)
        if std and abs(v - mean) > 1.5 * std
    ]
    stats = {
        "points": n,
        "mean": round(mean, 3),
        "min": round(min(values), 3) if values else None,
        "max": round(max(values), 3) if values else None,
        "stddev": round(std, 3),
        "linear_slope": round(slope, 5),
        "trend": "increasing" if slope > 0.001 else ("decreasing" if slope < -0.001 else "stable"),
        "anomalies": len(anomalies),
    }
    real = str(dataset.get("source", "")).upper() == "REAL" or bool(live)
    return {
        "op": "time-series",
        "label": "Time-Series Analysis",
        "geojson": as_feature_collection([], {"title": "Time-series (no geometry)"}),
        "stats": stats,
        "confidence": _confidence(0.7 if n >= 6 else 0.45, [], series),
        "charts": {
            "timeseries": [{"date": p.get("date"), "value": float(p.get("value", 0.0))} for p in series],
            "categories": [],
            "histogram": _histogram([{"lat": 0, "lng": 0, "value": v} for v in values]),
            "anomalies": anomalies,
        },
        "metadata": _meta(dataset, "temporal-trend-lstm-v1", simulated=not real),
    }
# ---------------------------------------------------------------------------
# flood-mapping
# ---------------------------------------------------------------------------


def _flood_mapping(dataset, understanding, params):
    bbox = _work_bbox(dataset, understanding)
    res, seed = _grid_params(dataset, bbox)
    start, end = _window(dataset, understanding.get("date_start"), understanding.get("date_end"))
    series = _filter_series(dataset.get("series", []), start, end)
    peak = max((float(p.get("value", 0.0)) for p in series), default=0.6)
    temporal = 0.5 + 0.5 * min(1.0, peak)  # how active the event window was
    # Fraction of the AOI flagged as affected; bounded and scene-aware.
    target = float(params.get("target_fraction", 0.025))
    fraction = max(0.01, min(target * temporal, 0.5))

    cells = sample_layer(seed, bbox, res, frequency=1.2)
    for c in cells:
        c["value"] = c["value"] * temporal
    cells.sort(key=lambda c: c["value"], reverse=True)
    k = int(len(cells) * fraction)
    flooded = cells[:k]

    total_area = sum(cell_area_km2(c["lat"], res) for c in flooded)
    density = _density(dataset, params)
    peak_date = max(series, key=lambda p: p.get("value", 0), default={}).get("date")
    threshold = min((c["value"] for c in flooded), default=0.0)

    geojson = as_feature_collection(
        [c["feature"] for c in flooded],
        {"title": "Simulated flood-water extent", "simulated": True},
    )
    stats = {
        "affected_area_km2": round(total_area, 2),
        "affected_cells": len(flooded),
        "detected_fraction": round(fraction, 3),
        "estimated_population": int(round(total_area * density)),
        "population_density_per_km2": int(density),
        "mean_intensity": round(sum(c["value"] for c in flooded) / max(len(flooded), 1), 3),
        "max_intensity": round(max((c["value"] for c in flooded), default=0.0), 3),
        "peak_date": peak_date,
        "threshold": round(threshold, 3),
    }
    return {
        "op": "flood-mapping",
        "label": "Flood Mapping",
        "geojson": geojson,
        "stats": stats,
        "confidence": _confidence(0.62 if flooded else 0.3, flooded, series),
        "charts": {
            "timeseries": _series_area(series, total_area, peak),
            "categories": _severity_chart(
                flooded, [("Severe", 0.82), ("High", 0.68), ("Moderate", 0.52), ("Minor", 0.0)]
            ),
            "histogram": _histogram(cells),
        },
        "metadata": _meta(dataset, "sar-flood-watermask-v1"),
    }


# ---------------------------------------------------------------------------
# change-detection
# ---------------------------------------------------------------------------


def _change_detection(dataset, understanding, params):
    bbox = _work_bbox(dataset, understanding)
    res, seed = _grid_params(dataset, bbox, max_cells=2000)
    start, end = _window(dataset, understanding.get("date_start"), understanding.get("date_end"))
    series = _filter_series(dataset.get("series", []), start, end)
    half = max(len(series) // 2, 1)
    early = max((float(p.get("value", 0.0)) for p in series[:half]), default=0.4)
    late = max((float(p.get("value", 0.0)) for p in series[half:]), default=0.5)
    delta = abs(late - early) / max(max(early, late), 0.001)
    target = float(params.get("target_fraction", 0.04))
    fraction = max(0.01, min(target, 0.4))

    cells = sample_layer(seed, bbox, res, frequency=1.0)
    for c in cells:
        c["value"] = (late - early) * (2 * c["value"] - 1)
    cells.sort(key=lambda c: abs(c["value"]), reverse=True)
    k = int(len(cells) * fraction)
    changed = cells[:k]
    gain = sum(1 for c in changed if c["value"] > 0)
    loss = len(changed) - gain

    total = sum(cell_area_km2(c["lat"], res) for c in changed)
    geojson = as_feature_collection(
        [c["feature"] for c in changed],
        {"title": "Detected change between selected dates", "simulated": True},
    )
    stats = {
        "changed_area_km2": round(total, 2),
        "changed_cells": len(changed),
        "expansion_cells": gain,
        "reduction_cells": loss,
        "trend": "increase" if late > early else "decrease",
        "delta_index": round(delta, 3),
        "window": f"{start} â†’ {end}",
    }
    return {
        "op": "change-detection",
        "label": "Change Detection",
        "geojson": geojson,
        "stats": stats,
        "confidence": _confidence(0.58 if changed else 0.3, changed, series),
        "charts": {
            "categories": [
                {"name": "Expansion", "value": gain},
                {"name": "Reduction", "value": loss},
            ],
            "histogram": _histogram(changed),
            "timeseries": [
                {"date": p.get("date"), "value": round(100 * float(p.get("value", 0.0)), 2)}
                for p in series
            ],
        },
        "metadata": _meta(dataset, "change-detector-v1"),
    }


def _fusion(dataset, understanding, params, extra_datasets=None):
    bbox = _work_bbox(dataset, understanding)
    res, seed = _grid_params(dataset, bbox, max_cells=2000)
    start, end = _window(dataset, understanding.get("date_start"), understanding.get("date_end"))
    series = _filter_series(dataset.get("series", []), start, end)
    peak = max((float(p.get("value", 0.0)) for p in series), default=0.6)
    temporal = 0.5 + 0.5 * min(1.0, peak)

    sources = [dataset] + (extra_datasets or [])[:2]
    layers = []
    layer_cells = []
    for src in sources:
        src_seed = int((src.get("grid") or {}).get("seed", seed))
        cells = sample_layer(src_seed, bbox, res, frequency=0.9)
        layers.append(
            {
                "id": src.get("id"),
                "name": src.get("name"),
                "simulated": True,
                "geojson": as_feature_collection(
                    [c["feature"] for c in cells],
                    {"title": f"Layer: {src.get('name')}", "simulated": True},
                ),
            }
        )
        layer_cells.append({(c["lat"], c["lng"]): c["value"] for c in cells})
    if not layer_cells:
        layer_cells = [{}]

    union_keys = sorted(set().union(*[set(m.keys()) for m in layer_cells]))
    consensus = []
    for key in union_keys:
        vals = [m.get(key, 0.0) for m in layer_cells]
        mean = sum(vals) / len(vals)
        agreement = 1.0 - (max(vals) - min(vals))
        score = mean * (0.5 + 0.5 * agreement) * temporal
        consensus.append({"lat": key[0], "lng": key[1], "value": score})
    threshold = float(params.get("fusion_threshold", 0.45))
    matched = [c for c in consensus if c["value"] >= threshold]

    total_area = sum(cell_area_km2(c["lat"], res) for c in matched)
    peak_date = max(series, key=lambda p: p.get("value", 0), default={}).get("date")
    stats = {
        "consensus_area_km2": round(total_area, 2),
        "consensus_cells": len(matched),
        "sources_fused": len(sources),
        "agreement_score": round(sum(m["value"] for m in matched) / max(len(matched), 1), 3),
        "peak_date": peak_date,
    }
    geojson = as_feature_collection(
        [{
            "type": "Feature",
            "properties": {"lat": c["lat"], "lng": c["lng"], "value": round(c["value"], 4)},
            "geometry": c["feature"]["geometry"],
        } for c in matched],
        {"title": "Multi-source consensus (simulated)", "simulated": True},
    )
    return {
        "op": "fusion",
        "label": "Multi-Source Fusion",
        "geojson": geojson,
        "layers": layers,
        "stats": stats,
        "confidence": _confidence(0.72 if matched else 0.3, matched, series),
        "charts": {
            "timeseries": _series_area(series, total_area, peak),
            "categories": [{"name": f"Source {i+1}", "value": 1} for i in range(len(sources))]
            + [{"name": "Consensus", "value": len(matched)}],
        },
        "metadata": _meta(dataset, "fusion-ensemble-v1"),
    }


def _terrain(dataset, understanding, params):
    bbox = _work_bbox(dataset, understanding)
    res, seed = _grid_params(dataset, bbox, max_cells=1500)
    z_min, z_max = (dataset.get("z_range_m") or [0, 1000])
    cells = sample_layer(seed, bbox, res, frequency=1.4)
    for c in cells:
        c["value"] = z_min + c["value"] * (z_max - z_min)

    geojson = as_feature_collection(
        [c["feature"] for c in cells],
        {"title": "Simulated elevation surface", "simulated": True},
    )
    classes = []
    for name, thr_fract in TERRAIN_CLASSES:
        v_thr = z_min + thr_fract * (z_max - z_min)
        n = sum(1 for c in cells if c["value"] >= v_thr)
        classes.append({"name": name, "value": n})
    stats = {
        "min_elevation_m": z_min,
        "max_elevation_m": z_max,
        "mean_elevation_m": round(sum(c["value"] for c in cells) / max(len(cells), 1), 1),
        "cells": len(cells),
    }
    return {
        "op": "terrain",
        "label": "Terrain / Elevation Analysis",
        "geojson": geojson,
        "stats": stats,
        "confidence": 0.75 if cells else 0.3,
        "charts": {
            "categories": classes,
            "histogram": _histogram(cells),
            "timeseries": [],
        },
        "metadata": _meta(dataset, "dem-terrain-v1"),
    }


def _image_search(dataset, understanding, params):
    scenes = params.get("scenes") or []
    features = []
    for s in scenes[:60]:
        geom = s.get("geometry") or s.get("bbox")
        if isinstance(geom, (list, tuple)) and len(geom) == 4:
            lng = (geom[0] + geom[2]) / 2
            lat = (geom[1] + geom[3]) / 2
            geometry = {"type": "Point", "coordinates": [lng, lat]}
        elif isinstance(geom, dict):
            geometry = geom
        else:
            continue
        features.append(
            {
                "type": "Feature",
                "properties": {
                    "id": s.get("id"),
                    "satellite": s.get("satellite"),
                    "date": s.get("date"),
                    "cloud": s.get("cloud_cover"),
                    "real": s.get("real", True),
                },
                "geometry": geometry,
            }
        )
    geojson = as_feature_collection(features, {"title": "Retrieved scenes", "simulated": not scenes})
    stats = {
        "scenes_found": len(scenes),
        "real_retrieval": bool(scenes),
        "sensors": sorted({s.get("satellite", "?") for s in scenes}),
    }
    conf = min(0.9, 0.4 + 0.5 * min(1.0, len(scenes) / 10)) if scenes else 0.3
    return {
        "op": "image-search",
        "label": "Scene Retrieval",
        "geojson": geojson,
        "stats": stats,
        "confidence": conf,
        "charts": {"categories": [], "histogram": [], "timeseries": []},
        "metadata": _meta(dataset, "stac-retriever", simulated=not scenes),
    }
# ---------------------------------------------------------------------------
# Spectral indices (NDVI / NDWI / NDBI) — simulated multispectral band math
# ---------------------------------------------------------------------------

SPECTRAL_SPECS = {
    "ndvi": {
        "label": "NDVI — Vegetation Health Index",
        "formula": "(NIR − RED) / (NIR + RED)",
        "bands": ("NIR", "RED"),
        "threshold": 0.35,
        "positive_label": "Healthy / dense vegetation",
        "negative_label": "Sparse / bare / water",
        "model": "optical-spectral-index-v1 (demo deterministic band model)",
    },
    "ndwi": {
        "label": "NDWI — Surface Water / Moisture Index",
        "formula": "(GREEN − NIR) / (GREEN + NIR)",
        "bands": ("GREEN", "NIR"),
        "threshold": 0.20,
        "positive_label": "Open water / high moisture",
        "negative_label": "Dry surface",
        "model": "optical-spectral-index-v1 (demo deterministic band model)",
    },
    "ndbi": {
        "label": "NDBI — Built-up / Impervious Index",
        "formula": "(SWIR − NIR) / (SWIR + NIR)",
        "bands": ("SWIR", "NIR"),
        "threshold": 0.15,
        "positive_label": "Built-up / urban",
        "negative_label": "Vegetated / non-urban",
        "model": "optical-spectral-index-v1 (demo deterministic band model)",
    },
}


def _spectral_bands(seed: int, lat: float, lng: float) -> dict[str, float]:
    """Deterministic pseudo-reflectance bands (0..1) from the shared spatial field.

    Band ranges mimic real vegetation/soil reflectance physics (NIR > RED for
    vegetated surfaces; GREEN dip over water; SWIR raised over built-up), so the
    resulting indices are statistically realistic. Reflectance values are
    simulated placeholders — never real DN values — and every output is clearly
    labelled simulated.
    """
    base = _field_value(seed, lat, lng, freq=0.9)
    nir = 0.28 + 0.42 * _field_value(seed + 1, lat, lng, freq=1.1)   # 0.28–0.70
    red = 0.05 + 0.20 * base                                           # 0.05–0.25
    green = 0.07 + 0.20 * _field_value(seed + 2, lat, lng, freq=1.0)  # 0.07–0.27
    swir = 0.08 + 0.30 * _field_value(seed + 3, lat, lng, freq=1.2)   # 0.08–0.38
    return {"RED": red, "NIR": nir, "GREEN": green, "SWIR": swir}
def _spectral_index(dataset, understanding, params):
    """Band-ratio spectral index analysis over the AOI (NDVI / NDWI / NDBI)."""
    op = understanding.get("analysis_type") or params.get("index") or "ndvi"
    if op not in SPECTRAL_SPECS:
        op = "ndvi"
    spec = SPECTRAL_SPECS[op]
    bbox = _work_bbox(dataset, understanding)
    res, seed = _grid_params(dataset, bbox, max_cells=2000)
    b1, b2 = spec["bands"]
    thresh = spec["threshold"]

    features = []
    values = []
    pos_cells = 0
    total_cells = 0
    for cell in sample_layer(seed, bbox, res, frequency=0.9):
        bands = _spectral_bands(seed, cell["lat"], cell["lng"])
        a, b = bands[b1], bands[b2]
        denom = (a + b) or 1e-6
        idx = (a - b) / denom
        idx = max(-1.0, min(1.0, round(idx, 4)))
        label = spec["positive_label"] if idx >= thresh else spec["negative_label"]
        values.append(idx)
        total_cells += 1
        if idx >= thresh:
            pos_cells += 1
        half = res / 2.0
        features.append({
            "type": "Feature",
            "properties": {
                "lat": round(cell["lat"], 6),
                "lng": round(cell["lng"], 6),
                "value": idx,
                "class": label,
            },
            "geometry": {
                "type": "Polygon",
                "coordinates": [[
                    [cell["lng"] - half, cell["lat"] - half],
                    [cell["lng"] + half, cell["lat"] - half],
                    [cell["lng"] + half, cell["lat"] + half],
                    [cell["lng"] - half, cell["lat"] + half],
                    [cell["lng"] - half, cell["lat"] - half],
                ]],
            },
        })

    mean = sum(values) / len(values) if values else 0.0
    cell_area = cell_area_km2((bbox["min_lat"] + bbox["max_lat"]) / 2, res)
    pos_area = round(pos_cells * cell_area, 2)
    geojson = as_feature_collection(features, {
        "title": spec["label"],
        "index": op.upper(),
        "formula": spec["formula"],
        "simulated": True,
    })
    stats = {
        "index": op.upper(),
        "mean_index": round(mean, 3),
        "min_index": round(min(values), 3) if values else None,
        "max_index": round(max(values), 3) if values else None,
        "positive_cells": pos_cells,
        "total_cells": total_cells,
        "positive_area_km2": pos_area,
        "threshold": thresh,
        "band_pair": f"{b1}/{b2}",
    }
    confidence = _confidence(0.66 if total_cells else 0.3, features, [])
    return {
        "op": op,
        "label": spec["label"],
        "geojson": geojson,
        "stats": stats,
        "confidence": confidence,
        "charts": {
"histogram": _histogram([{"lat": 0, "lng": 0, "value": v} for v in values]),
            "categories": [
                {"name": spec["positive_label"], "value": pos_cells},
                {"name": spec["negative_label"], "value": total_cells - pos_cells},
            ],
            "timeseries": [],
        },
        "metadata": _meta(dataset, spec["model"], simulated=True),
    }

def _sar_backscatter(dataset, understanding, params):
    """SAR backscatter σ⁰-signature analysis (simulated calibrated intensities).

    Models the deterministic backscatter field as pseudo-σ⁰ in dB and builds
    roughness/water/urban classes from the intensity envelope — the same
    physics-based label boundaries (smooth water ~ low σ⁰, corner reflectors ~
    very high σ⁰) used by real SAR flood and urban mapping."""
    bbox = _work_bbox(dataset, understanding)
    res, seed = _grid_params(dataset, bbox, max_cells=1600)
    classes = [
        ("Open water (low σ⁰)", 0.82),
        ("Smooth / bare (mid σ⁰)", 0.55),
        ("Rough / vegetation (mid-high σ⁰)", 0.4),
        ("Built-up corner reflectors (high σ⁰)", 0.0),
    ]
    features = []
    counts = {c[0]: 0 for c in classes}
    sigmas = []
    for cell in sample_layer(seed, bbox, res, frequency=1.0):
        v = cell["value"]
        sigma = round(-18.0 + v * 22.0, 2)  # -18 dB … +4 dB envelope
        sigmas.append(sigma)
        cls = None
        for name, thr in classes:
            if v >= thr:
                cls = name
                break
        cls = cls or classes[0][0]
        counts[cls] += 1
        half = res / 2.0
        features.append({
            "type": "Feature",
            "properties": {
                "lat": round(cell["lat"], 6),
                "lng": round(cell["lng"], 6),
                "value": sigma,
                "class": cls,
            },
            "geometry": {
                "type": "Polygon",
                "coordinates": [[
                    [cell["lng"] - half, cell["lat"] - half],
                    [cell["lng"] + half, cell["lat"] - half],
                    [cell["lng"] + half, cell["lat"] + half],
                    [cell["lng"] - half, cell["lat"] + half],
                    [cell["lng"] - half, cell["lat"] - half],
                ]],
            },
        })
    mean_s = sum(sigmas) / len(sigmas) if sigmas else 0.0
    geojson = as_feature_collection(features, {
        "title": "SAR Backscatter Signature",
        "band": "C-band VV σ⁰ (simulated)",
        "simulated": True,
    })
    stats = {
        "mean_sigma_db": round(mean_s, 2),
        "min_sigma_db": round(min(sigmas), 2) if sigmas else None,
        "max_sigma_db": round(max(sigmas), 2) if sigmas else None,
        "water_cells": counts["Open water (low σ⁰)"],
        "built_up_cells": counts["Built-up corner reflectors (high σ⁰)"],
        "total_cells": len(features),
        "polarization": "VV (simulated)",
    }
    return {
        "op": "sar-backscatter",
        "label": "SAR Backscatter Signature Analysis",
        "geojson": geojson,
"stats": stats,
        "confidence": _confidence(0.68 if features else 0.3, features, []),
        "charts": {
            "histogram": _histogram([{"lat": 0, "lng": 0, "value": s} for s in sigmas]),
            "categories": [{"name": k, "value": v} for k, v in counts.items() if v],
            "timeseries": [],
        },
        "metadata": _meta(dataset, "sar-backscatter-v1 (demo deterministic σ⁰ model)", simulated=True),
    }
def _real_events(dataset, understanding, params):
    """Render REAL observations (earthquakes/weather/stations) as point features.

    Uses live data pulled by the caller (params['live_events']) with the actual
    values as reported by the upstream provider — never fabricated geometry.
    """
    live = params.get("live_events") or []
    label = str(params.get("event_label", "Real observation"))

    features = []
    for ev in live:
        lat, lng = ev.get("lat"), ev.get("lng")
        if lat is None or lng is None:
            continue
        props = {k: v for k, v in ev.items() if k in
                 ("mag", "place", "depth_km", "time", "tsunami", "temperature_c",
                  "city", "weather", "wind_speed_kmh", "relative_humidity",
                  "precipitation_mm", "moved", "moved_deg", "downtime")}
        props["label"] = label
        features.append(
            {
                "type": "Feature",
                "properties": props,
                "geometry": {"type": "Point", "coordinates": [lng, lat]},
            }
        )

    source = str(dataset.get("source", "REAL"))
    observed = dataset.get("observed_at")
    stats = {
        "events": len(features),
        "source": source,
        "observed_at": observed,
    }
    mags = [f["properties"].get("mag") for f in features if f["properties"].get("mag") is not None]
    if mags:
        stats["max_magnitude"] = round(max(mags), 1)
        stats["mean_magnitude"] = round(sum(mags) / len(mags), 1)
        stats["events_above_4"] = sum(1 for m in mags if m >= 4.0)
    temps = [f["properties"].get("temperature_c") for f in features if f["properties"].get("temperature_c") is not None]
    if temps:
        stats["mean_temperature_c"] = round(sum(temps) / len(temps), 1)
        stats["min_temperature_c"] = round(min(temps), 1)
        stats["max_temperature_c"] = round(max(temps), 1)

    categories = {}
    for f in features:
        key = f["properties"].get("city") or f["properties"].get("place") or source
        categories[key] = categories.get(key, 0) + 1

    geojson = as_feature_collection(
        features,
        {
            "title": f"Live {label} — {source}",
            "real": True,
            "simulated": False,
            "source": source,
        },
    )
    return {
        "op": "real-events",
        "label": f"{label} (live)",
        "geojson": geojson,
        "stats": stats,
        "confidence": 0.82,
        "charts": {
            "timeseries": params.get("live_series") or [],
            "categories": [{"name": k, "value": v} for k, v in
                           sorted(categories.items(), key=lambda kv: kv[1], reverse=True)[:8]],
            "histogram": _histogram([{"lat": 0, "lng": 0, "value": m} for m in mags]) if mags else [],
        },
        "metadata": _meta(dataset, "realtime-live-v1", simulated=False),
    }
