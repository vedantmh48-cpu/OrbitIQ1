"""Dependency-free synthetic raster engine for change analysis.

Builds deterministic, physically-grounded *synthetic surface-reflectance
scenes* for any AOI + date (seeded per location and date), then computes
spectral indices, differences them between Date 1 and Date 2, runs Change
Vector Analysis, clusters changed pixels into hotspots and renders:
True-colour composites, a signed direction heatmap, an unsigned intensity
mask, and a single-band GeoTIFF of change intensity.

Pure Python standard library only (zlib/struct/math) - no NumPy/GDAL/Pillow
required, matching the project's dependency-light philosophy. The synthetic
scenes are clearly labelled simulated and must never be presented as real
observations.
"""
from __future__ import annotations

import math
import struct
import zlib
from datetime import date
from typing import Callable, Optional

from ...geo import _det_hash, _field_value, cell_area_km2

# ---------------------------------------------------------------------------
# Grid / raster helpers
# ---------------------------------------------------------------------------

# Land-cover classes used by the synthetic scene model.
WATER, BUILT, VEG_DENSE, VEG_SPARSE, BARREN = 0, 1, 2, 3, 4
CLASS_NAMES = {
    WATER: "Water",
    BUILT: "Built-up",
    VEG_DENSE: "Dense vegetation",
    VEG_SPARSE: "Sparse vegetation",
    BARREN: "Barren / bare soil",
}

# (R, G, B, NIR, SWIR) surface-reflectance signatures per class.
_SIGNATURES = {
    WATER: (0.08, 0.16, 0.24, 0.06, 0.05),
    BUILT: (0.34, 0.32, 0.30, 0.27, 0.44),
    VEG_DENSE: (0.06, 0.13, 0.05, 0.42, 0.16),
    VEG_SPARSE: (0.24, 0.26, 0.18, 0.30, 0.30),
    BARREN: (0.42, 0.40, 0.34, 0.46, 0.52),
}

BAND_NAMES = ("red", "green", "blue", "nir", "swir")


def rasters(scene: dict) -> dict:
    """ETL-ish accessor returning the canonical band maps of a scene."""
    return scene["bands"]


def _zero_grid(cols: int, rows: int, fill=0.0) -> list:
    return [[fill] * cols for _ in range(rows)]


def _seasonal_green(date_obj: date) -> float:
    """Peak greenness for month 4 (Apr), trough for month 10 (Oct)."""
    return 0.5 - 0.5 * math.cos(2.0 * math.pi * ((date_obj.month + 8) % 12 / 12.0))


# ---------------------------------------------------------------------------
# Scene generation (deterministic, per location + date)
# ---------------------------------------------------------------------------


def _loc_seed(bbox: dict) -> int:
    """Stable seed for a small AOI: independent of the requested dates so both
    scenes share the same underlying landscape; only the dated evolution moves."""
    return _det_hash(
        _det_hash(round(bbox["min_lng"], 4), round(bbox["min_lat"], 4)),
        round((bbox["max_lng"] - bbox["min_lng"]) * (bbox["max_lat"] - bbox["min_lat"]), 6),
    )


def _growth_centres(bbox: dict, loc_seed: int, n: int = 6):
    """Deterministic urban-growth centres for the expansion model."""
    centres = []
    span_lng = bbox["max_lng"] - bbox["min_lng"]
    span_lat = bbox["max_lat"] - bbox["min_lat"]
    for i in range(n):
        h = _det_hash(loc_seed, i * 977)
        u1 = (h % 10_000) / 10_000.0
        h2 = _det_hash(loc_seed, i * 977 + 31)
        u2 = (h2 % 10_000) / 10_000.0
        centres.append(
            (bbox["min_lng"] + u1 * span_lng, bbox["min_lat"] + u2 * span_lat)
        )
    return centres


