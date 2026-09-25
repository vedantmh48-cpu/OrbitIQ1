"""Demo dataset catalog for instant out-of-the-box usability.

Every dataset here is clearly flagged ``simulated`` / ``source: DEMO``. They are
structurally realistic (real bboxes, real temporal ranges, real sensor labels)
so the full pipeline, agents, mapping and reports work end-to-end without any
external API key. When real Sentinel/Landsat providers are configured, those
are preferred and demo data is never presented as real.
"""
from __future__ import annotations

import math
from datetime import date, timedelta

from .storage import datetime_now


def _bb(min_lng, min_lat, max_lng, max_lat) -> dict:
    return {"min_lng": min_lng, "min_lat": min_lat, "max_lng": max_lng, "max_lat": max_lat}


def _weekly(start: str, weeks: int) -> list[str]:
    d = date.fromisoformat(start)
    out = []
    for _ in range(weeks):
        out.append(d.isoformat())
        d += timedelta(days=7)
    return out


def _spike_series(start: str, weeks: int, peak: int, base: float, amplitude: float) -> list[dict]:
    """A synthesised time series peaking at index ``peak`` (flood / NDVI)."""
    dates = _weekly(start, weeks)
    out = []
    for i, d in enumerate(dates):
        v = base + amplitude * math.exp(-(((i - peak) / 2.5) ** 2))
        v += amplitude * 0.08 * math.sin(i * 1.7)
        out.append({"date": d, "value": round(max(0.0, v), 4)})
    return out


def _linear_series(start: str, weeks: int, v0: float, v1: float) -> list[dict]:
    dates = _weekly(start, weeks)
    out = []
    n = max(len(dates) - 1, 1)
    for i, d in enumerate(dates):
        t = i / n
        out.append({"date": d, "value": round(v0 + (v1 - v0) * t, 4)})
    return out


def _monthly_series(start: str, months: int, v0: float, v1: float, season: float) -> list[dict]:
    out = []
    y, m = int(start[:4]), int(start[5:7])
    for i in range(months):
        v = v0 + (v1 - v0) * (i / max(months - 1, 1)) + season * math.sin(i / 12.0 * 2 * 3.14159)
        out.append({"date": f"{y}-{m:02d}-01", "value": round(max(0.0, v), 4)})
        m += 1
        if m == 13:
            m, y = 1, y + 1
    return out
