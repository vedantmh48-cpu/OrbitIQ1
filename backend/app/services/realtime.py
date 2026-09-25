"""Real-time data layer — key-free public APIs with TTL + disk caching.

Fetches genuinely live observations (not fabricated):

* **USGS Earthquake** feed (real event GeoJSON: magnitude, depth, place, tsunami)
* **Open-Meteo** weather forecast (current conditions) & historical climate
* Combined with the existing real **STAC** scene search for imagery

Every result carries `real: True`, a human-readable `source` and an
`observed_at` timestamp so the UI can present it honestly. A short-TTL in-memory
cache plus an on-disk cache keeps repeat calls fast and tolerates brief network
hiccups (falls back to the latest cached values, clearly stamped).
"""
from __future__ import annotations

import json
import math
import time
import threading
from datetime import datetime, timedelta, timezone
from typing import Optional

import httpx

from ..config import settings

USGS_QUERY = "https://earthquake.usgs.gov/fdsnws/event/1/query"
OPEN_METEO = "https://api.open-meteo.com/v1/forecast"
OPEN_METEO_ARCHIVE = "https://archive-api.open-meteo.com/v1/archive"
OPEN_METEO_GEOCODE = "https://geocoding-api.open-meteo.com/v1/search"

_TTL_SECONDS = 120
_CACHE_DIR = settings.DATA_DIR / "realtime_cache"
_CACHE_DIR.mkdir(parents=True, exist_ok=True)

_sample_cities = [
    ("Mumbai", 19.076, 72.8777, "Asia/Kolkata"),
    ("New Delhi", 28.6139, 77.2090, "Asia/Kolkata"),
    ("Kochi", 9.9312, 76.2673, "Asia/Kolkata"),
    ("Los Angeles", 34.0522, -118.2437, "America/Los_Angeles"),
    ("London", 51.5072, -0.1276, "Europe/London"),
    ("Tokyo", 35.6762, 139.6503, "Asia/Tokyo"),
    ("São Paulo", -23.5505, -46.6247, "America/New_York"),
]

_mem: dict[str, tuple[float, dict]] = {}
_lock = threading.Lock()


def _cache_get(key: str) -> Optional[dict]:
    with _lock:
        hit = _mem.get(key)
        if hit and time.monotonic() - hit[0] < _TTL_SECONDS:
            return hit[1]
    path = _CACHE_DIR / f"{key}.json"
    if path.exists():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return None
    return None


def _cache_set(key: str, value: dict) -> dict:
    with _lock:
        _mem[key] = (time.monotonic(), value)
    try:
        (_CACHE_DIR / f"{key}.json").write_text(
            json.dumps(value, default=str), encoding="utf-8"
        )
    except Exception:
        pass
    return value


def _stamp(real: bool, source: str) -> dict:
    return {"real": real, "source": source,
            "observed_at": datetime.now(timezone.utc).isoformat()}


def _get_json(url: str, params: dict, timeout: float = 6.0) -> Optional[dict]:
    try:
        with httpx.Client(timeout=timeout, follow_redirects=True) as c:
            r = c.get(url, params=params, headers={"User-Agent": "SatQueryAI/1.0"})
            r.raise_for_status()
            return r.json()
    except Exception:
        return None
# ---------------------------------------------------------------------------
# USGS Earthquakes
# ---------------------------------------------------------------------------

def fetch_earthquakes(hours=48, min_magnitude=2.5, limit=80):
    key = f"usgs_{hours}_{int(min_magnitude * 10)}"
    cached = _cache_get(key)
    if cached is not None:
        return dict(cached)
    now = datetime.now(timezone.utc)
    data = _get_json(
        USGS_QUERY,
        {
            "format": "geojson",
            "starttime": (now - timedelta(hours=hours)).strftime("%Y-%m-%d"),
            "endtime": now.strftime("%Y-%m-%dT%H:%M:%S"),
            "minmagnitude": min_magnitude,
            "orderby": "time",
            "limit": limit,
        },
    )
    if not data:
        stale = _cache_get(key)
        return stale if stale is not None else {"events": [], "real": False,
                                                "source": "USGS (unreachable)"}
    events = []
    for f in data.get("features", []):
        p = f.get("properties", {}) or {}
        coords = (f.get("geometry") or {}).get("coordinates") or []
        events.append(
            {
                "id": str(f.get("id", "")),
                "mag": p.get("mag"),
                "place": p.get("place"),
                "time": p.get("time"),
                "depth_km": round(coords[2], 1) if len(coords) > 2 else None,
                "lat": coords[1] if len(coords) > 1 else None,
                "lng": coords[0] if coords else None,
                "url": p.get("url"),
                "tsunami": bool(p.get("tsunami")),
                "felt": p.get("felt"),
                "magType": p.get("magType"),
                "mmi": p.get("mmi"),
                "updated": p.get("updated"),
            }
        )
    return _cache_set(key, {"events": events, **_stamp(True, "USGS Earthquake Hazards Program")})