def _growth_strength(lat: float, lng: float, centres, sigma_km: float = 0.8) -> float:
    """0..1 radial intensity from the growth centres (gaussian sum, capped)."""
    total = 0.0
    for clng, clat in centres:
        d_lat = (lat - clat) * 110_574.0 / 1000.0
        d_lng = (lng - clng) * 111_320.0 * math.cos(math.radians(lat)) / 1000.0
        total += math.exp(-(d_lat ** 2 + d_lng ** 2) / (2.0 * sigma_km ** 2))
    return min(1.0, total)


def _rank_transform(field: list) -> list:
    """Replace each cell by its 0..1 rank within the scene.

    Rank-normalising keeps the synthetic landscape statistically stationary
    (a predictable share of water / built-up / vegetation at *any* AOI) while
    staying deterministic and preserving spatial smoothness.
    """
    rows = len(field)
    cols = len(field[0]) if rows else 0
    flat = sorted(v for row in field for v in row)
    n = max(len(flat) - 1, 1)
    rank_of = {v: i for i, v in enumerate(flat)}
    out = _zero_grid(cols, rows)
    for r in range(rows):
        for c in range(cols):
            out[r][c] = rank_of[field[r][c]] / n
    return out


def build_scene(
    date_obj: date,
    bbox: dict,
    cols: int,
    rows: int,
    evolution: float = 1.0,
) -> dict:
    """Create a deterministic synthetic surface-reflectance scene.

    ``evolution`` (typically 0 for Date 1, 1 for Date 2) drives urban
    expansion and water-line retreat. Scene composition is controlled through
    per-scene spatial ranks so any AOI yields a realistic, reproducible mix of
    water / built-up / vegetation / barren land cover.
    """
    loc_seed = _loc_seed(bbox)
    centres = _growth_centres(bbox, loc_seed)
    span_lng = bbox["max_lng"] - bbox["min_lng"]
    span_lat = bbox["max_lat"] - bbox["min_lat"]
    lng_step = span_lng / max(cols, 1)
    lat_step = span_lat / max(rows, 1)
    green = _seasonal_green(date_obj)

    hydr = _zero_grid(cols, rows)
    urban = _zero_grid(cols, rows)
    terra = _zero_grid(cols, rows)
    growth = _zero_grid(cols, rows)
    for r in range(rows):
        lat = bbox["min_lat"] + (r + 0.5) * lat_step
        for c in range(cols):
            lng = bbox["min_lng"] + (c + 0.5) * lng_step
            hydr[r][c] = _field_value(loc_seed + 1007, lat, lng, 0.85)
            urban[r][c] = _field_value(loc_seed + 2003, lat, lng, 1.1)
            terra[r][c] = _field_value(loc_seed + 3001, lat, lng, 0.6)
            growth[r][c] = _growth_strength(lat, lng, centres, sigma_km=0.8)

    hr = _rank_transform(hydr)
    ur = _rank_transform(urban)
    tr = _rank_transform(terra)
    water_thr = 0.22 * (1.0 - 0.35 * max(0.0, min(1.0, evolution)))
    built_thr = 0.78 - 0.12 * max(0.0, min(1.0, evolution))

    bands = {name: _zero_grid(cols, rows) for name in BAND_NAMES}
    classes = _zero_grid(cols, rows, fill=VEG_SPARSE)
    veg_boost = 1.0 + 0.18 * (green - 0.5)
    noise_seed = loc_seed + date_obj.toordinal() * 31

    for r in range(rows):
        lat = bbox["min_lat"] + (r + 0.5) * lat_step
        for c in range(cols):
            lng = bbox["min_lng"] + (c + 0.5) * lng_step
            if hr[r][c] < water_thr:
                cls = WATER
            elif ur[r][c] + 0.28 * growth[r][c] > built_thr:
                cls = BUILT
            elif tr[r][c] > 0.62:
                cls = VEG_DENSE
            elif tr[r][c] > 0.40:
                cls = VEG_SPARSE
            else:
                cls = BARREN
            classes[r][c] = cls
            sig = _SIGNATURES[cls]
            tex = _field_value(noise_seed, lat, lng, 0.35)
            for b_i, name in enumerate(BAND_NAMES):
                v = sig[b_i] * (1.0 + 0.16 * (2.0 * tex - 1.0))
                if cls in (VEG_DENSE, VEG_SPARSE) and name in ("nir", "red"):
                    v = v * veg_boost if name == "nir" else v * (2.0 - veg_boost)
                bands[name][r][c] = max(0.02, min(0.95, v))

    scene = {
        "date": date_obj.isoformat(),
        "bbox": bbox,
        "cols": cols,
        "rows": rows,
        "lng_step": lng_step,
        "lat_step": lat_step,
        "lats": [[bbox["min_lat"] + (r + 0.5) * lat_step] * cols for r in range(rows)],
        "lngs": [[bbox["min_lng"] + (c + 0.5) * lng_step for c in range(cols)] for _ in range(rows)],
        "classes": classes,
        "bands": bands,
        "simulated": True,
    }
    scene["ndvi"] = _index_band(scene, "nir", "red")
    scene["ndwi"] = _index_band(scene, "green", "nir")
    scene["ndbi"] = _index_band(scene, "swir", "nir")
    scene["brightness"] = _brightness(scene)
    return scene