DEMO_DATASETS = [
    {
        "id": "ds_demo_sar_kerala_flood",
        "name": "Kerala Monsoon Flood Footprints (SAR)",
        "provider_id": "demo_sar",
        "provider_label": "Demo SAR · simulated Sentinel-1 C-band",
        "data_type": "SAR",
        "phenomenons": ["flood", "cyclone"],
        "location": {"name": "Kerala", "country": "India", "bbox": _bb(74.8, 8.0, 77.6, 12.8)},
        "bbox": _bb(74.8, 8.0, 77.6, 12.8),
        "source": "DEMO",
        "simulated": True,
        "satellite": "Sentinel-1 C-SAR (simulated)",
        "resolution": "10 m",
        "temporal": {"start": "2024-06-15", "end": "2024-09-30", "count": 16},
        "description": "Simulated SAR flood-water detection masks over Kerala "
                       "during the 2024 monsoon southwest spells.",
        "grid": {"res_deg": 0.02, "seed": 731},
        "series": _spike_series("2024-06-15", 16, peak=9, base=0.08, amplitude=0.55),
        "tags": ["flood", "monsoon", "kerala", "2024"],
        "license": "Demo simulated data — NOT real satellite imagery",
        "acquisition_time": "03:10 UTC",
        "created_at": datetime_now(),
    },
    {
        "id": "ds_demo_sar_amazon_deforest",
        "name": "Amazon Forest Cover Change (SAR)",
        "provider_id": "demo_sar",
        "provider_label": "Demo SAR · simulated Sentinel-1",
        "data_type": "SAR",
        "phenomenons": ["deforestation"],
        "location": {"name": "Amazon basin", "country": "Brazil",
                     "bbox": _bb(-66.5, -9.5, -59.0, -3.0)},
        "bbox": _bb(-66.5, -9.5, -59.0, -3.0),
        "source": "DEMO",
        "simulated": True,
        "satellite": "Sentinel-1 C-SAR (simulated)",
        "resolution": "20 m",
        "temporal": {"start": "2021-01-01", "end": "2024-12-01", "count": 48},
        "description": "Simulated SAR-based forest/non-forest classification "
                       "and change masks over the southern Amazon arc.",
        "grid": {"res_deg": 0.05, "seed": 907},
        "series": _linear_series("2021-01-01", 48, 0.62, 0.46),
        "tags": ["deforestation", "amazon", "forest"],
        "license": "Demo simulated data — NOT real satellite imagery",
        "acquisition_time": "22:40 UTC",
        "created_at": datetime_now(),
    },
    {
        "id": "ds_demo_optical_california_fire",
        "name": "California Wildfire Burn Scar (Optical)",
        "provider_id": "demo_optical",
        "provider_label": "Demo Optical · simulated Sentinel-2 MSI",
        "data_type": "Optical",
        "phenomenons": ["wildfire"],
        "location": {"name": "California", "country": "USA",
                     "bbox": _bb(-122.8, 37.0, -121.0, 39.5)},
        "bbox": _bb(-122.8, 37.0, -121.0, 39.5),
        "source": "DEMO",
        "simulated": True,
        "satellite": "Sentinel-2 MSI (simulated)",
        "resolution": "10 m",
        "temporal": {"start": "2023-07-01", "end": "2023-09-15", "count": 12},
        "description": "Simulated burn-scar index (dNBR-like) rasters over "
                       "northern California wildfires in August 2023.",
        "grid": {"res_deg": 0.03, "seed": 214},
        "series": _spike_series("2023-07-01", 12, peak=6, base=0.05, amplitude=0.6),
        "tags": ["wildfire", "burn scar", "california", "2023"],
        "license": "Demo simulated data — NOT real satellite imagery",
        "acquisition_time": "18:20 UTC",
        "created_at": datetime_now(),
    },
    {
        "id": "ds_demo_optical_punjab_crop",
        "name": "Punjab Crop Health & Classification (Optical)",
        "provider_id": "demo_optical",
        "provider_label": "Demo Optical · simulated Sentinel-2 NDVI",
        "data_type": "Optical",
        "phenomenons": ["crop"],
        "location": {"name": "Punjab", "country": "India",
                     "bbox": _bb(74.2, 30.0, 76.5, 32.3)},
        "bbox": _bb(74.2, 30.0, 76.5, 32.3),
        "source": "DEMO",
        "simulated": True,
        "satellite": "Sentinel-2 MSI (simulated)",
        "resolution": "10 m",
        "temporal": {"start": "2023-03-01", "end": "2023-11-15", "count": 20},
        "description": "Simulated NDVI time series and crop-type classification "
                       "for the Punjab wheat/paddy belt.",
        "grid": {"res_deg": 0.02, "seed": 512},
        "series": _spike_series("2023-03-01", 20, peak=6, base=0.25, amplitude=0.5),
        "tags": ["crop", "ndvi", "punjab", "agriculture"],
        "license": "Demo simulated data — NOT real satellite imagery",
        "acquisition_time": "05:45 UTC",
        "created_at": datetime_now(),
    },
    {
        "id": "ds_demo_dem_uttarakhand",
        "name": "Uttarakhand Terrain Elevation (DEM)",
        "provider_id": "demo_dem",
        "provider_label": "Demo DEM · simulated SRTM 30m",
        "data_type": "DEM",
        "phenomenons": ["landslide", "snow"],
        "location": {"name": "Uttarakhand", "country": "India",
                     "bbox": _bb(78.0, 29.5, 80.8, 31.2)},
        "bbox": _bb(78.0, 29.5, 80.8, 31.2),
        "source": "DEMO",
        "simulated": True,
        "satellite": "SRTM (simulated)",
        "resolution": "30 m",
        "temporal": {"start": "2000-02-11", "end": "2000-02-22", "count": 1},
        "description": "Simulated digital elevation model over the Garhwal "
                       "Himalaya with derived slope grids.",
        "grid": {"res_deg": 0.008, "seed": 334},
        "z_range_m": [90, 4800],
        "series": [],
        "tags": ["dem", "elevation", "himalaya", "terrain"],
        "license": "Demo simulated data — NOT real elevation survey",
        "created_at": datetime_now(),
    },
    {
        "id": "ds_demo_optical_bengaluru_urban",
        "name": "Bengaluru Urban Expansion (Optical)",
        "provider_id": "demo_optical",
        "provider_label": "Demo Optical · simulated Landsat",
        "data_type": "Optical",
        "phenomenons": ["urban_growth"],
        "location": {"name": "Bengaluru", "country": "India",
                     "bbox": _bb(77.3, 12.7, 77.9, 13.3)},
        "bbox": _bb(77.3, 12.7, 77.9, 13.3),
        "source": "DEMO",
        "simulated": True,
        "satellite": "Landsat-8/9 OLI (simulated)",
        "resolution": "30 m",
        "temporal": {"start": "2015-01-01", "end": "2024-12-31", "count": 40},
        "description": "Simulated built-up area fraction grids showing urban "
                       "sprawl around Bengaluru from 2015 to 2024.",
        "grid": {"res_deg": 0.01, "seed": 808},
        "series": _linear_series("2015-01-01", 40, 0.22, 0.48),
        "tags": ["urban", "land use", "bengaluru", "sprawl"],
        "license": "Demo simulated data — NOT real satellite imagery",
        "created_at": datetime_now(),
    },
    {
        "id": "ds_demo_time_lst_gujarat",
        "name": "Gujarat Land Surface Temperature (Time-Series)",
        "provider_id": "demo_temporal",
        "provider_label": "Demo Tabular · simulated MODIS LST",
        "data_type": "Time-Series",
        "phenomenons": ["drought"],
        "location": {"name": "Gujarat", "country": "India",
                     "bbox": _bb(68.1, 20.0, 74.5, 24.7)},
        "bbox": _bb(68.1, 20.0, 74.5, 24.7),
        "source": "DEMO",
        "simulated": True,
        "satellite": "MODIS LST (simulated)",
        "resolution": "1 km",
        "temporal": {"start": "2020-01-01", "end": "2024-12-01", "count": 60},
        "description": "Simulated monthly land surface temperature index "
                       "(deg C anomaly) for drought monitoring in Gujarat.",
        "grid": {"res_deg": 0.1, "seed": 221},
        "series": _monthly_series("2020-01-01", 60, 0.5, 0.7, 0.18),
        "tags": ["temperature", "drought", "gujarat", "climate"],
        "license": "Demo simulated data — NOT real climate records",
        "created_at": datetime_now(),
    },
    {
        "id": "ds_demo_vector_districts_india",
        "name": "India District Boundaries (Vector)",
        "provider_id": "demo_vector",
        "provider_label": "Demo Vector · administrative units",
        "data_type": "Vector",
        "phenomenons": [],
        "location": {"name": "India", "country": "India",
                     "bbox": _bb(67.5, 6.5, 97.5, 36.0)},
        "bbox": _bb(67.5, 6.5, 97.5, 36.0),
        "source": "DEMO",
        "simulated": True,
        "satellite": "Admin boundaries (simulated)",
        "resolution": "1:250k",
        "temporal": {"start": "2024-01-01", "end": "2024-12-31", "count": 1},
        "description": "Simplified simulated district polygons useful for "
                       "zonal statistics and map context.",
        "grid": {"res_deg": 0.5, "seed": 151},
        "series": [],
        "tags": ["vector", "boundaries", "administration"],
        "license": "Demo simulated data — NOT official boundaries",
        "created_at": datetime_now(),
    },
    {
        "id": "ds_demo_tabular_rainfall_india",
        "name": "District Rainfall Records 2019-2024 (Tabular)",
        "provider_id": "demo_tabular",
        "provider_label": "Demo Tabular · rain-gauge statistics",
        "data_type": "Tabular",
        "phenomenons": ["flood", "drought"],
        "location": {"name": "India", "country": "India",
                     "bbox": _bb(67.5, 6.5, 97.5, 36.0)},
        "bbox": _bb(67.5, 6.5, 97.5, 36.0),
        "source": "DEMO",
        "simulated": True,
        "satellite": "Rain-gauge network (simulated)",
        "resolution": "district",
        "temporal": {"start": "2019-01-01", "end": "2024-12-01", "count": 72},
        "description": "Simulated monthly district rainfall (mm) used to "
                       "contextualise flood triggers.",
        "grid": {"res_deg": 0.5, "seed": 93},
        "series": _monthly_series("2019-01-01", 72, 90.0, 95.0, 120.0),
        "tags": ["rainfall", "tabular", "monsoon"],
        "license": "Demo simulated data — NOT official IMD records",
        "created_at": datetime_now(),
    },
    {
        "id": "ds_demo_fusion_kerala_multisource",
        "name": "Kerala Multi-Source Fusion Stack (SAR + Optical + DEM)",
        "provider_id": "demo_fusion",
        "provider_label": "Demo Fusion · simulated multi-sensor",
        "data_type": "Fusion",
        "phenomenons": ["flood", "cyclone", "landslide"],
        "location": {"name": "Kerala", "country": "India",
                     "bbox": _bb(74.8, 8.0, 77.6, 12.8)},
        "bbox": _bb(74.8, 8.0, 77.6, 12.8),
        "source": "DEMO",
        "simulated": True,
        "satellite": "Sentinel-1/Sentinel-2/SRTM (simulated)",
        "resolution": "10 m",
        "temporal": {"start": "2024-06-01", "end": "2024-09-30", "count": 18},
        "description": "Co-registered simulated SAR water + optical NDWI + DEM "
                       "drainage layers for fusion experiments over Kerala.",
        "grid": {"res_deg": 0.02, "seed": 538},
        "layers": ["sar_water", "optical_ndwi", "dem_lowland"],
        "series": _spike_series("2024-06-01", 18, peak=10, base=0.07, amplitude=0.6),
        "tags": ["fusion", "flood", "kerala", "multi-sensor"],
        "license": "Demo simulated data — NOT real satellite imagery",
        "created_at": datetime_now(),
    },
    {
        "id": "ds_demo_sar_myanmar_cyclone",
        "name": "Myanmar Cyclone Mocha Flood Extent (SAR)",
        "provider_id": "demo_sar",
        "provider_label": "Demo SAR · simulated Sentinel-1",
        "data_type": "SAR",
        "phenomenons": ["cyclone"],
        "location": {"name": "Myanmar", "country": "Myanmar",
                     "bbox": _bb(92.5, 15.0, 95.5, 18.0)},
        "bbox": _bb(92.5, 15.0, 95.5, 18.0),
        "source": "DEMO",
        "simulated": True,
        "satellite": "Sentinel-1 C-SAR (simulated)",
        "resolution": "10 m",
        "temporal": {"start": "2023-05-10", "end": "2023-06-15", "count": 6},
        "description": "Simulated flood-water mask in Rakhine (Myanmar) after "
                       "Cyclone Mocha 2023.",
        "grid": {"res_deg": 0.02, "seed": 411},
        "series": _spike_series("2023-05-10", 6, peak=3, base=0.06, amplitude=0.5),
        "tags": ["cyclone", "flood", "myanmar", "mocha"],
        "license": "Demo simulated data — NOT real satellite imagery",
        "created_at": datetime_now(),
    },
]
def build_demo_datasets() -> list[dict]:
    """Return the demo dataset documents."""
    return [dict(ds) for ds in DEMO_DATASETS]


