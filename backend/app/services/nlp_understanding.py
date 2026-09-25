"""Rule-based natural-language query understanding.

A lightweight, deterministic NLP layer that extracts the five core slots used
by the pipeline -- location, time range, phenomenon, data type and requested
analysis -- plus a recommended AI agent. An optional LLM hook can be enabled
later (LLM_API_KEY) to improve off-vocabulary extraction; until then every
extraction is explainable and works fully offline.
"""
from __future__ import annotations

import datetime as dt
import re
from typing import Optional

from .gazetteer import resolve_location

# ---------------------------------------------------------------------------
# Vocabularies
# ---------------------------------------------------------------------------

PHENOMENA = {
    "flood": ["flood", "inundat", "submerg", "waterlog", "overflow", "swollen river"],
    "wildfire": ["wildfire", "bushfire", "forest fire", "burn scar", "burned area", "fire"],
    "drought": ["drought", "arid", "water scarcity"],
    "deforestation": ["deforestation", "forest loss", "clear cut", "tree cover loss"],
    "urban_growth": ["urban growth", "urban expansion", "sprawl", "urbanisation", "urbanization"],
    "crop": ["crop", "agriculture", "farmland", "harvest", "yield", "vegetation health", "ndvi"],
    "landslide": ["landslide", "land slip"],
    "earthquake": ["earthquake", "seismic"],
    "cyclone": ["cyclone", "hurricane", "typhoon", "storm"],
    "weather": ["weather", "forecast", "conditions", "humidity", "temperature"],
    "water_quality": ["water quality", "turbidity", "algal bloom", "algae"],
    "snow": ["snow cover", "glacier", "snowmelt"],
    "coastal": ["coastal", "shoreline", "erosion"],
}

DATA_TYPES = {
    "SAR": ["sar", "radar", "sentinel-1", "synthetic aperture", "backscatter", "c-band"],
    "Optical": ["optical", "sentinel-2", "landsat", "rgb", "multispectral", "visible"],
    "DEM": ["dem", "elevation", "altitude", "terrain", "topography", "slope", "relief"],
    "Vector": ["vector", "boundaries", "districts", "roads", "infrastructure", "shapefile"],
    "Time-Series": ["time series", "time-series", "over time", "trend", "monthly", "temporal"],
    "Tabular": ["tabular", "table", "statistics", "rainfall records", "csv", "weather records"],
}

ANALYSES = {
    "flood-mapping": ["flood map", "flooded", "affected areas", "inundation map"],
    "change-detection": ["change detect", "changed area", "before and after", "difference", "gain/loss"],
    "classification": ["classify", "classification", "land cover", "crop type", "land use"],
    "object-detection": ["object detect", "detect vessel", "ships", "buildings", "vehicles"],
    "time-series": ["trend", "time series", "seasonality", "forecast", "anomaly"],
    "image-search": ["find images", "search imagery", "retrieve scenes", "satellite images of"],
    "fusion": ["fuse", "fusion", "combine", "integrate", "multi-source", "multi-sensor"],
    "ndvi": ["ndvi", "vegetation index", "vegetation health", "greenness", "biomass index", "veg index"],
    "ndwi": ["ndwi", "water index", "moisture index", "surface water index", "wetland index"],
    "ndbi": ["ndbi", "built-up index", "urban index", "built up index", "impervious index"],
    "sar-backscatter": ["backscatter", "sar intensity", "radar signature", "surface roughness", "sar amplitude"],
}

AGENT_RULES = {
    "sar": ["sar", "radar", "sentinel-1", "backscatter", "sar intensity", "sar amplitude", "surface roughness"],
    "optical": ["optical", "sentinel-2", "landsat", "ndvi", "ndwi", "ndbi", "rgb", "visible", "greenness", "vegetation health"],
    "temporal": ["trend", "over time", "time series", "temporal", "monthly", "seasonal"],
    "fusion": ["fuse", "fusion", "combine", "multi-source", "multi-sensor", "integrate"],
}