def _index_band(scene: dict, a: str, b: str) -> list:
    cols, rows = scene["cols"], scene["rows"]
    A, B = scene["bands"][a], scene["bands"][b]
    out = _zero_grid(cols, rows)
    for r in range(rows):
        for c in range(cols):
            num = A[r][c] - B[r][c]
            den = A[r][c] + B[r][c] + 1e-9
            out[r][c] = num / den
    return out


def _brightness(scene: dict) -> list:
    cols, rows = scene["cols"], scene["rows"]
    rg = scene["bands"]["red"]
    gr = scene["bands"]["green"]
    bl = scene["bands"]["blue"]
    sw = scene["bands"]["swir"]
    out = _zero_grid(cols, rows)
    for r in range(rows):
        for c in range(cols):
            out[r][c] = (rg[r][c] + gr[r][c] + bl[r][c] + sw[r][c]) / 4.0
    return out


# ---------------------------------------------------------------------------
# Change detection
# ---------------------------------------------------------------------------

# Detection thresholds (index-units) and interpretation labels per technique.
TECHNIQUES = {
    "ndvi": {
        "label": "Vegetation index (NDVI)",
        "threshold": 0.045,
        "scale": 0.14,
        "gain": "Vegetation gain",
        "loss": "Vegetation loss",
        "signal": "vegetation",
        "query_words": ("vegetation", "forest", "green", "deforest", "crop", "agricultur", "tree"),
    },
    "ndbi": {
        "label": "Built-up index (NDBI)",
        "threshold": 0.035,
        "scale": 0.12,
        "gain": "Built-up gain (construction)",
        "loss": "Built-up loss (demolition)",
        "signal": "built-up / infrastructure",
        "query_words": ("build", "construction", "infrastruct", "urban", "road", "housing", "developer"),
    },
    "ndwi": {
        "label": "Water index (NDWI)",
        "threshold": 0.035,
        "scale": 0.12,
        "gain": "Water body gain",
        "loss": "Water body shrinkage",
        "signal": "surface water",
        "query_words": ("water", "lake", "river", "reservoir", "shrink", "berea", "wetland", "coast"),
    },
    "cva": {
        "label": "Change Vector Analysis",
        "threshold": 0.0,
        "scale": 0.12,
        "gain": "Change vector present",
        "loss": "No significant change",
        "signal": "compound change",
        "query_words": (),
    },
}


def diff_grids(a: list, b: list) -> list:
    """Diff two equal-size grids (b - a)."""
    out = []
    for r in range(len(a)):
        out.append([b[r][c] - a[r][c] for c in range(len(a[r]))])
    return out


