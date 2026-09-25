"""Map Type Catalog & dynamic cartographic layer school.

Holds the 32+ entry SatQuery AI map catalog (core / statistical /
environmental / property / digital categories), serves MapLibre + Deck.gl
style & layer configurations, and generates lightweight dynamic GeoJSON
(dots, flow arcs, choropleth cells, contour isolines, DEM grids) so every
analytic map type renders real data without external APIs.
"""
from __future__ import annotations

import hashlib
import json
import random
import uuid
from typing import Any, Optional

from .auth_store import get_auth_store_backend
from .config import settings
from .storage import get_db

# ---------------------------------------------------------------------------
# Domain constants
# ---------------------------------------------------------------------------

MAP_CATEGORIES = ["general", "statistical", "environmental", "property", "digital"]

CATEGORY_LABELS = {
    "general": "General & Core Reference",
    "statistical": "Statistical & Data Visualization",
    "environmental": "Environmental, Scientific & Applied",
    "property": "Special Navigation & Property",
    "digital": "Modern Digital & Cognitive",
}

# Public key-free tile endpoints (raster). Used as MapLibre raster sources.
TILES = {
    "imagery": "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
    "streets": "https://server.arcgisonline.com/ArcGIS/rest/services/World_Street_Map/MapServer/tile/{z}/{y}/{x}",
    "physical": "https://server.arcgisonline.com/ArcGIS/rest/services/World_Physical_Map/MapServer/tile/{z}/{y}/{x}",
    "shaded_relief": "https://server.arcgisonline.com/ArcGIS/rest/services/World_Shaded_Relief/MapServer/tile/{z}/{y}/{x}",
    "terrain_base": "https://server.arcgisonline.com/ArcGIS/rest/services/World_Terrain_Base/MapServer/tile/{z}/{y}/{x}",
    "ocean": "https://server.arcgisonline.com/ArcGIS/rest/services/Ocean_Basemap/MapServer/tile/{z}/{y}/{x}",
    "natgeo": "https://server.arcgisonline.com/ArcGIS/rest/services/NatGeo_World_Map/MapServer/tile/{z}/{y}/{x}",
    "voyager": "https://a.basemaps.cartocdn.com/rastertiles/voyager/{z}/{x}/{y}{r}.png",
    "positive": "https://a.basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png",
    "dark": "https://a.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png",
    "topo": "https://a.tile.opentopomap.org/{z}/{x}/{y}.png",
    "osm": "https://a.tile.openstreetmap.org/{z}/{x}/{y}.png",
    "dem_terrarium": "https://s3.amazonaws.com/elevation-tiles-prod/terrarium/{z}/{x}/{y}.png",
    "dem_normal": "https://s3.amazonaws.com/elevation-tiles-prod/normal/{z}/{x}/{y}.png",
    "dem_geotiff": "https://s3.amazonaws.com/elevation-tiles-prod/geotiff/{z}/{x}/{y}.tif",
}

ATTRIBUTION = {
    "imagery": "Esri, Maxar, Earthstar Geographics",
    "streets": "© Esri — World Street Map",
    "physical": "© Esri — World Physical",
    "shaded_relief": "© Esri — World Shaded Relief",
    "terrain_base": "© Esri — World Terrain",
    "ocean": "© Esri — Ocean Basemap, GEBCO",
    "natgeo": "© Esri, National Geographic",
    "voyager": "© CARTO © OSM",
    "positive": "© CARTO © OSM",
    "dark": "© CARTO © OSM",
    "topo": "© OpenTopoMap (CC-BY-SA)",
    "osm": "© OpenStreetMap contributors",
    "dem_terrarium": "Mapzen Terrain Tiles",
    "dem_normal": "Mapzen Terrain Tiles",
    "dem_geotiff": "Mapzen / AWS Terrain Tiles",
}
# ---------------------------------------------------------------------------
# Legend metadata builders
# ---------------------------------------------------------------------------


def _legend_gradient(label: str, stops: list[tuple[float, str, str]]) -> dict:
    """Continuous gradient legend (heat, isarithmic, elevation, ...)."""
    return {
        "type": "gradient",
        "label": label,
        "stops": [{"value": v, "color": c, "label": lbl} for v, c, lbl in stops],
    }


def _legend_classes(items: list[tuple[str, str]]) -> dict:
    """Discrete class legend (choropleth, biomes, zoning, ...)."""
    return {"type": "classes", "label": "Categories", "items": [{"label": l, "color": c} for l, c in items]}


def _legend_contour(label: str, levels: list[float], low: str = "#0ea5e9", high: str = "#ef4444") -> dict:
    steps = []
    n = max(len(levels) - 1, 1)
    for i, lvl in enumerate(levels):
        color = _lerp_hex(low, high, i / n)
        steps.append({"level": lvl, "color": color})
    return {"type": "contour", "label": label, "unit": "m", "levels": steps}


def _legend_symbols(label: str, unit: str, scale: list[tuple[float, float, str]]) -> dict:
    return {"type": "symbol", "label": label, "unit": unit, "scale": [{"value": v, "size": s, "label": l} for v, s, l in scale]}