# phenomenon -> (default data type, default analysis, default agent)
PHENOMENON_DEFAULTS = {
    "flood": ("SAR", "flood-mapping", "sar"),
    "wildfire": ("Optical", "change-detection", "optical"),
    "drought": ("Optical", "time-series", "temporal"),
    "deforestation": ("SAR", "change-detection", "sar"),
    "urban_growth": ("Optical", "change-detection", "optical"),
    "crop": ("Optical", "classification", "optical"),
    "landslide": ("DEM", "change-detection", "optical"),
    "earthquake": ("SAR", "change-detection", "sar"),
    "cyclone": ("SAR", "flood-mapping", "fusion"),
    "weather": ("Time-Series", "time-series", "temporal"),
    "water_quality": ("Optical", "classification", "optical"),
    "snow": ("Optical", "change-detection", "optical"),
    "coastal": ("Optical", "change-detection", "optical"),
}

MONTHS = {
    "january": 1, "february": 2, "march": 3, "april": 4, "may": 5,
    "june": 6, "july": 7, "august": 8, "september": 9, "october": 10,
    "november": 11, "december": 12,
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "jun": 6, "jul": 7,
    "aug": 8, "sep": 9, "sept": 9, "oct": 10, "nov": 11, "dec": 12,
}

_ISO_DATE = re.compile(r"\b(20\d{2})[-/](\d{1,2})[-/](\d{1,2})\b")
_MONTH_YEAR = re.compile(
    r"\b(" + "|".join(MONTHS.keys()) + r")\w*\s+(\d{4})\b"
)
def _month_range(year: int, month: int) -> tuple[str, str]:
    start = dt.date(year, month, 1)
    if month == 12:
        end = dt.date(year + 1, 1, 1) - dt.timedelta(days=1)
    else:
        end = dt.date(year, month + 1, 1) - dt.timedelta(days=1)
    return start.isoformat(), end.isoformat()


def _parse_dates(text: str) -> tuple[Optional[str], Optional[str], list[str]]:
    """Return (start, end, explanation) or (None, None, [])."""
    low = text.lower()
    explanations: list[str] = []

    iso = list(_ISO_DATE.finditer(text))
    if len(iso) >= 2:
        d1 = f"{iso[0].group(1)}-{int(iso[0].group(2)):02d}-{int(iso[0].group(3)):02d}"
        d2 = f"{iso[1].group(1)}-{int(iso[1].group(2)):02d}-{int(iso[1].group(3)):02d}"
        start, end = sorted([d1, d2])
        explanations.append(f"Date range {start} to {end} (explicit dates).")
        return start, end, explanations
    if len(iso) == 1:
        d = f"{iso[0].group(1)}-{int(iso[0].group(2)):02d}-{int(iso[0].group(3)):02d}"
        explanations.append(f"Single date {d}.")
        return d, d, explanations

    months = re.findall(_MONTH_YEAR, low)
    if months:
        year = int(months[0][1])
        month = MONTHS[months[0][0].rstrip("s")]
        start, end = _month_range(year, month)
        explanations.append(f"Date range {start} to {end} (month {months[0][1]}).")
        return start, end, explanations

    # bare year, e.g. "in 2023"
    year_match = re.search(r"\b(20\d{2})\b", text)
    if year_match:
        y = int(year_match.group(1))
        explanations.append(f"Date range {y}-01-01 to {y}-12-31 (year {y}).")
        return f"{y}-01-01", f"{y}-12-31", explanations

    # relative: last N months/years
    rel = re.search(r"last\s+(\d+)\s+(month|months|year|years)", low)
    if rel:
        n = int(rel.group(1))
        unit = rel.group(2)
        now = dt.date.today()
        if unit.startswith("month"):
            end = now.isoformat()
            start = (now - dt.timedelta(days=30 * n)).isoformat()
        else:
            end = now.isoformat()
            start = (now.replace(year=now.year - n)).isoformat()
        explanations.append(f"Date range {start} to {end} (relative: last {n} {unit}).")
        return start, end, explanations

    return None, None, []


def _find_keywords(text_lower: str, vocab: dict) -> Optional[tuple[str, float]]:
    """Return the best matching (key, score) for a vocabulary."""
    best_key, best_score = None, 0.0
    for key, keywords in vocab.items():
        for kw in keywords:
            if kw in text_lower:
                score = 1.0 + (len(kw) / 20.0)
                if score > best_score:
                    best_key, best_score = key, score
    return (best_key, best_score) if best_key else None