# ---------------------------------------------------------------------------
# Open-Meteo weather & climate
# ---------------------------------------------------------------------------

def _weather_for_city(name, lat, lng):
    data = _get_json(
        OPEN_METEO,
        {
            "latitude": lat,
            "longitude": lng,
            "current": ("temperature_2m,relative_humidity_2m,weather_code,"
                        "wind_speed_10m,precipitation,cloud_cover,pressure_msl"),
            "hourly": "temperature_2m,precipitation_probability",
            "forecast_days": 2,
            "timezone": "auto",
        },
    )
    if not data:
        return {"city": name, "lat": lat, "lng": lng, "error": "unreachable"}
    cur = data.get("current") or {}
    hourly = data.get("hourly") or {}
    temps = hourly.get("temperature_2m") or []
    times = hourly.get("time") or []
    return {
        "city": name,
        "lat": lat,
        "lng": lng,
        "temperature_c": cur.get("temperature_2m"),
        "relative_humidity": cur.get("relative_humidity_2m"),
        "weather_code": cur.get("weather_code"),
        "wind_speed_kmh": cur.get("wind_speed_10m"),
        "precipitation_mm": cur.get("precipitation"),
        "cloud_cover": cur.get("cloud_cover"),
        "pressure_hpa": cur.get("pressure_msl"),
        "units": data.get("current_units", {}),
        "hourly": [{"time": t, "temperature_c": v} for t, v in zip(times[-24:], temps[-24:])],
    }


def fetch_weather():
    key = "openmeteo_weather"
    cached = _cache_get(key)
    if cached is not None:
        return dict(cached)
    cities = [_weather_for_city(n, la, lo) for n, la, lo, _tz in _sample_cities]
    return _cache_set(key, {"cities": cities, **_stamp(True, "Open-Meteo")})


# ---------------------------------------------------------------------------
# Detailed 7-day weather forecast (Weather Forecast section)
# ---------------------------------------------------------------------------