def _lerp_hex(a: str, b: str, t: float) -> str:
    def _h(x: str) -> tuple[int, int, int]:
        return tuple(int(x[i : i + 2], 16) for i in (1, 3, 5))

    ca, cb = _h(a), _h(b)
    rgb = tuple(round(ca[i] + (cb[i] - ca[i]) * t) for i in range(3))
    return f"#{rgb[0]:02x}{rgb[1]:02x}{rgb[2]:02x}"


# ---------------------------------------------------------------------------
# Catalog entry builder
# ---------------------------------------------------------------------------


def _entry(
    key: str,
    title: str,
    category: str,
    summary: str,
    tile: str | None = None,
    engine: str = "maplibre",
    overlay: dict | None = None,
    legend: dict | None = None,
    tier: str = "all",
    is_3d: bool = False,
    is_temporal: bool = False,
    opacity: float = 0.75,
) -> dict:
    return {
        "map_id": str(uuid.uuid4()),
        "key": key,
        "title": title,
        "category": category,
        "summary": summary,
        "engine": engine,
        "tile_url": TILES.get(tile or "") if tile else None,
        "layer_config": {
            "base": {
                "source": TILES.get(tile or "") if tile else None,
                "attribution": ATTRIBUTION.get(tile or "") or "",
                "engine": engine,
            },
            "overlay": overlay or {"type": "none", "renderer": "maplibre", "opacity": opacity},
            "temporal": is_temporal,
            "3d": is_3d,
        },
        "legend": legend or {"type": "classes", "label": "Legend", "items": []},
        "permission_tier": tier,
        "is_3d_supported": is_3d,
        "is_temporal": is_temporal,
        "default_opacity": opacity,
        "source_types": _source_types(overlay or {}),
    }


def _source_types(overlay: dict) -> list[str]:
    kinds = {"Raster", "Vector", "GeoJSON"}
    otype = (overlay or {}).get("type", "none")
    if otype in ("flow", "heat", "dots", "choropleth", "symbols", "isarithmic", "time_series", "dem"):
        kinds.add("Deck.gl")
    return sorted(kinds)
# ---------------------------------------------------------------------------
# The catalog (32 map types across all five categories)
# ---------------------------------------------------------------------------

