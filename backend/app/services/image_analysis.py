"""Satellite-photo analysis for user-uploaded images.

Users can upload a satellite/aerial photo from their device and ask questions
about it. This service:

* **Measures real pixel statistics** with Pillow (no fabrication): dimensions,
  format, aspect ratio, mean brightness/contrast, colourfulness, texture
  entropy, edge density, dominant colours and surface-tone fractions.
* **Infers the photo kind** (satellite/aerial vs ground photo vs chart/diagram)
  from measurable image statistics.
* **Estimates surface classes** (water / vegetation / bare / built-up) from hue
  and saturation as a *clearly-labelled approximation*, rendered as a coarse map
  grid over the query area (or a default AOI).
* **Runs the full pipeline** — NLP understanding, deep research, verification,
  summary — and persists upload/query/result/job records exactly like every
  other analysis so the UI, reports and history all work unchanged.
"""
from __future__ import annotations

import io
import math
import statistics

# ---------------------------------------------------------------------------
# Image loading & validation
# ---------------------------------------------------------------------------

ALLOWED_FORMATS = {
    "JPEG": (".jpg", ".jpeg"),
    "PNG": (".png",),
    "WEBP": (".webp",),
    "TIFF": (".tif", ".tiff"),
    "BMP": (".bmp",),
    "GIF": (".gif",),
}
MAX_BYTES = 25_000_000
_MAX_DIM = 6000


class ImageError(ValueError):
    pass


def load_image(raw: bytes) -> "object":
    """Open and validate an uploaded image. Raises ImageError on bad input."""
    if not raw:
        raise ImageError("Empty upload.")
    if len(raw) > MAX_BYTES:
        raise ImageError("File too large (max 25 MB).")
    try:
        from PIL import Image

        img = Image.open(io.BytesIO(raw))
        img.load()
        if img.format not in ALLOWED_FORMATS:
            raise ImageError(
                f"Unsupported image format '{img.format}'. Supported: "
                + ", ".join(sorted(ALLOWED_FORMATS))
            )
        if max(img.size) > _MAX_DIM:
            img = img.resize(
                (int(img.size[0] * _MAX_DIM / max(img.size)),
                 int(img.size[1] * _MAX_DIM / max(img.size)))
            )
        if img.mode not in ("RGB", "RGBA", "L"):
            img = img.convert("RGB")
        return img
    except ImageError:
# ---------------------------------------------------------------------------
# Real pixel metrics (Pillow / statistics — no fabrication).
# ---------------------------------------------------------------------------