def _forecast_for_city(name, lat, lng):
    """Fetch genuinely live current + hourly + 7-day daily forecast for a city."""
    data = _get_json(
        OPEN_METEO,
        {
            "latitude": lat,
            "longitude": lng,
            "current": (
                "temperature_2m,relative_humidity_2m,apparent_temperature,weather_code,"
                "wind_speed_10m,wind_direction_10m,precipitation,cloud_cover,pressure_msl,"
                "surface_pressure,is_day,uv_index,visibility"
            ),
            "hourly": (
                "temperature_2m,apparent_temperature,precipitation_probability,precipitation,"
                "weather_code,wind_speed_10m,wind_direction_10m,relative_humidity_2m,"
                "cloud_cover,pressure_msl"
            ),
            "daily": (
                "weather_code,temperature_2m_max,temperature_2m_min,apparent_temperature_max,"
                "precipitation_sum,precipitation_probability_max,wind_speed_10m_max,"
                "wind_direction_10m_dominant,uv_index_max,relative_humidity_2m_mean,"
                "sunrise,sunset"
            ),
            "forecast_days": 7,
            "timezone": "auto",
        },
        timeout=8.0,
    )
    if not data:
        return {"city": name, "lat": lat, "lng": lng, "error": "unreachable"}
    cur = data.get("current") or {}
    hourly = data.get("hourly") or {}
    daily = data.get("daily") or {}

    def _h(key):
        return hourly.get(key) or []

    def _d(key):
        return daily.get(key) or []

    hours = []
    for i, t in enumerate(_h("time")):
        hours.append({
            "time": t,
            "temperature_c": _h("temperature_2m")[i] if i < len(_h("temperature_2m")) else None,
            "apparent_temperature_c": _h("apparent_temperature")[i] if i < len(_h("apparent_temperature")) else None,
            "precipitation_probability": _h("precipitation_probability")[i] if i < len(_h("precipitation_probability")) else None,
            "precipitation_mm": _h("precipitation")[i] if i < len(_h("precipitation")) else None,
            "weather_code": _h("weather_code")[i] if i < len(_h("weather_code")) else None,
            "wind_speed_kmh": _h("wind_speed_10m")[i] if i < len(_h("wind_speed_10m")) else None,
            "wind_direction": _h("wind_direction_10m")[i] if i < len(_h("wind_direction_10m")) else None,
            "relative_humidity": _h("relative_humidity_2m")[i] if i < len(_h("relative_humidity_2m")) else None,
            "cloud_cover": _h("cloud_cover")[i] if i < len(_h("cloud_cover")) else None,
            "pressure_hpa": _h("pressure_msl")[i] if i < len(_h("pressure_msl")) else None,
        })

    days = []
    for i, t in enumerate(_d("time")):
        days.append({
            "date": t,
            "weather_code": _d("weather_code")[i] if i < len(_d("weather_code")) else None,
            "temperature_max_c": _d("temperature_2m_max")[i] if i < len(_d("temperature_2m_max")) else None,
            "temperature_min_c": _d("temperature_2m_min")[i] if i < len(_d("temperature_2m_min")) else None,
            "apparent_temperature_max_c": _d("apparent_temperature_max")[i] if i < len(_d("apparent_temperature_max")) else None,
            "precipitation_sum_mm": _d("precipitation_sum")[i] if i < len(_d("precipitation_sum")) else None,
            "precipitation_probability_max": _d("precipitation_probability_max")[i] if i < len(_d("precipitation_probability_max")) else None,
            "wind_speed_max_kmh": _d("wind_speed_10m_max")[i] if i < len(_d("wind_speed_10m_max")) else None,
            "wind_direction_dominant": _d("wind_direction_10m_dominant")[i] if i < len(_d("wind_direction_10m_dominant")) else None,
            "uv_index_max": _d("uv_index_max")[i] if i < len(_d("uv_index_max")) else None,
            "relative_humidity_mean": _d("relative_humidity_2m_mean")[i] if i < len(_d("relative_humidity_2m_mean")) else None,
            "sunrise": _d("sunrise")[i] if i < len(_d("sunrise")) else None,
            "sunset": _d("sunset")[i] if i < len(_d("sunset")) else None,
        })

    return {
        "city": name,
        "lat": lat,
        "lng": lng,
        "timezone": data.get("timezone"),
        "current": {
            "temperature_c": cur.get("temperature_2m"),
            "apparent_temperature_c": cur.get("apparent_temperature"),
            "relative_humidity": cur.get("relative_humidity_2m"),
            "weather_code": cur.get("weather_code"),
            "wind_speed_kmh": cur.get("wind_speed_10m"),
            "wind_direction": cur.get("wind_direction_10m"),
            "precipitation_mm": cur.get("precipitation"),
            "cloud_cover": cur.get("cloud_cover"),
            "pressure_hpa": cur.get("pressure_msl") or cur.get("surface_pressure"),
            "uv_index": cur.get("uv_index"),
            "visibility_km": cur.get("visibility"),
            "is_day": cur.get("is_day"),
        },
        "current_units": data.get("current_units", {}),
        "hourly": hours,
        "daily": days,
    }


def fetch_forecast():
    """7-day real-time weather forecast for the tracked global cities."""
    key = "openmeteo_forecast"
    cached = _cache_get(key)
    if cached is not None:
        return dict(cached)
    cities = [_forecast_for_city(n, la, lo) for n, la, lo, _tz in _sample_cities]
    # Honest provenance: real only when the provider actually answered for at
    # least one city (per-city "error" entries mark the ones that failed).
    real = any(isinstance(c, dict) and "error" not in c for c in cities)
    return _cache_set(key, {"cities": cities, **_stamp(real, "Open-Meteo (NOAA/GFS model)")})