MAP_CATALOG: list[dict] = [
    # ---- 1. General & core reference ------------------------------------
    _entry("physical", "Physical Map", "general",
           "Landforms, elevation and drainage rendered in natural terrain coloring.",
           "physical", legend=_legend_gradient("Elevation", [(0, "#0e7490", "Sea"), (300, "#65a30d", "Lowland"), (1200, "#8a5a2b", "Highland"), (3500, "#b6ae9c", "Peaks")])),
    _entry("political", "Political Map", "general",
           "National and administrative boundaries with clear country styling.",
           "voyager", legend=_legend_classes([("International boundary", "#334155"), ("Admin-1 boundary", "#94a3b8"), ("Capital", "#0f172a")])),
    _entry("topographic", "Topographic Map", "general",
           "Contours, relief shading and spot heights for outdoor navigation.",
           "topo", legend=_legend_contour("Contour elevation", [0, 100, 250, 500, 1000, 2000, 3500])),
    _entry("road", "Road Map (Navigation)", "general",
           "Street-level navigation with route infrastructure emphasis.",
           "streets", legend=_legend_classes([("Highway", "#ef4444"), ("Primary road", "#f59e0b"), ("Secondary road", "#eab308"), ("Local road", "#e2e8f0")])),
    _entry("historical", "Historical Map", "general",
           "Period cartography overlay on muted vintage basemap.",
           "shaded_relief", legend=_legend_classes([("Modern coast", "#334155"), ("Historical route overlay", "#b45309")])),
    _entry("satellite", "Satellite Imagery (Optical Base)", "general",
           "High-resolution optical earth observation base imagery.",
           "imagery", legend=_legend_classes([("True color composite", "#22d3ee")])),
    # ---- 2. Statistical & data visualization ---------------------------
    _entry("thematic", "Thematic Map", "statistical",
           "Single-theme statistical distribution (population, income, yield).",
           "positive", overlay={"type": "choropleth", "renderer": "maplibre", "opacity": 0.8},
           legend=_legend_gradient("Theme value", [(0, "#fef3c7", "Low"), (0.5, "#fb923c", "Medium"), (1, "#7c3aed", "High")])),
    _entry("choropleth", "Choropleth Map", "statistical",
           "Enumeration units shaded by data class (quantiles / Jenks).",
           "positive", overlay={"type": "choropleth", "renderer": "maplibre", "opacity": 0.85},
           legend=_legend_classes([("Q1 (low)", "#eff6ff"), ("Q2", "#bfdbfe"), ("Q3", "#60a5fa"), ("Q4", "#2563eb"), ("Q5 (high)", "#1e3a8a")])),
    _entry("isarithmic", "Isarithmic (Isoline) Map", "statistical",
           "Smooth continuous-surface isolines (temperature, pressure, rainfall).",
           "dark", overlay={"type": "isarithmic", "renderer": "maplibre", "opacity": 0.9},
           legend=_legend_contour("Isoline level", [0, 0.2, 0.4, 0.6, 0.8, 1.0], "#38bdf8", "#fb7185"), is_3d=False),
    _entry("dot_distribution", "Dot Distribution Map", "statistical",
           "One-dot-per-N random placement showing density patterns.",
           "positive", overlay={"type": "dots", "renderer": "deck", "opacity": 0.9},
           legend=_legend_symbols("Density", "pts/km²", [(1, 3, "Low"), (5, 6, "Medium"), (20, 12, "High")])),
    _entry("proportional_symbol", "Proportional (Graduated) Symbol Map", "statistical",
           "Symbol size scaled by data magnitude at representative locations.",
           "positive", overlay={"type": "symbols", "renderer": "deck", "opacity": 0.85},
           legend=_legend_symbols("Magnitude", "units", [(10, 4, "10"), (100, 10, "100"), (500, 20, "500")])),
    _entry("cartogram", "Cartogram", "statistical",
           "Areas distorted proportionally to a statistic (population, GDP).",
           "positive", overlay={"type": "cartogram", "renderer": "deck", "opacity": 0.7},
           legend=_legend_gradient("Distortion factor", [(0, "#dbeafe", "Shrunk"), (0.5, "#93c5fd", "Neutral"), (1, "#1d4ed8", "Grown")])),
    _entry("dasymetric", "Dasymetric Map", "statistical",
           "Density refined by land-cover zones instead of crude areal units.",
           "terrain_base", overlay={"type": "choropleth", "renderer": "maplibre", "opacity": 0.75},
           legend=_legend_classes([("Urban core", "#991b1b"), ("Suburban", "#f59e0b"), ("Arable land", "#65a30d"), ("Forest", "#15803d"), ("Undeveloped", "#d6d3d1")])),
    _entry("flow", "Flow Map", "statistical",
           "Animated directional movement between origins and destinations.",
           "dark", overlay={"type": "flow", "renderer": "deck", "opacity": 0.85},
           legend=_legend_symbols("Flow magnitude", "units/hr", [(1, 1, "Low"), (5, 3, "Medium"), (20, 6, "High")]), is_temporal=True),
    _entry("cartographic_anamorphose", "Cartographic Anamorphoses", "statistical",
           "Value-distorted geography (size ~ variable).",
           "dark", overlay={"type": "cartogram", "renderer": "deck", "opacity": 0.7},
           legend=_legend_gradient("Anamorphic value", [(0, "#e0e7ff", "Low"), (0.5, "#818cf8", "Medium"), (1, "#4338ca", "High")])),
    _entry("heat", "Heat Map", "statistical",
           "Kernel-density smoothing of event intensity.",
           "dark", overlay={"type": "heat", "renderer": "deck", "opacity": 0.8},
           legend=_legend_gradient("Intensity", [(0, "rgba(0,0,255,0)", "None"), (0.33, "#2563eb", "Low"), (0.66, "#f59e0b", "Medium"), (1, "#ef4444", "High")])),
    # ---- 3. Environmental, scientific & applied -------------------------
    _entry("climate", "Climate Map", "environmental",
           "Temperature / precipitation surfaces with annotated isolines.",
           "terrain_base", overlay={"type": "isarithmic", "renderer": "maplibre", "opacity": 0.8},
           legend=_legend_contour("Mean annual temperature", [0, 5, 10, 15, 20, 25, 30], "#3b82f6", "#ef4444")),
    _entry("economic_resource", "Economic / Resource Map", "environmental",
           "Extractive resources, energy and agricultural production.",
           "dark", overlay={"type": "symbols", "renderer": "deck", "opacity": 0.85},
           legend=_legend_classes([("Oil & gas", "#f97316"), ("Minerals", "#eab308"), ("Agriculture", "#84cc16"), ("Hydropower", "#0ea5e9")])),
    _entry("geological", "Geological Map", "environmental",
           "Bedrock lithology and structural geology units.",
           "terrain_base", overlay={"type": "choropleth", "renderer": "maplibre", "opacity": 0.7},
           legend=_legend_classes([("Igneous", "#dc2626"), ("Metamorphic", "#7c3aed"), ("Sedimentary", "#ca8a04"), ("Quaternary", "#65a30d"), ("Water", "#0ea5e9")])),
    _entry("biomes_vegetation", "Biomes & Vegetation Map", "environmental",
           "Terrestrial biome and vegetation-cover classification.",
           "natgeo", overlay={"type": "choropleth", "renderer": "maplibre", "opacity": 0.8},
           legend=_legend_classes([("Tropical forest", "#15803d"), ("Temperate forest", "#65a30d"), ("Savanna", "#ca8a04"), ("Desert", "#d6d3d1"), ("Tundra", "#e0f2fe"), ("Ice", "#ffffff")])),
    _entry("bathymetric", "Bathymetric Map", "environmental",
           "Submarine depth contours and ocean-floor relief (isobaths).",
           "ocean", overlay={"type": "isarithmic", "renderer": "maplibre", "opacity": 0.8},
           legend=_legend_contour("Depth (m)", [0, -200, -1000, -2500, -4000, -6000], "#67e8f9", "#1e3a8a")),
    _entry("soil_pedological", "Soil (Pedological) Map", "environmental",
           "Soil taxonomy orders and dominant surface texture.",
           "terrain_base", overlay={"type": "choropleth", "renderer": "maplibre", "opacity": 0.75},
           legend=_legend_classes([("Alfisols", "#b45309"), ("Andisols", "#78350f"), ("Aridisols", "#a8a29e"), ("Mollisols", "#4d7c0f"), ("Ultisols", "#9a3412"), ("Histosols", "#1e293b")])),
    _entry("epidemiological", "Epidemiological Map", "environmental",
           "Disease incidence / outbreak cluster analysis.",
           "positive", overlay={"type": "heat", "renderer": "deck", "opacity": 0.8},
           legend=_legend_gradient("Incidence rate", [(0, "rgba(0,0,0,0)", "None"), (0.33, "#fde047", "Low"), (0.66, "#f97316", "Medium"), (1, "#991b1b", "High")])),
    _entry("air_quality", "Air Quality Map", "environmental",
           "Gaseous pollutant and particulate concentration surfaces.",
           "dark", overlay={"type": "heat", "renderer": "deck", "opacity": 0.8},
           legend=_legend_gradient("AQI", [(0, "rgba(0,0,0,0)", "Good"), (0.33, "#4ade80", "Moderate"), (0.66, "#f59e0b", "Unhealthy"), (1, "#991b1b", "Hazardous")])),
# ---- 4. Special navigation & property -------------------------------
    _entry("cadastral", "Cadastral Map", "property",
           "Parcel boundaries, ownership and land-valuation records.",
           "positive", overlay={"type": "cadastral", "renderer": "maplibre", "opacity": 0.9}, tier="analyst",
           legend=_legend_classes([("Freehold parcel", "#94a3b8"), ("Leasehold parcel", "#fbbf24"), ("Public land", "#4ade80"), ("Easement", "#c084fc")])),
    _entry("aeronautical", "Aeronautical Chart", "property",
           "Airspace, runways, navaids and obstacle clearance information.",
           "shaded_relief", overlay={"type": "aerodata", "renderer": "maplibre", "opacity": 0.8},
           legend=_legend_classes([("Controlled airspace", "#3b82f6"), ("Uncontrolled airspace", "#22d3ee"), ("Airway", "#8b5cf6"), ("Navaid", "#f43f5e")])),
    _entry("nautical", "Nautical Chart", "property",
           "Harbour soundings, buoys, lights and dangers-to-navigation.",
           "ocean", overlay={"type": "nautical", "renderer": "maplibre", "opacity": 0.85},
           legend=_legend_symbols("Sounding (m)", "m", [(2, 4, "2"), (10, 7, "10"), (30, 10, "30")])),
    _entry("zoning_land_use", "Zoning & Land Use Map", "property",
           "Municipal zoning districts and land-use categories.",
           "voyager", overlay={"type": "choropleth", "renderer": "maplibre", "opacity": 0.8},
           legend=_legend_classes([("Residential", "#fbbf24"), ("Commercial", "#ef4444"), ("Industrial", "#7c3aed"), ("Agricultural", "#84cc16"), ("Open space", "#4ade80")])),
    # ---- 5. Modern digital & cognitive ----------------------------------
    _entry("time_series", "Time-Series (Animated) Map", "digital",
           "Choropleth/dot sequences animated over time frames.",
           "positive", overlay={"type": "time_series", "renderer": "deck", "opacity": 0.85},
           legend=_legend_gradient("Value over time", [(0, "#fef3c7", "Low"), (0.5, "#fb923c", "Medium"), (1, "#7c3aed", "High")]),
           is_temporal=True),
    _entry("mental_cognitive", "Mental (Cognitive) Overlay", "digital",
           "Sketch-map / cognitive terrain reconstruction overlays.",
           "dark", overlay={"type": "mental", "renderer": "maplibre", "opacity": 0.6},
           legend=_legend_classes([("Cognitive anchor", "#22d3ee"), ("Mentally salient path", "#8b5cf6"), ("Fuzzy region", "#f59e0b")])),
    _entry("dem_3d", "Digital Elevation Model (DEM / 3D Terrain)", "digital",
           "Terrain mesh from vector elevation tiles with hillshade.",
           "dem_terrarium", overlay={"type": "dem", "renderer": "maplibre", "opacity": 1.0},
           legend=_legend_contour("Elevation (m)", [0, 300, 800, 1500, 2500, 4000]),
           is_3d=True),
    _entry("hillshade", "Hillshade Relief", "digital",
           "Analytical relief shading for terrain interpretation.",
           "dem_normal", overlay={"type": "dem", "renderer": "maplibre", "opacity": 1.0},
           legend=_legend_gradient("Relief direction", [(0, "#0f172a", "Shaded"), (1, "#f8fafc", "Lit")])),
]

