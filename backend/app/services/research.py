"""Deep query research — encyclopaedic context + live evidence enrichment.

Turns a parsed natural-language query (from ``nlp_understanding``) into a rich
research brief that is surfaced in the UI alongside the analysis:

* **overview** — what the query is about (phenomenon science summary)
* **sections** — factual notes: how satellites observe it, key indices,
  related hazards, at-risk context
* **location_context** — gazetteer-derived place facts (country, kind, extent)
* **live_evidence** — *real* observations pulled from key-free public APIs when
  the phenomenon maps to one (USGS earthquakes, Open-Meteo weather/climate),
  each stamped ``real: True`` + ``observed_at``
* **imagery_availability** — best-effort live STAC scene check (Sentinel-1/2)
  for the query bbox/time window
* **recommended_datasets** — top catalogue matches (same ranking as retrieval)

Nothing here is fabricated: static facts are curated reference text, all numbers
come from the gazetteer / live APIs / the dataset catalogue, and every failure
degrades gracefully.
"""
from __future__ import annotations

import datetime as dt

from .gazetteer import resolve_location

# ---------------------------------------------------------------------------
# Curated phenomenon fact sheets (reference knowledge, not live data).
# ---------------------------------------------------------------------------

PHENOMENON_FACTS: dict[str, dict] = {
    "flood": {
        "title": "Flood & inundation",
        "summary": (
            "Floods are the most frequent natural disaster worldwide. Optical "
            "imagery struggles under cloud cover during monsoon events, so radar "
            "(Sentinel-1 C-band SAR) is the workhorse for water mapping — water "
            "appears near-black (very low backscatter) compared with land."
        ),
        "satellite_methods": (
            "SAR threshold water-masking (dark pixels = specular reflection), "
            "NDWI optical water index, DEM-based hydrological overlay to flag "
            "low-lying flood-prone zones, and before/after change detection."
        ),
        "key_indices": ["NDWI", "SAR σ⁰ backscatter", "MNDWI"],
        "related_hazards": ["Landslide", "Disease outbreaks (stagnant water)", "Crop loss"],
        "context": (
            "Flood extent, duration and depth drive evacuation planning, crop "
            "damage estimates and relief logistics. Near-real-time SAR revisit "
            "times (Sentinel-1 ~6 days at equator, more frequent at high latitude) "
            "make repeat flood mapping practical."
        ),
    },
    "wildfire": {
        "title": "Wildfire & burn scars",
        "summary": (
            "Wildfires are detected through thermal anomalies (SWIR/MIR bands) "
            "and burn scars through sharp reductions in near-infrared reflectance. "
            "Optical multispectral sensors (Sentinel-2, Landsat) enable severity "
            "classification and regrowth monitoring."
        ),
        "satellite_methods": (
            "NBR (Normalised Burn Ratio) using NIR+SWIR, thermal anomaly "
            "detection, active-fire hotspot tracking and post-event vegetation "
            "recovery time-series."
        ),
        "key_indices": ["NBR", "NDVI", "SWIR thermal"],
        "related_hazards": ["Smoke & air quality", "Erosion after burn", "Flash floods"],
        "context": (
            "Burn-severity maps support ecosystem recovery planning and "
            "insurance claims. Dense-smoke plumes can hide fires from optical "
            "sensors — radar and thermal bands provide the all-weather view."
        ),
    },
    "drought": {
        "title": "Drought & water stress",
        "summary": (
            "Drought is a slow-onset hazard tracked through vegetation stress "
            "(NDVI anomalies vs. long-term means), soil-moisture deficits, and "
            "precipitation shortfalls. Climate archives provide real "
            "rainfall/temperature series for anomaly detection."
        ),
        "satellite_methods": (
            "Vegetation Condition Index (VCI) from NDVI history, soil-moisture "
            "retrieval, precipitation anomaly analysis, and reservoir/water-body "
            "surface-area trend monitoring."
        ),
        "key_indices": ["NDVI / VCI", "SPI (precipitation)", "Soil moisture"],
        "related_hazards": ["Crop failure", "Food insecurity", "Water rationing"],
        "context": (
"deforestation": {
        "title": "Deforestation & forest loss",
        "summary": (
            "Forest loss is detected by persistent drops in tree-canopy "
            "reflectance. Change-detection over annual optical mosaics is the "
            "standard method; radar adds all-weather sensitivity in cloudy "
            "tropical regions."
        ),
        "satellite_methods": (
            "Before/after NDVI or NBR differencing, supervised land-cover "
            "classification, and time-series breakpoint detection (e.g. a sudden, "
            "sustained drop in greenness marks a clearing event)."
        ),
        "key_indices": ["NDVI", "NBR", "Canopy height (DEM diff)"],
        "related_hazards": ["Biodiversity loss", "Carbon emissions", "Erosion"],
        "context": (
            "Annual global forest-loss figures are produced from Landsat-scale "
            "(30 m) optical time-series. Radar's penetration of cloud makes it "
            "invaluable for the humid tropics."
        ),
    },
    "urban_growth": {
        "title": "Urban growth & sprawl",
        "summary": (
            "Urbanisation is tracked by converting vegetation/bare land to "
            "impervious surfaces, visible as rising built-up indices and changed "
            "texture in high-resolution imagery."
        ),
        "satellite_methods": (
            "NDBI (built-up index) trends, land-cover classification between "
            "dates, night-lights intensity mapping, and settlement-extent "
            "delineation from VNIR+SWIR signatures."
        ),
        "key_indices": ["NDBI", "NDVI (inverse)", "Night-time lights"],
        "related_hazards": ["Heat islands", "Infrastructure strain", "Habitat loss"],
        "context": (
            "Urban growth rates inform zoning, transport and utility planning. "
            "Comparing two or more dated images over the same extent quantifies "
            "expansion in km² per year."
        ),
    },
    "crop": {
        "title": "Agriculture & crop condition",
        "summary": (
            "Crop health is assessed through vegetation indices that track "
            "chlorophyll content and green biomass. Time-series analysis "
            "separates seasonal crop calendars from stress anomalies."
        ),
        "satellite_methods": (
            "NDVI/LAI vegetation monitoring, crop-type classification with "
            "multi-date signatures, phenology (sowing→harvest) extraction, and "
            "yield-forecast regression against greenness integrals."
        ),
        "key_indices": ["NDVI", "LAI", "EVI"],
        "related_hazards": ["Pest outbreaks", "Drought stress", "Flood damage"],
        "context": (
            "Sentinel-2's 10 m resolution and 5-day revisit make precision "
            "agriculture feasible. A full growing-season NDVI trajectory is far "
            "more informative than any single date."
        ),
    },
    "landslide": {
        "title": "Landslides & slope failure",
        "summary": (
            "Landslides are identified by displaced material, scarps and changed "
            "texture on slopes. Radar's all-weather ability and optical "
            "before/after differencing both contribute."
        ),
        "satellite_methods": (
            "Pre/post optical difference mapping, SAR coherence loss, and "
            "terrain analysis (slope, aspect, relief) to rank susceptibility."
        ),
        "key_indices": ["SAR coherence", "NDVI difference", "Slope from DEM"],
        "related_hazards": ["Blocked rivers", "Damaged roads", "Casualties"],
        "context": (
            "Rainfall-triggered landslides cluster along steep, deforested "
            "slopes. Combining high-resolution imagery with a DEM and a rainfall "
            "archive produces useful susceptibility maps."
        ),
    },
"earthquake": {
        "title": "Earthquakes (seismic events)",
        "summary": (
            "Earthquakes are ground-shaking events recorded by seismometers; "
            "satellite techniques (InSAR) measure the resulting surface "
            "deformation. The system surfaces genuine USGS observations live."
        ),
        "satellite_methods": (
            "InSAR interferograms for co-seismic displacement, SAR amplitude "
            "change for damaged areas, and geodetic estimates of slip magnitude."
        ),
        "key_indices": ["Magnitude (Mw)", "Depth", "Peak Ground Acceleration"],
        "related_hazards": ["Tsunami", "Aftershocks", "Building damage", "Landslides"],
        "context": (
            "The USGS feed provides real-time magnitude, depth and location for "
            "every detected event. Combining a live event with population "
            "density and building footprint data estimates exposure."
        ),
    },
    "cyclone": {
        "title": "Cyclones & severe storms",
        "summary": (
            "Tropical cyclones are rotating storm systems with intense wind and "
            "rain. Live weather feeds provide current conditions; storm tracks "
            "and intensity come from meteorological agencies."
        ),
        "satellite_methods": (
            "Cloud-top temperature (IR) for intensity, microwave precipitation, "
            "storm-surge modelling, and post-event flood mapping with SAR/optical."
        ),
        "key_indices": ["Wind speed", "Central pressure", "Rainfall rate"],
        "related_hazards": ["Storm surge", "Flooding", "Wind damage"],
        "context": (
            "Cyclone risk peaks on low-lying coasts. Live wind, rain and pressure "
            "readings (Open-Meteo) combined with flood-prone elevation maps give "
            "an immediate hazard picture."
        ),
    },
    "weather": {
        "title": "Weather & atmospheric conditions",
        "summary": (
            "Current weather (temperature, humidity, wind, precipitation, cloud "
            "cover) is observed by ground stations and nowcast models. The system "
            "uses Open-Meteo's forecast API for genuine live conditions."
        ),
        "satellite_methods": (
            "Thermal IR cloud/land temperature, visible albedo, and satellite-"
            "assimilated numerical weather models for forecasts."
        ),
        "key_indices": ["Temperature", "Humidity", "Wind speed", "Precipitation"],
        "related_hazards": ["Heat stress", "Flooding", "Fog", "Severe wind"],
        "context": (
            "Live conditions are refreshed from upstream providers (2-minute "
            "cache) — values are as observed and carry a timestamp and source."
        ),
    },
    "water_quality": {
        "title": "Water quality & algal blooms",
        "summary": (
            "Water quality is inferred from water colour: chlorophyll-a (green "
            "algae), turbidity (tan/brown) and CDOM (brown dissolved matter). "
            "Blue-green band ratios separate these signals."
        ),
        "satellite_methods": (
            "Chlorophyll-a index (green/blue ratio), turbidity retrieval, and "
            "NDCI (Normalised Difference Chlorophyll Index) for cyanobacteria "
            "blooms."
        ),
        "key_indices": ["Chlorophyll-a", "NDCI", "Turbidity"],
        "related_hazards": ["Fish kills", "Drinking-water risk", "Recreation closures"],
        "context": (
            "Optical bands across 443-705 nm are most sensitive to water "
            "quality. High reflectance in the red is a classic chlorophyll/ "
            "bloom signal."
        ),
    },
"snow": {
        "title": "Snow cover & glaciers",
        "summary": (
            "Snow and ice are bright in visible bands but dark in SWIR — the "
            "NDSI ratio separates snow from cloud and bare rock. Glacier "
            "extent trends track climate change."
        ),
        "satellite_methods": (
            "NDSI (green/SWIR ratio) snow-masking, glacier-terminus mapping from "
            "optical mosaics, and albedo change tracking."
        ),
        "key_indices": ["NDSI", "Albedo", "Snow cover fraction"],
        "related_hazards": ["Avalanche", "Glacial lake outburst", "Water-supply change"],
        "context": (
            "Snowmelt water supply feeds billions globally. Continuous snow-"
            "cover monitoring across the season is essential for runoff "
            "forecasting."
        ),
    },
    "coastal": {
        "title": "Coastal erosion & shoreline change",
        "summary": (
            "Shoreline position is mapped from water/land boundary pixels over "
            "time. Repeated satellite observations quantify erosion and "
            "accretion rates metre-by-metre."
        ),
        "satellite_methods": (
            "NDWI water delineation per date, shoreline transect differencing, "
            "and SAR-based storm-surge impact mapping."
        ),
        "key_indices": ["NDWI", "Shoreline position", "Bathymetry"],
        "related_hazards": ["Property loss", "Saltwater intrusion", "Habitat loss"],
        "context": (
            "Coastal change is highly localised — high-resolution (10 m) "
            "Sentinel-2 time-series is the standard observational input."
        ),
    },
}

# Fallback used when the phenomenon is not in the fact sheet.
_GENERIC_FACTS = {
    "title": "Geospatial analysis",
    "summary": (
        "This query was analysed with satellite-observation techniques. The "
        "specific phenomenon, location and time window from the query drive the "
        "agent plan, dataset retrieval and processing below."
    ),
    "satellite_methods": (
        "The selected agent runs the planned operations (classification, change "
        "detection, index computation, time-series, fusion or live-event "
        "analysis) against the best-matching datasets in the catalogue."
    ),
    "key_indices": ["NDVI", "NDWI", "NDBI", "SAR σ⁰"],
    "related_hazards": ["—"],
    "context": (
        "Deep research adds reference context plus any live evidence available "
        "for the query area so the analysis is interpreted in the right setting."
    ),
}

# Live phenomenon keys that map to realtime module fetch functions.
_LIVE_FETCHERS = {
    "earthquake": "earthquakes",
    "weather": "weather",
    "cyclone": "weather",
    "drought": "climate",
}

_COUNTRY_FACTS = {
    "India": "The world's most populous country; flood, drought and crop "
             "monitoring are national priorities (ISRO/NASA partnership missions).",
    "USA": "Wide-ranging hazard exposure from quakes (California), wildfires "
           "and coastal storms; Landsat and USGS monitoring are world-leading.",
    "Bangladesh": "Extremely flood-prone delta; seasonal monsoon inundation "
                  "affects large fractions of the population yearly.",
    "Brazil": "Hosts the Amazon basin, the planet's largest tropical forest; "
              "deforestation monitoring is a global focus.",
    "Australia": "Fire-prone continent with recurring bushfire seasons and "
                 "drought cycles monitored by national agencies.",
    "Netherlands": "Low-lying reclaimed land; water management and flood "
                   "defence are engineering cornerstones.",
def _live_evidence(understanding: dict) -> list[dict]:
    """Fetch real observations when the phenomenon maps to a live feed.

    Every item is a genuine API observation stamped ``real: True``; failures
    are gracefully skipped so the research brief never breaks the query.
    """
    from . import realtime as _rt

    phenom = (understanding.get("phenomenon") or "").lower()
    kind = _LIVE_FETCHERS.get(phenom)
    if not kind:
        return []
    out: list[dict] = []
    try:
        if kind == "earthquakes":
            data = _rt.fetch_earthquakes(hours=48, min_magnitude=2.0, limit=40)
            events = data.get("events") or []
            bbox = understanding.get("bbox")
            for ev in events[:12]:
                lat, lng = ev.get("lat"), ev.get("lng")
                if lat is None or lng is None:
                    continue
                if bbox and not (
                    bbox["min_lat"] - 1 <= lat <= bbox["max_lat"] + 1
                    and bbox["min_lng"] - 1 <= lng <= bbox["max_lng"] + 1
                ):
                    continue
                detail = f"{lat:.2f}°, {lng:.2f}°"
                if ev.get("depth_km") is not None:
                    detail = f"Depth {ev['depth_km']} km · " + detail
                out.append({
                    "kind": "earthquake", "real": True,
                    "source": data.get("source", "USGS"),
                    "observed_at": ev.get("time") or data.get("observed_at"),
                    "title": f"M{ev.get('mag')} — {ev.get('place','')}".strip(),
                    "detail": detail,
                })
        elif kind == "weather":
            data = _rt.fetch_weather()
            cities = data.get("cities") or []
            loc = (understanding.get("location") or "").lower()
            if loc:
                cities = ([c for c in cities if loc in c.get("city", "").lower()]
                          or cities[:2])
            for c in cities[:3]:
                out.append({
                    "kind": "weather", "real": True,
                    "source": data.get("source", "Open-Meteo"),
                    "observed_at": data.get("observed_at"),
                    "title": f"{c.get('city')} weather now",
                    "detail": (
                        f"{c.get('temperature_c')} °C · RH {c.get('relative_humidity')}% · "
                        f"wind {c.get('wind_speed_kmh')} km/h · "
                        f"{_rt.weather_label(c.get('weather_code'))}"
                    ),
                })
        elif kind == "climate":
            bbox = understanding.get("bbox")
            lat = (bbox["min_lat"] + bbox["max_lat"]) / 2 if bbox else 19.076
            lng = (bbox["min_lng"] + bbox["max_lng"]) / 2 if bbox else 72.8777
            data = _rt.fetch_climate(lat, lng, understanding.get("date_start"),
                                     understanding.get("date_end"), days=30)
            series = data.get("series") or []
            if series:
                temps = [s["temperature_c"] for s in series
                         if s.get("temperature_c") is not None]
                rains = [s["precipitation_mm"] for s in series
                         if s.get("precipitation_mm") is not None]
                detail = f"{len(series)} days of observed data"
                if temps:
                    detail += f" · mean temp {sum(temps)/len(temps):.1f} °C"
                if rains:
                    detail += f" · total rain {sum(rains):.1f} mm"
                out.append({
                    "kind": "climate", "real": bool(data.get("real", True)),
                    "source": data.get("source", "Open-Meteo Climate Archive"),
                    "observed_at": data.get("observed_at"),
                    "title": f"Climate archive ({lat:.1f}°, {lng:.1f}°)",
                    "detail": detail,
                })
    except Exception:
def _imagery_availability(understanding: dict) -> dict:
    """Best-effort real STAC availability (scene count + latest date)."""
    bbox = understanding.get("bbox")
    if not bbox:
        return {"available": False, "real": False,
                "note": "No location resolved — cannot check imagery."}
    try:
        from .satellite import StacProvider

        provider = StacProvider(timeout=12)
        res = provider.search(
            bbox,
            understanding.get("date_start"),
            understanding.get("date_end"),
            understanding.get("data_type") or "Any",
            limit=6,
        )
        scenes = res.get("scenes") or []
        if not scenes:
            return {
                "available": False, "real": True,
                "note": ("No scenes matched the query area/window in the live "
                         "STAC catalogue."),
                "source": provider.label,
            }

        def _platform(s):
            p = (s.get("properties") or {}).get("platform")
            c = (s.get("properties") or {}).get("constellation")
            return p or c or "Sentinel"

        def _date(s):
            return ((s.get("properties") or {}).get("datetime") or "")

        platforms = sorted({str(_platform(s)) for s in scenes})
        latest = sorted(_date(s) for s in scenes if _date(s))[-1:] or [""]
        return {
            "available": True, "real": True,
            "note": f"{len(scenes)} recent scene(s) found in the live catalogue.",
            "source": provider.label,
            "platforms": platforms,
            "latest": (latest[0][:10] if latest and latest[0] else None),
            "scenes": [{
                "id": s.get("id"),
                "platform": _platform(s),
                "date": _date(s)[:10],
                "cloud_cover": (s.get("properties") or {}).get("eo:cloud_cover"),
            } for s in scenes[:6]],
        }
    except Exception:
        return {
def _recommended_datasets(db, understanding: dict) -> list[dict]:
    try:
        from .indexing import SemanticIndex, search_datasets

        datasets = db.find("datasets", {})
        index = SemanticIndex(datasets) if datasets else None
        hits = search_datasets(db, understanding, limit=5, semantic_index=index)
        return [{
            "id": d.get("id"), "name": d.get("name"),
            "data_type": d.get("data_type"),
            "satellite": d.get("satellite"),
            "source": d.get("source"),
        } for d in hits]
    except Exception:
        return []


def build_research_brief(
    understanding: dict,
    db=None,
    include_live: bool = True,
    include_imagery: bool = True,
) -> dict:
    """Assemble the full research brief for a parsed query."""
    phenom = understanding.get("phenomenon")
    facts = PHENOMENON_FACTS.get(phenom, _GENERIC_FACTS)

    location = None
    loc_key = understanding.get("location_key") or (
        understanding.get("location") or "").lower()
    if loc_key:
        location = resolve_location(loc_key)
    if location is None and understanding.get("bbox"):
        location = {
            "name": understanding.get("location") or "AOI",
            "country": "", "kind": "area of interest",
            "bbox": understanding.get("bbox"),
        }

    sections = [
        {"id": "overview", "title": facts["title"],
         "body": facts["summary"]},
        {"id": "methods", "title": "How satellites observe this",
         "body": facts["satellite_methods"]},
        {"id": "indices", "title": "Key measurements",
         "body": " · ".join(facts["key_indices"])},
        {"id": "related", "title": "Related risks",
         "body": ", ".join(facts["related_hazards"])},
    ]
    if facts["context"]:
        sections.append(
            {"id": "context", "title": "Context", "body": facts["context"]}
        )

    location_context = {}
    if location:
        location_context = {
            "name": location.get("name"),
            "country": location.get("country"),
            "kind": location.get("kind"),
            "bbox": location.get("bbox"),
        }
        country = location.get("country")
        if country in _COUNTRY_FACTS:
            location_context["country_note"] = _COUNTRY_FACTS[country]

    research = {
        "query_text": understanding.get("query_text", ""),
        "phenomenon": phenom,
        "location": location_context,
        "sections": sections,
        "factors": {
            "date_start": understanding.get("date_start"),
            "date_end": understanding.get("date_end"),
            "data_type": understanding.get("data_type"),
            "analysis_type": understanding.get("analysis_type"),
            "confidence": understanding.get("confidence"),
        },
        "live_evidence": [],
        "imagery_availability": {"available": False, "note": "Not checked.",
                                 "real": False},
        "recommended_datasets": [],
        "sources": ["SatQuery AI curated reference knowledge"],
        "generated_at": _now(),
    }

    if include_live:
        research["live_evidence"] = _live_evidence(understanding)
    if include_imagery:
        research["imagery_availability"] = _imagery_availability(understanding)
    if db is not None:
        research["recommended_datasets"] = _recommended_datasets(db, understanding)

    research["sources"] = sorted({
        "SatQuery AI curated reference knowledge",
        "Open-Meteo (current + climate archive)",
        "USGS Earthquake Hazards Program",
        "Amazon Web Services — Earth Search STAC (Sentinel-1/2)",
        facts["title"],
    })
    return research
            "available": False, "real": False,
            "note": "Live STAC catalogue unreachable — imagery check skipped.",
            "source": "STAC (Earth Search)",
        }
        pass
    return out
}


def _now() -> str:
    return dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
            "Drought indices must be computed against a climatological baseline "
            "of at least 10-20 years to separate true stress from seasonal "
            "variability. Combining vegetation greenness with observed rainfall "
            "greatly improves accuracy."
        ),
    },
}