def cva_vectors(scene1: dict, scene2: dict) -> tuple[list, list]:
    """Per-pixel change-vector magnitude [0..1] and dominant signed component."""
    cols, rows = scene1["cols"], scene1["rows"]
    dims = ["ndvi", "ndbi", "ndwi"]
    scales = [TECHNIQUES[d]["scale"] for d in dims]
    mag = _zero_grid(cols, rows)
    sign = _zero_grid(cols, rows, fill=1.0)
    for r in range(rows):
        for c in range(cols):
            m2, strongest = 0.0, 0.0
            for d_i, dim in enumerate(dims):
                delta = scene2[dim][r][c] - scene1[dim][r][c]
                m2 += (delta / scales[d_i]) ** 2
                if abs(delta) > abs(strongest):
                    strongest = delta
            mag[r][c] = min(1.0, math.sqrt(m2))
            sign[r][c] = 1.0 if strongest >= 0 else -1.0
    return mag, sign


def analyze_change(scene1: dict, scene2: dict, techniques: Optional[list] = None) -> dict:
    """Run the selected techniques between two scenes.

    Returns per-technique delta grids + boolean masks, the union change mask,
    a signed intensity heatmap and the CVA signature used for hotspot ranking.
    """
    if techniques:
        selected = [t for t in techniques if t in TECHNIQUES]
    else:
        selected = ["ndvi", "ndbi", "ndwi"]
    if "cva" in selected and len(selected) > 1:
        selected.remove("cva")  # cva is derived from the three spectral indices
    if not selected:
        selected = ["ndvi", "ndbi", "ndwi"]

    cols, rows = scene1["cols"], scene1["rows"]
    per_technique = {}
    union = _zero_grid(cols, rows, fill=False)

    for tech in selected:
        delta = diff_grids(scene1[tech], scene2[tech])
        thr = TECHNIQUES[tech]["threshold"]
        mask = _zero_grid(cols, rows, fill=False)
        for r in range(rows):
            for c in range(cols):
                if abs(delta[r][c]) > thr:
                    mask[r][c] = True
                    union[r][c] = True
        per_technique[tech] = {"delta": delta, "mask": mask}

    mag, sign = cva_vectors(scene1, scene2)
    per_technique["cva"] = {
        "delta": mag,
        "mask": [[bool(mag[r][c] > 0.22) for c in range(cols)] for r in range(rows)],
    }

    # Signed intensity heatmap: gain => warm (reds), loss => cool (blues).
    heat = _zero_grid(cols, rows)
    for r in range(rows):
        for c in range(cols):
            if not union[r][c] and not per_technique["cva"]["mask"][r][c]:
                continue
            m2, strongest = 0.0, 0.0
            for tech in selected:
                d = per_technique[tech]["delta"][r][c]
                m2 += (d / TECHNIQUES[tech]["scale"]) ** 2
                if abs(d) > abs(strongest):
                    strongest = d
            heat[r][c] = min(1.0, math.sqrt(m2 / len(selected)))

    heat_signed = [[heat[r][c] * sign[r][c] for c in range(cols)] for r in range(rows)]
    return {
        "techniques": per_technique,
        "union": union,
        "heat": heat_signed,
        "selected": selected,
    }


# ---------------------------------------------------------------------------
# Rendering: composites, heatmaps (pure stdlib)
# ---------------------------------------------------------------------------


def _sample_bilinear(grid: list, width: int, height: int, x: float, y: float) -> float:
    """Sample a grid at normalized (x, y) in [0, 1] with bilinear interpolation."""
    fx = x * (width - 1)
    fy = y * (height - 1)
    x0, y0 = int(fx), int(fy)
    x1, y1 = min(x0 + 1, width - 1), min(y0 + 1, height - 1)
    dx, dy = fx - x0, fy - y0
    return (
        grid[y0][x0] * (1 - dx) * (1 - dy)
        + grid[y0][x1] * dx * (1 - dy)
        + grid[y1][x0] * (1 - dx) * dy
        + grid[y1][x1] * dx * dy
    )