CATALOG_BY_KEY: dict[str, dict] = {e["key"]: e for e in MAP_CATALOG}
# ---------------------------------------------------------------------------
# Persistence (document store + best-effort PostgreSQL table)
# ---------------------------------------------------------------------------

POSTGRES_CATALOG_DDL = """
CREATE TABLE IF NOT EXISTS map_catalog (
    map_id UUID PRIMARY KEY,
    key TEXT NOT NULL UNIQUE,
    title TEXT NOT NULL,
    category TEXT NOT NULL,
    tile_url TEXT,
    layer_config JSONB NOT NULL DEFAULT '{}',
    is_3d_supported BOOLEAN NOT NULL DEFAULT FALSE,
    is_temporal BOOLEAN NOT NULL DEFAULT FALSE,
    legend JSONB NOT NULL DEFAULT '{}',
    permission_tier TEXT NOT NULL DEFAULT 'all',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_map_catalog_category ON map_catalog(category);
"""


def sync_map_catalog() -> None:
    """Seed the document store (once) and best-effort sync the Postgres table."""
    db = get_db()
    try:
        if db.count("map_catalog", {}) == 0:
            for entry in MAP_CATALOG:
                db.insert("map_catalog", dict(entry))
    except Exception as exc:  # pragma: no cover
        print(f"[satquery] map catalog seed skipped: {exc}")
    _sync_postgres_catalog()