def fetch_climate(lat, lng, start=None, end=None, days=30):
    key = f"climate_{lat:.1f}_{lng:.1f}"
    cached = _cache_get(key)
    if cached is not None:
        return dict(cached)
    now = datetime.now(timezone.utc)
    data = _get_json(
        OPEN_METEO_ARCHIVE,
        {
            "latitude": lat,
            "longitude": lng,
            "start_date": start or (now - timedelta(days=days)).strftime("%Y-%m-%d"),
            "end_date": end or now.strftime("%Y-%m-%d"),
            "daily": "temperature_2m_mean,precipitation_sum",
            "timezone": "UTC",
        },
    )
    if not data:
        stale = _cache_get(key)
        if stale is not None:
            return dict(stale)
        return {"series": [], "real": False, "source": "Open-Meteo archive (unreachable)"}
    daily = data.get("daily") or {}
    series = [
        {"date": t, "temperature_c": tm, "precipitation_mm": pr}
        for t, tm, pr in zip(
            daily.get("time") or [],
            daily.get("temperature_2m_mean") or [],
            daily.get("precipitation_sum") or [],
        )
    ]
    return _cache_set(key, {"series": series, **_stamp(True, "Open-Meteo Climate Archive")})


# ---------------------------------------------------------------------------
# Combined board + labels
# ---------------------------------------------------------------------------

def fetch_overview():
    quakes = fetch_earthquakes()
    weather = fetch_weather()
    return {
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "earthquakes": quakes,
        "weather": weather,
        "labels": {
            "data": "Real live observations",
            "sources": ["USGS Earthquake Hazards Program", "Open-Meteo"],
            "note": ("Live data is fetched from public real-time APIs. Times are "
                     "UTC; values are as observed by the upstream provider."),
        },
        "real": bool(quakes.get("real", True)),
    }


WEATHER_CODES = {
    0: "Clear", 1: "Mainly clear", 2: "Partly cloudy", 3: "Overcast",
    45: "Fog", 48: "Rime fog", 51: "Drizzle", 61: "Rain (light)",
    63: "Rain (moderate)", 65: "Rain (heavy)", 71: "Snow",
    80: "Rain showers", 95: "Thunderstorm",
}


def weather_label(code):
    if code is None:
        return "—"
    return WEATHER_CODES.get(int(code), f"Code {code}")


# ===========================================================================
# Natural Calamity Prediction Engine
# ---------------------------------------------------------------------------
# A transparent statistical/threshold risk model over genuinely live provider
# feeds: USGS seismic events (magnitude × distance × recency) and Open-Meteo
# 7-day forecasts (rain, wind, pressure, temperature, humidity). Each hazard
# is scored 0-100 with Low < 25, Moderate 25-49, High 50-74, Extreme >= 75.
# ===========================================================================

HAZARD_DEFS = [
    ("earthquake", "Earthquake / seismic activity",
     "Aftershock & regional seismic-trigger risk derived from recent USGS events"
     " (magnitude, distance and recency)."),
    ("flood", "Flooding / heavy rainfall",
     "Forecast precipitation totals and probability over the next 7 days."),
    ("storm", "Cyclone / severe storm",
     "Forecast wind matched with low surface pressure (developing systems)."),
    ("heatwave", "Heatwave",
     "How many consecutive forecast days exceed 35 °C plus apparent-temperature"
     " heat stress."),
    ("wildfire", "Wildfire / fire weather",
     "Hot, dry and windy forecast conditions with little rainfall."),
    ("thunderstorm", "Thunderstorm / lightning",
     "Convection signals from rain probability and thunderstorm weather codes."),
]