def _stretch(v: float, lo: float, hi: float) -> int:
    if hi <= lo:
        return 0
    t = max(0.0, min(1.0, (v - lo) / (hi - lo)))
    return int(round(t * 255.0))


_HEAT_STOPS = (
    (0.0, (0, 0, 0, 0)),
    (0.28, (59, 130, 246, 70)),
    (0.55, (34, 211, 238, 150)),
    (0.95, (245, 158, 11, 225)),
    (1.0, (185, 28, 28, 255)),
)


def _ramp(frac: float, stops) -> tuple:
    if frac <= stops[0][0]:
        return stops[0][1]
    for i in range(1, len(stops)):
        if frac <= stops[i][0]:
            x0, c0 = stops[i - 1]
            x1, c1 = stops[i]
            t = (frac - x0) / max(1e-6, x1 - x0)
            return tuple(round(c0[k] + (c1[k] - c0[k]) * t) for k in range(len(c0)))
    return stops[-1][1]


def _heat_color(h: float, sign: float) -> tuple:
    """Map signed intensity h*sign to RGBA (cool = loss, warm = gain)."""
    if sign >= 0:
        c = _ramp(h, _HEAT_STOPS)
    else:
        stops = tuple((x, (c[2], c[1], c[0], c[3])) for x, c in _HEAT_STOPS)
        c = _ramp(h, stops)
    alpha = 0 if h < 0.05 else max(60, min(255, int(c[3] * h)))
    return (c[0], c[1], c[2], alpha)


def render_scene_rgb(scene: dict, size: int = 360) -> bytes:
    """Render a true-colour composite (RGB PNG bytes) of a scene."""
    bbox = scene["bbox"]
    imin_lng, imax_lng = bbox["min_lng"], bbox["max_lng"]
    imin_lat, imax_lat = bbox["min_lat"], bbox["max_lat"]
    band_lo = min(
        min(min(row) for row in scene["bands"]["red"]),
        min(min(row) for row in scene["bands"]["green"]),
        min(min(row) for row in scene["bands"]["blue"]),
    )
    band_hi = max(
        max(max(row) for row in scene["bands"]["red"]),
        max(max(row) for row in scene["bands"]["green"]),
        max(max(row) for row in scene["bands"]["blue"]),
    )
    pixels = bytearray()
    for py in range(size):
        for px in range(size):
            lng = imin_lng + (px + 0.5) / size * (imax_lng - imin_lng)
            lat = imax_lat - (py + 0.5) / size * (imax_lat - imin_lat)
            x = (lng - imin_lng) / max(1e-9, imax_lng - imin_lng)
            y = 1.0 - (lat - imin_lat) / max(1e-9, imax_lat - imin_lat)
            r = _stretch(_sample_bilinear(scene["bands"]["red"], scene["cols"], scene["rows"], x, y), band_lo, band_hi)
            g = _stretch(_sample_bilinear(scene["bands"]["green"], scene["cols"], scene["rows"], x, y), band_lo, band_hi)
            b = _stretch(_sample_bilinear(scene["bands"]["blue"], scene["cols"], scene["rows"], x, y), band_lo, band_hi)
            pixels += bytes((r, g, b))
    return write_png(size, size, bytes(pixels), color_type=2)


def render_heatmap(heat_signed: list, size: int = 360) -> bytes:
    """Render the signed change heatmap as an RGBA PNG overlay."""
    rows = len(heat_signed)
    cols = len(heat_signed[0]) if rows else 0
    pixels = bytearray()
    for py in range(size):
        for px in range(size):
            x = (px + 0.5) / size
            y = (py + 0.5) / size
            h = _sample_bilinear(heat_signed, cols, rows, x, y)
            sign = 1.0 if h >= 0 else -1.0
            pixels += bytes(_heat_color(abs(h), sign))
    return write_png(size, size, bytes(pixels), color_type=6)