def _maybe_psycopg():
    try:
        import psycopg  # noqa: F401

        return True
    except ImportError:
        return False


def _sync_postgres_catalog() -> None:
    if not _maybe_psycopg() or get_auth_store_backend() != "postgres":
        return
    try:
        import psycopg

        conn = psycopg.connect(settings.POSTGRES_DSN, connect_timeout=3)
        conn.autocommit = True
        cur = conn.cursor()
        cur.execute(POSTGRES_CATALOG_DDL)
        for entry in MAP_CATALOG:
            cur.execute(
                """
                INSERT INTO map_catalog (map_id, key, title, category, tile_url,
                    layer_config, is_3d_supported, is_temporal, legend, permission_tier)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (key) DO UPDATE SET
                    title = EXCLUDED.title, category = EXCLUDED.category,
                    layer_config = EXCLUDED.layer_config, legend = EXCLUDED.legend,
                    permission_tier = EXCLUDED.permission_tier
                """,
                (
                    entry["map_id"],
                    entry["key"],
                    entry["title"],
                    entry["category"],
                    entry.get("tile_url"),
                    json.dumps(entry.get("layer_config") or {}),
                    bool(entry.get("is_3d_supported")),
                    bool(entry.get("is_temporal")),
                    json.dumps(entry.get("legend") or {}),
                    entry.get("permission_tier", "all"),
                ),
            )
        conn.close()
    except Exception as exc:  # pragma: no cover
        print(f"[satquery] map_catalog postgres sync skipped: {exc}")


_TIER_RANK = {"all": 0, "analyst": 1, "organization": 2, "admin": 3}
_ROLE_TIER = {"user": 0, "analyst": 1, "organization": 2, "admin": 3}


def permission_gate(entry: dict, user: dict | None) -> bool:
    """Return True when the current user may use this catalog entry."""
    if not user:
        return True
    min_rank = _TIER_RANK.get(entry.get("permission_tier", "all"), 0)
    rank = _ROLE_TIER.get((user.get("role") or "user"), 0)
    if entry.get("permission_tier") == "organization":
        return rank >= 2  # org accounts or admins
    return rank >= min_rank


def public_catalog(filter_category: str | None = None, query: str | None = None) -> list[dict]:
    """Catalog entries with permission metadata applied, searchable."""
    out = []
    q = (query or "").strip().lower()
    for entry in MAP_CATALOG:
        if filter_category and entry["category"] != filter_category:
            continue
        if q and q not in entry["title"].lower() and q not in entry["key"].lower():
            continue
        out.append(_public_entry(entry))
    return out


def _public_entry(entry: dict) -> dict:
    return {
        "map_id": entry.get("map_id"),
        "key": entry["key"],
        "title": entry["title"],
        "category": entry["category"],
        "summary": entry["summary"],
        "engine": entry.get("engine", "maplibre"),
        "tile_url": entry.get("tile_url"),
        "layer_config": entry.get("layer_config"),
        "legend": entry.get("legend"),
        "permission_tier": entry.get("permission_tier", "all"),
        "is_3d_supported": entry.get("is_3d_supported", False),
        "is_temporal": entry.get("is_temporal", False),
    }


def get_entry(key: str) -> dict | None:
    return CATALOG_BY_KEY.get(key)
# ---------------------------------------------------------------------------
# Dynamic cartographic data generation
# ---------------------------------------------------------------------------

DEFAULT_BBOX = [68.0, 6.0, 98.0, 38.0]  # min_lng, min_lat, max_lng, max_lat
TIME_FRAMES = 12


def clamp_bbox(bbox: Any) -> list[float]:
    if isinstance(bbox, str) and len(bbox.split(",")) == 4:
        try:
            return [float(x) for x in bbox.split(",")]
        except ValueError:
            pass
    if isinstance(bbox, (list, tuple)) and len(bbox) == 4:
        try:
            return [float(x) for x in bbox]
        except (TypeError, ValueError):
            pass
    return list(DEFAULT_BBOX)


def _rng(*parts: Any):
    raw = "|".join(str(p) for p in parts)
    digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()
    return random.Random(int(digest[:16], 16))