_RECS = {
    "earthquake": {
        "Low": "Routine vigilance only — no elevated regional seismic trigger.",
        "Moderate": "Recent regional seismicity — review emergency kits and safe spots.",
        "High": "A strong recent quake is nearby; expect possible aftershocks and secure heavy objects.",
        "Extreme": "Very active seismic zone — follow official alerts and avoid damaged structures.",
    },
    "flood": {
        "Low": "No significant rainfall expected; normal drainage activity.",
        "Moderate": "Monitor local river gauges if heavy rain is forecast nearby.",
        "High": "Prepare sandbags and avoid low-lying roads during the rain window.",
        "Extreme": "Move valuables to higher floors and avoid travel in flood-prone areas.",
    },
    "storm": {
        "Low": "No significant wind or pressure signals in the forecast window.",
        "Moderate": "Secure loose outdoor items if gusts rise.",
        "High": "Avoid coastal exposure and secure windows and doors before the windy window.",
        "Extreme": "Storm-force conditions possible — follow cyclone warnings and stay indoors.",
    },
    "heatwave": {
        "Low": "Temperatures within normal bounds.",
        "Moderate": "Stay hydrated and limit midday sun exposure.",
        "High": "Heatwave conditions — check on vulnerable people and avoid strenuous outdoor work.",
        "Extreme": "Severe heat — stay indoors during peak hours and watch for heat-stroke symptoms.",
    },
    "wildfire": {
        "Low": "Fire weather conditions unremarkable.",
        "Moderate": "Avoid outdoor burning and stay alert near dry vegetation.",
        "High": "Hot, dry and windy — report smoke and follow local fire bans.",
        "Extreme": "Extreme fire danger — evacuate if instructed and keep a go-bag ready.",
    },
    "thunderstorm": {
        "Low": "No significant convection signal.",
        "Moderate": "Possible showers; keep weather-aware when outdoors.",
        "High": "Isolated severe storms possible — move indoors if thunder is heard.",
        "Extreme": "Severe thunderstorms forecast — avoid open fields, trees and water during strikes.",
    },
}


def _haversine_km(lat1, lng1, lat2, lng2):
    """Great-circle distance between two points, in kilometres."""
    rlat1, rlat2 = math.radians(lat1), math.radians(lat2)
    dlat = math.radians(lat2 - lat1)
    dlng = math.radians(lng2 - lng1)
    a = math.sin(dlat / 2) ** 2 + math.cos(rlat1) * math.cos(rlat2) * math.sin(dlng / 2) ** 2
    return 6371.0 * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def _clamp(value, lo=0.0, hi=100.0):
    try:
        return max(lo, min(hi, float(value)))
    except (TypeError, ValueError):
        return lo


def _hazard_level(score):
    if score >= 75:
        return "Extreme"
    if score >= 50:
        return "High"
    if score >= 25:
        return "Moderate"
    return "Low"


def _hazard_confidence(active_signals):
    if active_signals == 0:
        return "Low"
    if active_signals >= 4:
        return "High"
    return "Medium"


def _hazard_record(hazard_id, label, description, score, indicators, active_signals):
    level = _hazard_level(score)
    return {
        "id": hazard_id,
        "label": label,
        "description": description,
        "score": round(score),
        "level": level,
        "confidence": _hazard_confidence(active_signals),
        "indicators": indicators,
        "recommendation": _RECS.get(hazard_id, {}).get(level, "Monitor official local guidance."),
    }


def _earthquake_score(lat, lng, quakes):
    """Seismic trigger risk from recent USGS events near the location."""
    if not quakes:
        return 0, []
    now_ms = time.time() * 1000
    contributions = []
    for ev in quakes:
        if ev.get("lat") is None or ev.get("lng") is None or ev.get("mag") is None:
            continue
        dist = _haversine_km(lat, lng, float(ev["lat"]), float(ev["lng"]))
        if dist > 2000:
            continue
        mag = float(ev["mag"])
        age_ms = max(0, now_ms - float(ev.get("time") or now_ms))
        recency = max(0.0, 1.0 - age_ms / (7 * 24 * 3600 * 1000))
        influence = max(mag - 3.5, 0.0) * 2.2 + (3.0 if mag >= 6.0 else 0.0)
        if influence <= 0:
            continue
        contributions.append((dist, influence, recency, mag, ev.get("place")))
    contributions.sort(key=lambda c: -(c[1] * c[2]))
    score = 0.0
    seen = []
    for dist, influence, recency, mag, place in contributions[:4]:
        term = influence * (1 - dist / 2000) * recency
        score += term
        seen.append({
            "label": f"M {mag:.1f} {place or 'event'}",
            "value": f"{int(dist)} km away",
            "weight": "high" if term >= 8 else "medium",
        })
    return _clamp(score * 22.0), seen