def render_magnitude(heat_signed: list, size: int = 360) -> bytes:
    """Render an unsigned 'magnitude' overlay using a hot colormap."""
    rows = len(heat_signed)
    cols = len(heat_signed[0]) if rows else 0
    stops = (
        (0.0, (0, 0, 0, 0)),
        (0.25, (59, 130, 246, 90)),
        (0.55, (250, 204, 21, 170)),
        (1.0, (239, 68, 68, 255)),
    )
    pixels = bytearray()
    for py in range(size):
        for px in range(size):
            x = (px + 0.5) / size
            y = (py + 0.5) / size
            h = abs(_sample_bilinear(heat_signed, cols, rows, x, y))
            c = _ramp(h, stops)
            alpha = 0 if h < 0.05 else max(40, min(255, int(c[3] * h)))
            pixels += bytes((c[0], c[1], c[2], alpha))
    return write_png(size, size, bytes(pixels), color_type=6)


def render_mask(mask: list, size: int = 360) -> bytes:
    """Render the boolean change mask as a translucent red overlay PNG."""
    rows = len(mask)
    cols = len(mask[0]) if rows else 0
    pixels = bytearray()
    for py in range(size):
        for px in range(size):
            x = (px + 0.5) / size
            y = (py + 0.5) / size
            yr = min(rows - 1, max(0, int(y * (rows - 1))))
            xr = min(cols - 1, max(0, int(x * (cols - 1))))
            hit = bool(mask[yr][xr])
            pixels += bytes((239, 68, 68, 150)) if hit else bytes((0, 0, 0, 0))
    return write_png(size, size, bytes(pixels), color_type=6)


def cluster_mask(mask: list, min_cluster: int = 6) -> list:
    """8-connected component labelling; clusters sorted desc by size.

    Returns a list of clusters; each cluster is a list of (row, col) cells.
    """
    rows = len(mask)
    cols = len(mask[0]) if rows else 0
    seen = [[False] * cols for _ in range(rows)]
    clusters = []
    for r in range(rows):
        for c in range(cols):
            if not mask[r][c] or seen[r][c]:
                continue
            stack = [(r, c)]
            seen[r][c] = True
            cells = []
            while stack:
                cr, cc = stack.pop()
                cells.append((cr, cc))
                for dr in (-1, 0, 1):
                    for dc in (-1, 0, 1):
                        if dr == 0 and dc == 0:
                            continue
                        nr, nc = cr + dr, cc + dc
                        if (
                            0 <= nr < rows and 0 <= nc < cols
                            and mask[nr][nc] and not seen[nr][nc]
                        ):
                            seen[nr][nc] = True
                            stack.append((nr, nc))
            if len(cells) >= min_cluster:
                clusters.append(cells)
    clusters.sort(key=len, reverse=True)
    return clusters


# ---------------------------------------------------------------------------
# PNG encoder (pure stdlib)
# ---------------------------------------------------------------------------


def _png_chunk(tag: bytes, data: bytes) -> bytes:
    return (
        struct.pack(">I", len(data))
        + tag + data
        + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)
    )


def write_png(width: int, height: int, pixels: bytes, color_type: int = 6) -> bytes:
    """Encode an RGB (color_type=2) or RGBA (color_type=6) buffer to PNG."""
    ihdr = struct.pack(">IIBBBBB", width, height, 8, color_type, 0, 0, 0)
    channels = 4 if color_type == 6 else 3
    stride = width * channels
    raw = bytearray()
    for y in range(height):
        raw += b"\x00" + pixels[y * stride:(y + 1) * stride]
    idat = zlib.compress(bytes(raw), 6)
    return (
        b"\x89PNG\r\n\x1a\n"
        + _png_chunk(b"IHDR", ihdr)
        + _png_chunk(b"IDAT", idat)
        + _png_chunk(b"IEND", b"")
    )