def _scalar_field(lng: float, lat: float, key: str, t: float = 0.0) -> float:
    """Normalized 0..1 smooth synthetic field used by all generators."""
    import math

    v = (
        math.sin(lng * 0.35 + t * 0.6) * math.cos(lat * 0.28 + t * 0.4)
        + 0.5 * math.sin(lng * 1.3 + lat * 0.9)
        + 0.3 * math.sin((lng + lat) * 2.1 + t * 1.2)
        + 0.2 * math.cos(lng * 0.9 - lat * 1.7)
    )
    return max(0.0, min(1.0, 0.5 + 0.5 * v))


def _grad_color(stops: list[tuple[float, str, str]], value: float) -> str:
    """Sample a (value,color,label) stop list at `value` (0..1)."""
    value = max(0.0, min(1.0, value))
    for i, (v, color, _label) in enumerate(stops):
        if value <= v:
            if i == 0 or v == stops[i - 1][0]:
                return color
            v0, c0 = stops[i - 1][0], stops[i - 1][1]
            return _lerp_hex(c0, color, (value - v0) / (v - v0))
    return stops[-1][1]


def _point_feature(lng: float, lat: float, props: dict) -> dict:
    return {"type": "Feature", "geometry": {"type": "Point", "coordinates": [round(lng, 5), round(lat, 5)]}, "properties": props}


def _polygon_feature(ring: list[tuple[float, float]], props: dict) -> dict:
    coords = [[[round(lng, 5), round(lat, 5)] for lng, lat in ring]]
    return {"type": "Feature", "geometry": {"type": "Polygon", "coordinates": coords}, "properties": props}


def _line_feature(coords: list[tuple[float, float]], props: dict) -> dict:
    line = [[round(x, 5), round(y, 5)] for x, y in coords]
    return {"type": "Feature", "geometry": {"type": "LineString", "coordinates": line}, "properties": props}


def _generate_points(key: str, bbox: list[float], count: int, t: float) -> dict:
    min_lng, min_lat, max_lng, max_lat = bbox
    rng = _rng(key, "points", int(t * 100))
    features = []
    for _ in range(count):
        lng, lat = rng.uniform(min_lng, max_lng), rng.uniform(min_lat, max_lat)
        density = _scalar_field(lng, lat, key, t)
        if density < rng.random() * 0.75:  # clustering poisson-ish
            continue
        value = round(rng.uniform(1, 100) * density, 2)
        features.append(
            _point_feature(lng, lat, {"value": value, "t": round(t, 2), "class": "event" if density > 0.62 else "sparse"})
        )
    return {"type": "FeatureCollection", "features": features, "frame": t, "frames": TIME_FRAMES}


def _generate_flow(key: str, bbox: list[float], count: int, t: float) -> dict:
    min_lng, min_lat, max_lng, max_lat = bbox
    rng = _rng(key, "flow", int(t * 100))
    cx, cy = (min_lng + max_lng) / 2, (min_lat + max_lat) / 2
    features = []
    for i in range(count):
        sx, sy = rng.uniform(min_lng, max_lng), rng.uniform(min_lat, max_lat)
        magnitude = round(rng.uniform(1, 40) * _scalar_field(sx, sy, key, t), 2)
        tx = sx + (cx - sx) * 0.55 + rng.uniform(-1.2, 1.2)
        ty = sy + (cy - sy) * 0.55 + rng.uniform(-1.0, 1.0)
        features.append(
            _line_feature(
                [(sx, sy), ((sx + tx) / 2, (sy + ty) / 2), (tx, ty)],
                {"magnitude": magnitude, "t": round(t, 2), "from": f"src-{i}", "to": f"dst-{i}", "animated": True},
            )
        )
    return {"type": "FeatureCollection", "features": features, "frame": t, "frames": TIME_FRAMES}
DISCRETE_CLASSES: dict[str, list[tuple[str, str]]] = {
    "choropleth": [("Q1 (low)", "#eff6ff"), ("Q2", "#bfdbfe"), ("Q3", "#60a5fa"), ("Q4", "#2563eb"), ("Q5 (high)", "#1e3a8a")],
    "dasymetric": [("Urban core", "#991b1b"), ("Suburban", "#f59e0b"), ("Arable land", "#65a30d"), ("Forest", "#15803d"), ("Undeveloped", "#d6d3d1")],
    "biomes_vegetation": [("Tropical forest", "#15803d"), ("Temperate forest", "#65a30d"), ("Savanna", "#ca8a04"), ("Desert", "#d6d3d1"), ("Tundra", "#e0f2fe"), ("Ice", "#ffffff")],
    "geological": [("Igneous", "#dc2626"), ("Metamorphic", "#7c3aed"), ("Sedimentary", "#ca8a04"), ("Quaternary", "#65a30d"), ("Water", "#0ea5e9")],
    "soil_pedological": [("Alfisols", "#b45309"), ("Andisols", "#78350f"), ("Aridisols", "#a8a29e"), ("Mollisols", "#4d7c0f"), ("Ultisols", "#9a3412"), ("Histosols", "#1e293b")],
    "cadastral": [("Freehold parcel", "#94a3b8"), ("Leasehold parcel", "#fbbf24"), ("Public land", "#4ade80"), ("Easement", "#c084fc")],
    "zoning_land_use": [("Residential", "#fbbf24"), ("Commercial", "#ef4444"), ("Industrial", "#7c3aed"), ("Agricultural", "#84cc16"), ("Open space", "#4ade80")],
    "mental_cognitive": [("Cognitive anchor", "#22d3ee"), ("Mentally salient path", "#8b5cf6"), ("Fuzzy region", "#f59e0b")],
    "aeronautical": [("Controlled airspace", "#3b82f6"), ("Uncontrolled airspace", "#22d3ee"), ("Airway", "#8b5cf6"), ("Navaid", "#f43f5e")],
    "economic_resource": [("Oil & gas", "#f97316"), ("Minerals", "#eab308"), ("Agriculture", "#84cc16"), ("Hydropower", "#0ea5e9")],
}