def seed_demo_data(db) -> int:
    """Idempotently upsert demo datasets and a default admin user."""
    count = 0
    for ds in DEMO_DATASETS:
        db.upsert("datasets", {"id": ds["id"]}, ds)
        count += 1
    admin = db.find_one("users", {"email": "admin@satquery.ai"})
    if not admin:
        from .security import hash_password

        db.insert(
            "users",
            {
                "name": "SatQuery Admin",
                "email": "admin@satquery.ai",
                "password": hash_password("Admin@123"),
                "role": "admin",
                "active": True,
                "email_verified": True,
                "settings": {},
                "created_at": datetime_now(),
            },
        )
    demo = db.find_one("users", {"email": "demo@satquery.ai"})
    if not demo:
        db.insert(
            "users",
            {
                "name": "Demo Analyst",
                "email": "demo@satquery.ai",
                "password": hash_password("Demo@123"),
                "role": "analyst",
                "active": True,
                "email_verified": True,
                "settings": {
                    "theme": "dark",
                    "default_satellite_source": "demo",
                    "default_data_type": "any",
                    "map_preferences": {"base_layer": "dark", "show_labels": True},
                    "notifications": {"email_summary": True, "job_updates": True, "weekly_digest": False},
                },
                "created_at": datetime_now(),
            },
        )
    return count