def _colorfulness(img) -> float:
    """Hasler & Süsstrunk colourfulness measure on a downscaled RGB sample."""
    small = img.resize((max(1, img.size[0] // 8), max(1, img.size[1] // 8)))
    px = list(small.getdata())
    if not px:
        return 0.0
    if isinstance(px[0], (int, float)):
        return 0.0  # greyscale
    rg = [p[0] - p[1] for p in px]
    yb = [0.5 * (p[0] + p[1]) - p[2] for p in px if len(p) > 2]
    f = (
        math.hypot(statistics.pstdev(rg), statistics.pstdev(yb))
        + 0.3 * math.hypot(statistics.mean(rg), statistics.mean(yb))
    )
    return round(float(f), 2)


def _texture_entropy(img) -> float:
    """Shannon entropy of the greyscale histogram (0 = flat, 8 = noisy)."""
    grey = img.convert("L")
    hist = grey.histogram()
    total = sum(hist)
    if not total:
        return 0.0
    ent = -sum(
        (c / total) * math.log2(c / total) for c in hist if c
    )
    return round(ent, 3)


def _edge_density(img) -> float:
    """Mean edge-magnitude (0..1) from PIL FIND_EDGES on a small greyscale."""
    try:
        from PIL import ImageFilter

        small = img.convert("L").resize((96, 96))
        edges = small.filter(ImageFilter.FIND_EDGES)
        px = list(edges.getdata())
        if px and isinstance(px[0], (int, float)):
            return round(sum(px) / len(px) / 255.0, 4)
    except Exception:
        pass
    return 0.0


SURFACE_LABELS = {
    "water": "#0ea5e9",
    "vegetation": "#22c55e",
    "bare": "#d6d3d1",
    "built_up": "#f97316",
}


def _surface_tone(hue: float, sat: int, val: int) -> str:
    """Heuristic hue/saturation bucket -> approximate surface type."""
    if val < 28:
        return "water"          # very dark: shadowed water / deep shadow
    if sat < 28:
        return "built_up" if val > 55 else "bare"   # grey -> built-up; tan -> bare
    h = hue
    if h < 28 or h >= 340:      # red / orange
        return "built_up" if sat > 55 else "bare"
    if 28 <= h < 80:            # yellow / olive
        return "bare"
    if 80 <= h < 170:           # green / cyan
        return "vegetation"
    if 170 <= h < 260:          # blue
        return "water"
    return "bare"               # purple / magenta -> mixed


def extract_image_metrics(img) -> dict:
    """Real, measurable statistics of the uploaded image."""
    rgb = _to_rgb(img)
    width, height = rgb.size
    small = rgb.resize((max(1, width // 4), max(1, height // 4)))
    px = list(small.getdata())
    if isinstance(px[0], (int, float)):  # greyscale after conversion
        px = [(int(p), int(p), int(p)) for p in px]
    if not px:
        raise ImageError("Could not read image pixels.")

    n = len(px)
    r = sum(p[0] for p in px) / n
    g = sum(p[1] for p in px) / n
    b = sum(p[2] for p in px) / n
    brightness = (r + g + b) / 3.0 / 255.0
    lums = [0.299 * p[0] + 0.587 * p[1] + 0.114 * p[2] for p in px]
    contrast = statistics.pstdev(lums) / 255.0

    # HSV surface-tone fractions
    import colorsys

    tone_counts = {k: 0 for k in SURFACE_LABELS}
    for p in px:
        h, s, v = colorsys.rgb_to_hsv(p[0] / 255.0, p[1] / 255.0, p[2] / 255.0)
        tone_counts[_surface_tone(h * 360.0, int(s * 255), int(v * 255))] += 1
    surface_frac = {
        k: round(v / n, 4) for k, v in tone_counts.items()
    }

    # Dominant colours: quantise to 32 levels then count.
    buckets: dict[tuple, int] = {}
    for p in px:
        key = (p[0] // 32 * 32, p[1] // 32 * 32, p[2] // 32 * 32)
        buckets[key] = buckets.get(key, 0) + 1
    top = sorted(buckets.items(), key=lambda kv: kv[1], reverse=True)[:6]
    dominant_colors = [
        {"hex": "#%02x%02x%02x" % (k[0], k[1], k[2]),
         "share": round(v / n, 4)}
        for k, v in top
    ]
def infer_photo_kind(metrics: dict) -> dict:
    """Classify the image type from measurable statistics (best-effort)."""
    cf = metrics.get("colorfulness", 0.0)
    ent = metrics.get("texture_entropy", 0.0)
    edges = metrics.get("edge_density", 0.0)
    aspect = metrics.get("aspect_ratio", 1.0)

    if cf < 18 and ent < 5.5 and edges < 0.12:
        kind = "chart_diagram"
        label = "Chart / diagram"
        reason = "Low colour variety and limited texture match diagrammatic content."
        confidence = round(min(0.85, 0.45 + (5.5 - ent) * 0.02 + (0.12 - edges)), 2)
    elif cf > 38 and ent > 6.4 and abs(aspect - 1.0) > 0.45:
        kind = "ground_photo"
        label = "Ground-level photo"
        reason = "High colourfulness, rich texture and a non-square frame are typical of ground photography."
        confidence = round(min(0.85, 0.4 + (cf - 38) * 0.004 + (ent - 6.4) * 0.2), 2)
    else:
        kind = "satellite_aerial"
        label = "Satellite / aerial imagery"
        reason = "Colourfulness, texture and framing are consistent with overhead remote-sensing imagery."
        confidence = round(min(0.82, 0.5 + (6.4 - abs(ent - 6.4)) * 0.04), 2)
    return {"kind": kind, "label": label, "reason": reason, "confidence": confidence}


def color_histogram(img, buckets: int = 12) -> list[dict]:
    """True-colour luminance/hue profile for charts — real pixel data."""
    rgb = _to_rgb(img).resize((64, 64))
    px = list(rgb.getdata())
    if isinstance(px[0], (int, float)):
        px = [(int(p), int(p), int(p)) for p in px]
    n = len(px)
    out = [{"bin": i, "name": f"{round(i * 320 / buckets)}°–{round((i + 1) * 320 / buckets)}°",
            "value": 0} for i in range(buckets)]
    import colorsys

    for p in px:
        h, s, v = colorsys.rgb_to_hsv(p[0] / 255.0, p[1] / 255.0, p[2] / 255.0)
        # Weight by saturation so grey doesn't skew the hue histogram.
        idx = min(buckets - 1, int(h * 320.0 // (320.0 / buckets))) if s > 0.12 else -1
        if idx >= 0:
def surface_grid(img, grid: int = 12) -> list[dict]:
    """Coarse surface-type estimate over a down-sampled tile grid.

    Each tile's dominant HSV tone is mapped to an approximate class
    (water / vegetation / bare / built-up). This is an *estimate* derived from
    the photo pixels — it is clearly labelled as approximate.
    """
    rgb = _to_rgb(img)
    tw = max(1, rgb.size[0] // grid)
    th = max(1, rgb.size[1] // grid)
    rows = []
    import colorsys

    for gy in range(min(grid, rgb.size[1] // th or grid)):
        for gx in range(min(grid, rgb.size[0] // tw or grid)):
            box = (gx * tw, gy * th, min(rgb.size[0], (gx + 1) * tw),
                   min(rgb.size[1], (gy + 1) * th))
            tile = rgb.crop(box).resize((8, 8))
            px = list(tile.getdata())
            if not px:
                continue
            if isinstance(px[0], (int, float)):
                px = [(int(p), int(p), int(p)) for p in px]
            counts: dict[str, int] = {}
            for p in px:
                h, s, v = colorsys.rgb_to_hsv(p[0] / 255.0, p[1] / 255.0,
                                              p[2] / 255.0)
                cls = _surface_tone(h * 360.0, int(s * 255), int(v * 255))
                counts[cls] = counts.get(cls, 0) + 1
            dominant = max(counts.items(), key=lambda kv: kv[1])[0]
            frac = counts[dominant] / len(px)
            rows.append({
                "x": gx, "y": gy,
                "class": dominant,
                "class_frac": round(frac, 3),
                "color": SURFACE_LABELS[dominant],
            })
    return rows
            out[idx]["value"] += 1
# ---------------------------------------------------------------------------
# Full pipeline: persist an image query/result/job exactly like other analyses
# ---------------------------------------------------------------------------

_DEFAULT_BBOX = {
    "min_lng": 72.6, "min_lat": 18.6, "max_lng": 73.5, "max_lat": 19.4
}  # Mumbai region default shown when the query has no resolvable location


def _bbox_for(understanding: dict) -> dict:
    bb = understanding.get("bbox")
    if bb and all(k in bb for k in ("min_lng", "min_lat", "max_lng", "max_lat")):
        return bb
    return dict(_DEFAULT_BBOX)


def _grid_geojson(rows: list[dict], bbox: dict) -> dict:
    """Turn the surface grid into GeoJSON polygons over the AOI bbox."""
    nx = max(1, max((r["x"] for r in rows), default=0) + 1)
    ny = max(1, max((r["y"] for r in rows), default=0) + 1)
    d_lng = (bbox["max_lng"] - bbox["min_lng"]) / nx
    d_lat = (bbox["max_lat"] - bbox["min_lat"]) / ny
    features = []
    for r in rows:
        x0, y0, x1, y1 = (
            bbox["min_lng"] + r["x"] * d_lng,
            bbox["min_lat"] + r["y"] * d_lat,
            bbox["min_lng"] + (r["x"] + 1) * d_lng,
            bbox["min_lat"] + (r["y"] + 1) * d_lat,
        )
        features.append({
            "type": "Feature",
            "properties": {
                "class": r["class"].replace("_", " ").title(),
                "frac": r["class_frac"],
                "color": r["color"],
            },
            "geometry": {
                "type": "Polygon",
                "coordinates": [[
                    [x0, y0], [x1, y0], [x1, y1], [x0, y1], [x0, y0],
                ]],
            },
        })
    from ..geo import as_feature_collection

    return as_feature_collection(
        features,
        {
            "title": ("Approximate surface-type estimate derived from the "
                      "uploaded photo pixels (not validated ground truth)"),
            "simulated": True,
            "note": (
                "Coarse photo-pixel tone classification — illustrative, "
                "not a calibrated land-cover product."
            ),
        },
    )


def _store_upload(db, user_id: str, raw: bytes, filename: str,
                  metrics: dict, kind: dict) -> str:
    """Persist the image bytes to disk + a record row; returns the upload id."""
    import uuid

    from ..config import settings

    up_dir = settings.DATA_DIR / "uploads"
    up_dir.mkdir(parents=True, exist_ok=True)
    upload_id = uuid.uuid4().hex
    ext = ".img"
    if filename and "." in filename:
        ext = "." + filename.rsplit(".", 1)[-1].lower()
    fname = f"{upload_id}{ext}"
    (up_dir / fname).write_bytes(raw)
def run_image_query(db, user_id: str, raw: bytes, filename: str,
                    text: str) -> dict:
    """End-to-end image query: understand -> analyse pixels -> research ->
    verify -> summarise -> persist upload/query/result/job records.

    Returns the bundle the router needs: ``{query_id, result_id, job_id,
    understanding, research, metrics, ...}``.
    """
    from ..storage import datetime_now
    from .nlp_understanding import understand_query
    from .research import build_research_brief

    img = load_image(raw)
    metrics = extract_image_metrics(img)
    kind = infer_photo_kind(metrics)
    hist = color_histogram(img)

    understanding = understand_query(text or "")
    bbox = _bbox_for(understanding) if understanding.get("bbox") else dict(_DEFAULT_BBOX)
    understanding["bbox"] = bbox

    upload_id = _store_upload(db, user_id, raw, filename, metrics, kind)

    rows = surface_grid(img, grid=12)
    geojson = _grid_geojson(rows, bbox)
    from ..geo import cell_area_km2

    nx = max(1, max((r["x"] for r in rows), default=0) + 1)
    ny = max(1, max((r["y"] for r in rows), default=0) + 1)
    res_deg = (bbox["max_lng"] - bbox["min_lng"]) / nx
    area_by_class: dict[str, float] = {}
    class_cells: dict[str, int] = {}
    for r in rows:
        cls = r["class"]
        mid_lat = bbox["min_lat"] + (r["y"] + 0.5) / ny
        area_by_class[cls] = area_by_class.get(cls, 0.0) + cell_area_km2(mid_lat, res_deg)
        class_cells[cls] = class_cells.get(cls, 0) + 1

    surface_frac = metrics.get("surface_estimate", {})
    dominant_cls = max(surface_frac.items(), key=lambda kv: kv[1])[0]

    stats = {
        "width": metrics["width"],
        "height": metrics["height"],
        "format": metrics["format"],
        "aspect_ratio": metrics["aspect_ratio"],
        "mean_brightness": metrics["mean_brightness"],
        "contrast": metrics["contrast"],
        "colorfulness": metrics["colorfulness"],
        "texture_entropy": metrics["texture_entropy"],
        "edge_density": metrics["edge_density"],
        "dominant_surface": dominant_cls.replace("_", " ").title(),
        "dominant_share": surface_frac.get(dominant_cls, 0.0),
        "class_cells": class_cells,
        "area_by_class_km2": {k: round(v, 2) for k, v in area_by_class.items()},
    }

    research = build_research_brief(understanding, db)

    metadata = {
        "model": "photo-pixel-v1 (statistical image analysis)",
        "satellite": "User-uploaded image",
        "resolution": f"{metrics['width']}×{metrics['height']} px",
        "data_type": "Optical",
        "source": "UPLOAD",
        "simulated": False,
        "note": (
            "Pixel statistics are real measurements taken from your uploaded "
            "photo. The surface-type map is a coarse photo-pixel tone estimate "
            "— not a calibrated land-cover product."
        ),
        "image": {
            "upload_id": upload_id,
            "filename": filename,
            "kind": kind,
            "dominant_colors": metrics.get("dominant_colors", []),
        },
    }

execution_trace = {
        "target_task": "Image query — understand and analyse the uploaded photo",
        "modality": {
            "id": "photo-optical",
            "label": "User-uploaded optical photo (pixel statistics)",
            "sensors": ["Uploaded device image"],
            "constraints": ("No georeferencing is assumed. Surface-type map is "
                            "an approximation derived from photo colour."),
            "realtime": False,
        },
        "tools": [
            "ImageLoader", "PixelStatistics", "ColorfulnessEstimator",
            "SurfaceToneEstimator", "NLPCurrencyParsing", "DeepResearch",
        ],
        "steps": [
            {"step": 1, "tool": "ImageLoader",
             "op": "load", "detail": f"Opened {filename} ({metrics['format']})",
             "result": {"size": f"{metrics['width']}×{metrics['height']}px"}},
            {"step": 2, "tool": "PixelStatistics",
             "op": "image-statistics",
             "detail": "Measured brightness, contrast, colourfulness, entropy, edges.",
             "result": {"brightness": metrics["mean_brightness"],
                        "colorfulness": metrics["colorfulness"]}},
            {"step": 3, "tool": "SurfaceToneEstimator",
             "op": "image-classification-estimate",
             "detail": "Approximate surface types from photo hue/saturation.",
             "result": {"dominant": dominant_cls,
                        "share": surface_frac.get(dominant_cls)}},
            {"step": 4, "tool": "DeepResearch",
             "op": "research",
             "detail": "Assembled research brief (facts + live evidence + STAC).",
             "result": {"sections": len(research.get("sections", []))}},
        ],
        "confidence": confidence,
        "uncertainties": [
            "Surface-type map is an approximate heuristic from photo colours, "
            "not a calibrated classification.",
            "No geolocation is embedded in the image unless your query named one.",
        ],
    }

    from .summarizer import build_summary
    from .verification import verify_result

    verification = verify_result(
        {"op": "image-analysis", "stats": stats, "metadata": metadata,
         "geojson": geojson, "confidence": confidence},
        {"bbox": bbox, "source": "UPLOAD"},
        understanding,
        execution_trace=execution_trace["steps"],
        modality=execution_trace["modality"],
    )
    summary = build_summary(
        {"op": "image-analysis", "stats": stats, "metadata": metadata,
         "confidence": confidence, "label": "Satellite photo analysis"},
        understanding,
        {"location": {"name": understanding.get("location", "the photo")}},
query_id = db.insert("queries", {
        "user_id": user_id,
        "text": text or f"Analyse the uploaded photo {filename}",
        "understanding": understanding,
        "agent": "Optical Photo Agent",
        "model": "photo-pixel-v1 (statistical image analysis)",
        "datasets_used": ["user_upload"],
        "upload_id": upload_id,
        "research": research,
        "execution_trace": execution_trace,
        "status": "completed",
    })
    result_id = db.insert("results", {
        "user_id": user_id,
        "query_id": query_id,
        "upload_id": upload_id,
        "op": "image-analysis",
        "label": "Satellite photo analysis",
        "confidence": confidence,
        "geojson": geojson,
        "layers": [{"type": "grid", "title": "Surface-type estimate"}],
        "stats": stats,
        "charts": charts,
        "metadata": metadata,
        "verification": verification,
        "summary": summary,
        "understanding": understanding,
        "execution_trace": execution_trace,
        "modality": execution_trace["modality"],
        "simulated": False,
        "research": research,
    })
    job_id = db.insert("jobs", {
        "user_id": user_id,
        "query_id": query_id,
        "result_id": result_id,
        "status": "completed",
        "progress": 100,
        "stage": "saved",
        "message": "Image analysis complete.",
        "op": "image-analysis",
    })

    return {
        "query_id": query_id,
        "result_id": result_id,
        "job_id": job_id,
        "upload_id": upload_id,
        "understanding": understanding,
        "research": research,
        "metrics": metrics,
        "kind": kind,
        "stats": stats,
        "charts": charts,
        "geojson": geojson,
        "verification": verification,
        "summary": summary,
        "execution_trace": execution_trace,
        "created_at": datetime_now(),
    }


def read_upload_bytes(upload_id: str) -> bytes | None:
    """Return the stored image bytes for an upload id (or None)."""
    from ..config import settings

    up_dir = settings.DATA_DIR / "uploads"
    for p in up_dir.glob(f"{upload_id}.*"):
        return p.read_bytes()
    return None
        "Optical Photo Agent",
    )
    charts = {
        "categories": [
            {"name": "Water", "value": surface_frac.get("water", 0.0)},
            {"name": "Vegetation", "value": surface_frac.get("vegetation", 0.0)},
            {"name": "Bare", "value": surface_frac.get("bare", 0.0)},
            {"name": "Built-up", "value": surface_frac.get("built_up", 0.0)},
        ],
        "histogram": hist,
    }

    confidence = round(0.55 + 0.15 * metrics["colorfulness"] / 60.0 + 0.1 * kind["confidence"], 2)
    confidence = round(min(0.9, confidence), 2)
    db.insert("uploads", {
        "id": upload_id,
        "user_id": user_id,
        "filename": filename or f"upload{ext}",
        "stored_name": fname,
        "size_bytes": len(raw),
        "format": metrics.get("format"),
        "width": metrics.get("width"),
        "height": metrics.get("height"),
        "kind": kind.get("kind"),
        "kind_label": kind.get("label"),
    })
    return upload_id
    for b in out:
        b["value"] = round(b["value"] / max(n, 1), 4)
    return out

    colorfulness = _colorfulness(rgb)
    entropy = _texture_entropy(rgb)
    edges = _edge_density(rgb)

    return {
        "format": getattr(img, "format", None) or "IMAGE",
        "width": width,
        "height": height,
        "aspect_ratio": round(width / max(height, 1), 3),
        "mean_rgb": [round(r, 1), round(g, 1), round(b, 1)],
        "mean_brightness": round(brightness, 4),
        "contrast": round(contrast, 4),
        "colorfulness": colorfulness,
        "texture_entropy": entropy,
        "edge_density": edges,
        "surface_estimate": surface_frac,
        "dominant_colors": dominant_colors,
    }
        raise
    except Exception as exc:
        raise ImageError(f"Not a valid image file: {exc}")


def _to_rgb(img) -> "object":
    if img.mode == "RGBA":
        bg = __import__("PIL.Image", fromlist=["Image"]).Image.new(
            "RGB", img.size, (0, 0, 0))
        bg.paste(img, mask=img.split()[-1])
        return bg.convert("RGB")
    return img.convert("RGB")