GRADIENT_STOPS: dict[str, list[tuple[float, str, str]]] = {
    "thematic": [(0, "#fef3c7", "Low"), (0.5, "#fb923c", "Medium"), (1, "#7c3aed", "High")],
    "cartogram": [(0, "#dbeafe", "Shrunk"), (0.5, "#93c5fd", "Neutral"), (1, "#1d4ed8", "Grown")],
    "cartographic_anamorphose": [(0, "#e0e7ff", "Low"), (0.5, "#818cf8", "Medium"), (1, "#4338ca", "High")],
}


def _generate_polygons(key: str, bbox: list[float], grid: int = 9, t: float = 0.0) -> dict:
    min_lng, min_lat, max_lng, max_lat = bbox
    rng = _rng(key, "grid", int(t * 100))
    classes = DISCRETE_CLASSES.get(key)
    w, h = (max_lng - min_lng) / grid, (max_lat - min_lat) / grid
    features = []
    for i in range(grid):
        for j in range(grid):
            lng0, lat0 = min_lng + i * w, min_lat + j * h
            lng1, lat1 = lng0 + w, lat0 + h
            cx, cy = (lng0 + lng1) / 2, (lat0 + lat1) / 2
            jx, jy = rng.uniform(-0.05, 0.05) * w, rng.uniform(-0.05, 0.05) * h
            ring = [
                (lng0 + jx, lat0 + jy), (lng1 + jx, lat0 + jy),
                (lng1 + jx, lat1 + jy), (lng0 + jx, lat1 + jy), (lng0 + jx, lat0 + jy),
            ]
            value = round(_scalar_field(cx, cy, key, t), 3)
            if classes:
                cls = classes[min(int(value * len(classes)), len(classes) - 1)]
                props = {"value": value, "class": cls[0], "color": cls[1]}
            else:
                props = {"value": value, "class": "", "color": _grad_color(GRADIENT_STOPS.get(key, GRADIENT_STOPS["thematic"]), value)}
            props["t"] = round(t, 2)
            features.append(_polygon_feature(ring, props))
    return {"type": "FeatureCollection", "features": features, "frame": t, "frames": TIME_FRAMES}
# ---------------------------------------------------------------------------
# Isolines (marching squares) — isarithmic, climate, bathymetric, DEM
# ---------------------------------------------------------------------------

def _contour_segments_for_cell(level: float, a: float, b: float, c: float, d: float,
                               lng0: float, lat0: float, lng1: float, lat1: float) -> list[list[tuple[float, float]]]:
    """Return the 1D segments crossing the cell (TL=a, TR=b, BR=c, BL=d)."""
    # corner -> edge interpolants
    top = _edge_point((lng0, lat1), (lng1, lat1), a, b, level)
    right = _edge_point((lng1, lat1), (lng1, lat0), b, c, level)
    bottom = _edge_point((lng1, lat0), (lng0, lat0), c, d, level)
    left = _edge_point((lng0, lat0), (lng0, lat1), d, a, level)

    idx = (8 if a >= level else 0) | (4 if b >= level else 0) | (2 if c >= level else 0) | (1 if d >= level else 0)
    table = {
        0: [], 15: [],
        1: [(bottom, left)], 2: [(right, bottom)], 3: [(right, left)],
        4: [(top, right)], 5: [(top, bottom), (right, left)],  # ambiguous saddle
        6: [(top, bottom)], 7: [(top, left)],
        8: [(left, top)], 9: [(left, right), (bottom, top)], 10: [(left, right)],
        11: [(bottom, top)], 12: [(right, left)], 13: [(bottom, left)], 14: [(top, right)],
    }
    return [list(seg) for seg in table.get(idx, []) if None not in seg]


def _edge_point(p0: tuple[float, float], p1: tuple[float, float], v0: float, v1: float, level: float) -> tuple[float, float] | None:
    denom = v1 - v0
    if abs(denom) < 1e-12:
        return None
    t = max(0.0, min(1.0, (level - v0) / denom))
    return (p0[0] + t * (p1[0] - p0[0]), p0[1] + t * (p1[1] - p0[1]))