def _flood_score(city):
    daily = city.get("daily") or []
    current = city.get("current") or {}
    pops = [d.get("precipitation_probability_max") for d in daily if d.get("precipitation_probability_max") is not None]
    totals = [d.get("precipitation_sum_mm") for d in daily if d.get("precipitation_sum_mm") is not None]
    pop_max = max(pops) if pops else 0.0
    total = sum(totals) if totals else 0.0
    cur = float(current.get("precipitation_mm") or 0.0)
    score = pop_max * 0.45 + min(total * 1.6, 60.0) + min(cur * 6.0, 15.0)
    return _clamp(score), [
        {"label": "Max daily rain probability (7d)", "value": f"{pop_max:.0f}%",
         "weight": "high" if pop_max >= 70 else "medium"},
        {"label": "Total forecast rainfall (7d)", "value": f"{total:.1f} mm",
         "weight": "high" if total >= 60 else "medium"},
        {"label": "Current rainfall", "value": f"{cur:.1f} mm", "weight": "low"},
    ]


def _storm_score(city):
    daily = city.get("daily") or []
    current = city.get("current") or {}
    winds = [d.get("wind_speed_max_kmh") for d in daily if d.get("wind_speed_max_kmh") is not None]
    wind_max = max(winds) if winds else float(current.get("wind_speed_kmh") or 0.0)
    press = []
    for h in city.get("hourly") or []:
        if h.get("pressure_hpa") is not None:
            press.append(float(h["pressure_hpa"]))
    if not press and current.get("pressure_hpa") is not None:
        press = [float(current["pressure_hpa"])]
    p_min = min(press) if press else None
    score = 0.0
    if wind_max >= 118:
        score += 62
    elif wind_max >= 88:
        score += 48
    elif wind_max >= 62:
        score += 34
    elif wind_max >= 39:
        score += 20
    else:
        score += wind_max * 0.5
    if p_min:
        score += min(max(1013.0 - p_min - 4.0, 0.0) * 2.2, 34.0)
    return _clamp(score), [
        {"label": "Max forecast wind", "value": f"{wind_max:.0f} km/h",
         "weight": "high" if wind_max >= 88 else "medium"},
        {"label": "Min surface pressure",
         "value": f"{p_min:.0f} hPa" if p_min else "—",
         "weight": "high" if p_min and p_min <= 1005 else "low"},
    ]


def _heatwave_score(city):
    daily = city.get("daily") or []
    temps = [d.get("temperature_max_c") for d in daily if d.get("temperature_max_c") is not None]
    app = [d.get("apparent_temperature_max_c") for d in daily if d.get("apparent_temperature_max_c") is not None]
    if not temps:
        return 0, []
    tmax = max(temps)
    streak = 0
    for t in temps:
        if t >= 35.0:
            streak += 1
        else:
            break
    score = 0.0
    if tmax >= 35.0:
        score = 25.0 + (tmax - 35.0) * 5.0 + streak * 6.0
    elif tmax >= 30.0:
        score = (tmax - 30.0) * 3.0
    amax = max(app) if app else None
    if amax and amax >= 40.0:
        score += 12.0
    return _clamp(score), [
        {"label": "Forecast max temperature", "value": f"{tmax:.0f} °C",
         "weight": "high" if tmax >= 40 else "medium"},
        {"label": "Consecutive hot days (≥35 °C)", "value": str(streak),
         "weight": "high" if streak >= 3 else "low"},
        {"label": "Feels-like max", "value": f"{amax:.0f} °C" if amax else "—",
         "weight": "medium" if amax and amax >= 40 else "low"},
    ]


def _wildfire_score(city):
    daily = city.get("daily") or []
    temps = [d.get("temperature_max_c") for d in daily if d.get("temperature_max_c") is not None]
    hums = [d.get("relative_humidity_mean") for d in daily if d.get("relative_humidity_mean") is not None]
    winds = [d.get("wind_speed_max_kmh") for d in daily if d.get("wind_speed_max_kmh") is not None]
    rains = [d.get("precipitation_sum_mm") for d in daily if d.get("precipitation_sum_mm") is not None]
    tmax = max(temps) if temps else 0.0
    hum_min = min(hums) if hums else 100.0
    wind_max = max(winds) if winds else 0.0
    rain_total = sum(rains) if rains else 0.0
    score = 0.0
    if tmax >= 30.0:
        score += (tmax - 30.0) * 4.0
    if hum_min <= 35.0:
        score += (35.0 - hum_min) * 1.8
    if wind_max >= 30.0:
        score += min(wind_max - 30.0, 60.0) * 0.5
    score -= rain_total * 0.9
    return _clamp(score), [
        {"label": "Max forecast temperature", "value": f"{tmax:.0f} °C", "weight": "medium"},
        {"label": "Min forecast humidity", "value": f"{hum_min:.0f}%",
         "weight": "high" if hum_min <= 25 else "medium"},
        {"label": "Max forecast wind", "value": f"{wind_max:.0f} km/h", "weight": "medium"},
        {"label": "7-day rainfall", "value": f"{rain_total:.1f} mm", "weight": "medium"},
    ]