# ---------------------------------------------------------------------------
# GeoTIFF encoder (single-band greyscale, EPSG:4326) - pure stdlib
# ---------------------------------------------------------------------------


def write_geotiff(
    rows: list,
    min_lng: float,
    max_lat: float,
    pixel_w: float,
    pixel_h: float,
    epsg: int = 4326,
) -> bytes:
    """Encode a row-major 2D list of intensities (0..255) as a greyscale GeoTIFF.

    Follows the same minimal TIFF layout as ``services.geotools``: an 8-byte
    header, one IFD, a packed pixel strip and the long payloads (strip offset,
    byte count, ModelPixelScale, ModelTiepoint, GeoKeyDirectory). EPSG:4326
    geographic coordinates, little-endian, no compression.
    """
    height = len(rows)
    width = len(rows[0]) if height else 0
    if width == 0 or height == 0:
        raise ValueError("Empty raster cannot be encoded.")

    pixels = bytearray()
    for row in rows:
        for v in row:
            pixels.append(max(0, min(255, int(round(v)))))

    geo_key_dir = [
        1, 1, 0, 4,
        1024, 0, 1, 1,          # GTModelTypeGeoKey = 1 (geographic)
        1025, 0, 1, 1,          # GTRasterTypeGeoKey = 1
        2048 if epsg <= 32767 else 3072, 0, 1, epsg,
    ]
    pixel_scale = (pixel_w, pixel_h, 0.0)
    tiepoint = (0.0, 0.0, 0.0, min_lng, max_lat, 0.0)

    scale_raw = struct.pack("<3d", *pixel_scale)
    tie_raw = struct.pack("<6d", *tiepoint)
    geo_raw = struct.pack("<%dH" % len(geo_key_dir), *geo_key_dir)
    strip_count_raw = struct.pack("<I", len(pixels))

    n_inline = 8
    n_long = 5
    ifd_len = 2 + (n_inline + n_long) * 12 + 4
    pixel_data_off = 8 + ifd_len
    cursor = pixel_data_off + len(pixels)

    long_payloads = [
        (cursor, struct.pack("<I", pixel_data_off)),
        (cursor + 4, strip_count_raw),
    ]
    cursor += 8
    long_payloads.append((cursor, scale_raw)); cursor += len(scale_raw)
    long_payloads.append((cursor, tie_raw)); cursor += len(tie_raw)
    long_payloads.append((cursor, geo_raw)); cursor += len(geo_raw)

    def inline_entry(tid, ftype, count, packed):
        return struct.pack("<HHI", tid, ftype, count) + packed.ljust(4, b"\x00")

    def long_entry(tid, ftype, count, offset):
        return struct.pack("<HHI", tid, ftype, count) + struct.pack("<I", offset)

    entries = [
        inline_entry(256, 3, 1, struct.pack("<H", width)),
        inline_entry(257, 3, 1, struct.pack("<H", height)),
        inline_entry(258, 3, 1, struct.pack("<H", 8)),
        inline_entry(259, 3, 1, struct.pack("<H", 1)),
        inline_entry(262, 3, 1, struct.pack("<H", 1)),
        inline_entry(277, 3, 1, struct.pack("<H", 1)),
        inline_entry(278, 4, 1, struct.pack("<I", height)),
        inline_entry(284, 3, 1, struct.pack("<H", 1)),
        long_entry(273, 4, 1, long_payloads[0][0]),
        long_entry(279, 4, 1, long_payloads[1][0]),
        long_entry(33550, 12, 3, long_payloads[2][0]),
        long_entry(33922, 12, 6, long_payloads[3][0]),
        long_entry(34735, 3, len(geo_key_dir), long_payloads[4][0]),
    ]
    ifd = struct.pack("<H", len(entries)) + b"".join(entries) + struct.pack("<I", 0)
    body = b"".join(p for _, p in long_payloads)
    return b"II" + struct.pack("<HI", 42, 8) + ifd + bytes(pixels) + body