def _generate_isolines(key: str, bbox: list[float], levels: list[float], k: int = 24, t: float = 0.0) -> dict:
    min_lng, min_lat, max_lng, max_lat = bbox
    grid_values: dict[tuple[int, int], float] = {}
    features: list[dict] = []
    for level in levels:
        segments: list[list[tuple[float, float]]] = []
        for i in range(k):
            for j in range(k):
                lng0 = min_lng + (max_lng - min_lng) * i / k
                lng1 = min_lng + (max_lng - min_lng) * (i + 1) / k
                lat0 = min_lat + (max_lat - min_lat) * j / k
                lat1 = min_lat + (max_lat - min_lat) * (j + 1) / k
                key_cache = (i, j)
                if key_cache not in grid_values:
                    a = _scalar_field((lng0 + lng1) / 2, lat1, key, t)
                    b = _scalar_field(lng1, (lat0 + lat1) / 2, key, t)
                    c = _scalar_field((lng0 + lng1) / 2, lat0, key, t)
                    d = _scalar_field(lng0, (lat0 + lat1) / 2, key, t)
                    grid_values[key_cache] = (a, b, c, d)
                a, b, c, d = grid_values[key_cache]
                segments.extend(_contour_segments_for_cell(level, a, b, c, d, lng0, lat0, lng1, lat1))
        for seg in segments:
            features.append(
                _line_feature(seg, {"level": level, "color": _contour_color(level, levels), "class": f"{level:g}"})
            )
    return {"type": "FeatureCollection", "features": features, "levels": levels, "frame": t, "frames": TIME_FRAMES}


def _contour_color(level: float, levels: list[float]) -> str:
    lo, hi = min(levels), max(levels)
    t = (level - lo) / (hi - lo) if hi > lo else 0.5
    return _lerp_hex("#38bdf8", "#fb7185", max(0.0, min(1.0, t)))


def _generate_dem_points(key: str, bbox: list[float], count: int, t: float = 0.0) -> dict:
    min_lng, min_lat, max_lng, max_lat = bbox
    grid = 14
    features = []
    for i in range(grid):
        for j in range(grid):
            lng = min_lng + (max_lng - min_lng) * (i + 0.5) / grid
            lat = min_lat + (max_lat - min_lat) * (j + 0.5) / grid
            elev = round(_scalar_field(lng, lat, "dem", t) ** 1.4 * 4500, 1)
            features.append(_point_feature(lng, lat, {"elevation": elev, "class": "dem_sample"}))
    return {"type": "FeatureCollection", "features": features, "frame": t, "frames": TIME_FRAMES}


def _generate_time_series(key: str, bbox: list[float], count: int, frame: int) -> dict:
    """Points whose `t` (0..frames-1) maps to the current animation frame."""
    collection = _generate_points(key, bbox, count, float(frame % TIME_FRAMES))
    collection["frames"] = TIME_FRAMES
    collection["frame"] = frame
    return collection
# ---------------------------------------------------------------------------
# Dispatcher + layer response
# ---------------------------------------------------------------------------

ISOLINE_LEVELS: dict[str, list[float]] = {
    "isarithmic": [0.15, 0.3, 0.45, 0.6, 0.75, 0.9],
    "climate": [0.15, 0.3, 0.45, 0.6, 0.75, 0.9],
    "bathymetric": [0.1, 0.25, 0.45, 0.65, 0.85],
    "topographic": [0.1, 0.3, 0.5, 0.7, 0.9],
}


def generate_layer_data(key: str, bbox: list[float], count: int = 240, time_index: int = 0) -> dict:
    """Return deterministic GeoJSON/meta for a catalog entry's analytic layer."""
    bounds = clamp_bbox(bbox)
    frame = max(0, int(time_index)) % TIME_FRAMES
    t = frame / max(TIME_FRAMES - 1, 1)
    entry = get_entry(key)
    overlay_type = (entry.get("layer_config") or {}).get("overlay", {}).get("type", "none") if entry else ""

    if overlay_type in ("dots", "heat"):
        data = _generate_points(key, bounds, count, t)
    elif overlay_type == "flow":
        data = _generate_flow(key, bounds, count, t)
    elif overlay_type == "time_series":
        data = _generate_time_series(key, bounds, count, frame)
    elif overlay_type == "dem":
        data = _generate_dem_points(key, bounds, count, t)
    elif overlay_type == "isarithmic":
        levels = ISOLINE_LEVELS.get(key, ISOLINE_LEVELS["isarithmic"])
        data = _generate_isolines(key, bounds, levels, t=t)
    elif overlay_type in ("choropleth", "cartogram", "cadastral", "mental", "aerodata"):
        data = _generate_polygons(key, bounds, t=t)
    elif overlay_type == "nautical":
        pts = _generate_points(key, bounds, count, t)
        for f in pts["features"]:
            f["properties"]["sounding_m"] = round(f["properties"]["value"] * 30, 1)
        data = pts
    else:
        data = {"type": "FeatureCollection", "features": [], "note": "Base reference map — no analytic overlay."}
    return {"data": data, "key": key, "overlay_type": overlay_type, "bbox": bounds}


def layer_response(key: str, bbox: list[float], count: int, time_index: int, dynamic: bool) -> dict:
    entry = get_entry(key)
    if not entry:
        return {"error": True, "detail": f"Unknown map type: {key}"}
    payload: dict = {"entry": _public_entry(entry)}
    if dynamic:
        payload.update(generate_layer_data(key, bbox, count, time_index))
    else:
        payload["data"] = {"type": "FeatureCollection", "features": [], "dynamic": False}
    return payload