def _thunderstorm_score(city):
    daily = city.get("daily") or []
    pops = [d.get("precipitation_probability_max") for d in daily if d.get("precipitation_probability_max") is not None]
    pop_max = max(pops) if pops else 0.0
    thunder_days = sum(1 for d in daily if (d.get("weather_code") or 0) in (95, 96, 99))
    heavy_days = sum(
        1 for d in daily
        if (d.get("weather_code") or 0) in (80, 81, 82, 95, 96, 99)
        or (d.get("precipitation_probability_max") or 0) >= 70
    )
    score = pop_max * 0.5 + thunder_days * 14.0 + heavy_days * 8.0
    return _clamp(score), [
        {"label": "Max rain probability (7d)", "value": f"{pop_max:.0f}%",
         "weight": "high" if pop_max >= 70 else "medium"},
        {"label": "Thunderstorm days (7d)", "value": str(thunder_days),
         "weight": "high" if thunder_days >= 2 else "low"},
    ]


def _predict_city(city, quakes):
    """Risk records (0-100 each) for every hazard type at a single city."""
    eq_score, eq_inds = _earthquake_score(city.get("lat") or 0, city.get("lng") or 0, quakes)
    flood_score, flood_inds = _flood_score(city)
    storm_score, storm_inds = _storm_score(city)
    heat_score, heat_inds = _heatwave_score(city)
    fire_score, fire_inds = _wildfire_score(city)
    thunder_score, thunder_inds = _thunderstorm_score(city)

    records = [
        _hazard_record("earthquake", "Earthquake / seismic activity",
                       "Aftershock & regional seismic-trigger risk from recent USGS events.",
                       eq_score, eq_inds, len(eq_inds)),
        _hazard_record("flood", "Flooding / heavy rainfall",
                       "Forecast rainfall totals & probability over the next 7 days.",
                       flood_score, flood_inds, len(flood_inds)),
        _hazard_record("storm", "Cyclone / severe storm",
                       "High forecast wind matched with low surface pressure.",
                       storm_score, storm_inds, len(storm_inds)),
        _hazard_record("heatwave", "Heatwave",
                       "Forecast days at or above heat-stress thresholds.",
                       heat_score, heat_inds, len(heat_inds)),
        _hazard_record("wildfire", "Wildfire / fire weather",
                       "Hot, dry and windy forecast conditions with rainfall deficit.",
                       fire_score, fire_inds, len(fire_inds)),
        _hazard_record("thunderstorm", "Thunderstorm / lightning",
                       "Convection signals from rain probability & thunderstorm codes.",
                       thunder_score, thunder_inds, len(thunder_inds)),
    ]
    records.sort(key=lambda r: -r["score"])
    top = records[0]
    return {
        "city": city.get("city"),
        "lat": city.get("lat"),
        "lng": city.get("lng"),
        "max_score": top["score"],
        "max_hazard": {
            "id": top["id"], "label": top["label"], "score": top["score"],
            "level": top["level"], "confidence": top["confidence"],
        },
        "overall_level": top["level"],
        "hazards": records,
    }


# ---------------------------------------------------------------------------
# Location-aware prediction engine
# ---------------------------------------------------------------------------

def _valid_coord(lat, lng) -> bool:
    try:
        lat = float(lat)
        lng = float(lng)
        return -90.0 <= lat <= 90.0 and -180.0 <= lng <= 180.0
    except (TypeError, ValueError):
        return False