def understand_query(text: str) -> dict:
    """Parse a natural-language query into structured understanding slots."""
    text = " ".join(text.split())
    low = text.lower()
    explanations: list[str] = []

    # --- location ---
    location_meta = resolve_location(low)
    loc_name = location_meta["name"] if location_meta else None
    bbox = location_meta["bbox"] if location_meta else None
    if loc_name:
        explanations.append(
            f"Detected location: {loc_name} "
            f"({location_meta['kind']}, {location_meta['country']})."
        )
    else:
        explanations.append(
            "No specific location detected; will use the most relevant "
            "dataset extent instead."
        )

    # --- phenomenon ---
    phen = _find_keywords(low, PHENOMENA)
    if phen:
        explanations.append(f"Detected phenomenon: {phen[0].replace('_', ' ').title()}.")
    else:
        explanations.append("No specific natural-hazard phenomenon detected.")

    # --- data type ---
    dtype = _find_keywords(low, DATA_TYPES)
    if dtype:
        explanations.append(f"Detected data type preference: {dtype[0]}.")

    # --- date ---
    start, end, date_expl = _parse_dates(text)
    explanations.extend(date_expl)
    if not start:
        explanations.append("No date given; using the most recent available scenes.")

    # --- analysis ---
    analysis = _find_keywords(low, ANALYSES)
    if analysis:
        explanations.append(f"Requested analysis: {analysis[0].replace('-', ' ').title()}.")

    # --- agent selection ---
    agent = select_agent(low, dtype, analysis, phen)
    explanations.append(f"Recommended agent: {agent['name']}.")

    # --- defaults ---
    dtype_key = dtype[0] if dtype else None
    if not dtype_key and phen:
        dtype_key = PHENOMENON_DEFAULTS[phen[0]][0]
    analysis_key = analysis[0] if analysis else None
    if not analysis_key and phen:
        analysis_key = PHENOMENON_DEFAULTS[phen[0]][1]

    confidence = 0.35
    if loc_name:
        confidence += 0.15
    if start:
        confidence += 0.15
    if dtype_key:
        confidence += 0.15
    if analysis_key:
        confidence += 0.15
    if phen:
        confidence += 0.10
    confidence = round(min(0.97, confidence), 2)

    return {
        "query_text": text,
        "raw_text": text,
        "location": loc_name,
        "location_key": location_meta["name"].lower() if location_meta else None,
        "bbox": bbox,
        "date_start": start,
        "date_end": end,
        "phenomenon": phen[0] if phen else None,
        "data_type": dtype_key,
        "requested_analysis": analysis_key,
        "agent": agent["id"],
        "agent_confidence": round(agent["confidence"], 2),
        "analysis_type": analysis_key or agent["default_analysis"],
        "confidence": confidence,
        "explanation": explanations,
    }


def select_agent(low: str, dtype, analysis, phen) -> dict:
    """Pick the agent, weighted by explicit + implied signals."""
    scores = {
        "sar": {"score": 0.0, "name": "SAR Agent", "default_analysis": "flood-mapping"},
        "optical": {"score": 0.0, "name": "Optical Agent", "default_analysis": "change-detection"},
        "temporal": {"score": 0.0, "name": "Temporal Agent", "default_analysis": "time-series"},
        "fusion": {"score": 0.0, "name": "Fusion Agent", "default_analysis": "fusion"},
    }

    for key, words in AGENT_RULES.items():
        for w in words:
            if w in low:
                scores[key]["score"] += 1.0

    if dtype:
        dt_agent = {"SAR": "sar", "Optical": "optical",
                    "Time-Series": "temporal", "Tabular": "temporal"}.get(dtype[0])
        if dt_agent:
            scores[dt_agent]["score"] += 2.0

    if analysis:
        an_agent = {
            "flood-mapping": "sar",
            "change-detection": "fusion",
            "classification": "optical",
            "object-detection": "optical",
            "time-series": "temporal",
            "image-search": "optical",
            "fusion": "fusion",
            "ndvi": "optical",
            "ndwi": "optical",
            "ndbi": "optical",
            "sar-backscatter": "sar",
        }.get(analysis[0])
        if an_agent:
            scores[an_agent]["score"] += 2.5

    if phen:
        implied = PHENOMENON_DEFAULTS.get(phen[0], (None, None, "optical"))[2]
        if implied:
            scores[implied]["score"] += 1.5

    best = max(scores.items(), key=lambda kv: kv[1]["score"])
    agent_id, info = best[0], best[1]
    total = sum(v["score"] for v in scores.values()) or 1.0
    return {
        "id": agent_id,
        "name": info["name"],
        "default_analysis": info["default_analysis"],
        "confidence": info["score"] / max(total, 1.0),
    }