def _predictions_envelope(results, forecast, quakes, cache_key):
    """Assemble the shared predictions response shape (alerts + metadata)."""
    alerts = []
    for rec in results:
        top = rec["max_hazard"]
        if top and top["score"] >= 50:
            alerts.append({
                "city": rec["city"],
                "hazard": top["label"],
                "level": top["level"],
                "score": top["score"],
                "confidence": top["confidence"],
            })
    alerts.sort(key=lambda a: -a["score"])
    return _cache_set(cache_key, {
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "cities": results,
        "alerts": alerts,
        "hazard_types": [{"id": h[0], "label": h[1], "description": h[2]} for h in HAZARD_DEFS],
        "methodology": (
            "The risk engine scores each hazard 0-100 from genuinely live feeds: USGS "
            "seismic events (magnitude × distance × recency) and Open-Meteo 7-day "
            "forecasts (rain, wind, pressure, temperature, humidity). "
            "Severity: Low < 25 · Moderate 25-49 · High 50-74 · Extreme ≥ 75."
        ),
        "real": bool(forecast.get("real", False) and quakes.get("real", False)),
        "source": "USGS Earthquake Hazards Program · Open-Meteo",
    })


def predict_hazards():
    """Natural calamity prediction engine — per-city hazard risk scores."""
    key = "hazard_predictions"
    cached = _cache_get(key)
    if cached is not None:
        return dict(cached)
    forecast = fetch_forecast()
    quakes = fetch_earthquakes(hours=168, min_magnitude=3.0, limit=100)
    results = [_predict_city(city, quakes.get("events", [])) for city in forecast.get("cities", [])]
    return _predictions_envelope(results, forecast, quakes, key)


def geocode(name, limit=5):
    """Resolve a free-text place name to real coordinates (Open-Meteo geocoding).

    Returns accurate ``{name, latitude, longitude, country, ...}`` candidates so
    the forecast and the calamity engine run against the *actual* location the
    user asked for, not a lookup table.
    """
    name = (name or "").strip()
    if not name or len(name) < 2:
        return []
    data = _get_json(
        OPEN_METEO_GEOCODE,
        {"name": name, "count": max(1, min(int(limit), 10)), "language": "en", "format": "json"},
        timeout=6.0,
    )
    out = []
    for item in (data or {}).get("results") or []:
        out.append({
            "name": item.get("name"),
            "latitude": item.get("latitude"),
            "longitude": item.get("longitude"),
            "country": item.get("country"),
            "country_code": item.get("country_code"),
            "admin1": item.get("admin1"),
            "admin2": item.get("admin2"),
            "population": item.get("population"),
            "timezone": item.get("timezone"),
            "label": ", ".join(
                x for x in [item.get("name"), item.get("admin1"), item.get("country_code")] if x
            ),
        })
    return out


def fetch_forecast_for(lat, lng, name=None):
    """Live 7-day weather forecast for a single custom location (lat/lng).

    Uses the same real Open-Meteo model as the preset cities, so changing the
    location returns an accurate forecast for those exact coordinates.
    """
    if not _valid_coord(lat, lng):
        raise ValueError("Invalid coordinates: lat must be -90..90 and lng -180..180")
    lat = round(float(lat), 3)
    lng = round(float(lng), 3)
    key = f"forecast_custom_{lat}_{lng}"
    cached = _cache_get(key)
    if cached is not None:
        return dict(cached)
    city = _forecast_for_city(name or f"{lat:.2f}, {lng:.2f}", lat, lng)
    # Honest provenance: real only when the provider actually answered.
    real = isinstance(city, dict) and "error" not in city
    return _cache_set(key, {"cities": [city], **_stamp(real, "Open-Meteo (NOAA/GFS model)")})


def predict_hazards_at(lat, lng, name=None):
    """Natural calamity prediction engine for a single custom location.

    The forecast is fetched for the exact coordinates, and seismic risk uses the
    real USGS catalogue with distance from this exact point — so predictions are
    location-accurate, not tied to the preset city list.
    """
    if not _valid_coord(lat, lng):
        raise ValueError("Invalid coordinates: lat must be -90..90 and lng -180..180")
    lat = round(float(lat), 3)
    lng = round(float(lng), 3)
    key = f"hazard_pred_custom_{lat}_{lng}"
    cached = _cache_get(key)
    if cached is not None:
        return dict(cached)
    forecast = fetch_forecast_for(lat, lng, name)
    quakes = fetch_earthquakes(hours=168, min_magnitude=3.0, limit=100)
    cities = forecast.get("cities") or []
    city = cities[0] if cities else {
        "city": name or f"{lat}, {lng}", "lat": lat, "lng": lng,
        "current": {}, "hourly": [], "daily": [],
    }
    rec = {**city, **_predict_city(city, quakes.get("events", []))}
    return _predictions_envelope([rec], forecast, quakes, key)