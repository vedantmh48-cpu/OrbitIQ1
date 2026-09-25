"""Real-time data routes: live board, events, and dataset-style feeds."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query

from ..deps import get_current_user
from ..storage import get_db
from ..services import realtime as rt

router = APIRouter(prefix="/api/realtime", tags=["realtime"])


@router.get("/overview")
def overview(user: dict = Depends(get_current_user)):
    """Live board of real-time observations (earthquakes + weather)."""
    return rt.fetch_overview()


@router.get("/earthquakes")
def earthquakes(
    hours: int = Query(48, ge=1, le=720),
    min_magnitude: float = Query(2.5, ge=0, le=10),
    limit: int = Query(80, ge=1, le=200),
    user: dict = Depends(get_current_user),
):
    return rt.fetch_earthquakes(hours=hours, min_magnitude=min_magnitude, limit=limit)


@router.get("/weather")
def weather(user: dict = Depends(get_current_user)):
    return rt.fetch_weather()


@router.get("/geocode")
def geocode(
    q: str = Query(..., min_length=2, max_length=120),
    limit: int = Query(5, ge=1, le=10),
    user: dict = Depends(get_current_user),
):
    """Resolve a place name to accurate coordinates for the forecast/prediction tools."""
    return {"results": rt.geocode(q, limit=limit)}


@router.get("/forecast")
def forecast(
    lat: float | None = None,
    lng: float | None = None,
    name: str | None = None,
    user: dict = Depends(get_current_user),
):
    """7-day real-time weather forecast.

    * No coords      -> the preset global cities (Weather Forecast section default)
    * ``lat``+``lng`` -> a live 7-day forecast for that exact location (``name``
      is an optional display label), cached per coordinate.
    """
    if lat is not None and lng is not None:
        try:
            return rt.fetch_forecast_for(lat, lng, name)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc))
    if (lat is None) != (lng is None):
        raise HTTPException(status_code=422, detail="Provide both lat and lng (with an optional name).")
    return rt.fetch_forecast()


@router.get("/predictions")
def predictions(
    lat: float | None = None,
    lng: float | None = None,
    name: str | None = None,
    user: dict = Depends(get_current_user),
):
    """Natural calamity prediction engine — hazard risk scores.

    * No coords   -> risk scores for the preset global cities
    * ``lat``+``lng`` -> risk scores for that exact location, using the real
      USGS catalogue (distance from this point) and the Open-Meteo forecast at
      those coordinates.
    """
    if lat is not None and lng is not None:
        try:
            return rt.predict_hazards_at(lat, lng, name)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc))
    if (lat is None) != (lng is None):
        raise HTTPException(status_code=422, detail="Provide both lat and lng (with an optional name).")
    return rt.predict_hazards()


@router.get("/climate")
def climate(
    lat: float,
    lng: float,
    start: str | None = None,
    end: str | None = None,
    days: int = Query(30, ge=2, le=365),
    user: dict = Depends(get_current_user),
):
    return rt.fetch_climate(lat, lng, start, end, days)


@router.get("/datasets")
def realtime_datasets(user: dict = Depends(get_current_user)):
    """Expose live feeds as catalogue-style entries for the datasets page."""
    from ..geo import as_feature_collection

    quakes = rt.fetch_earthquakes(hours=24)
    weather = rt.fetch_weather()
    now = rt.datetime.now(rt.timezone.utc)

    quake_features = [
        {
            "type": "Feature",
            "properties": {
                "label": "Earthquake",
                "mag": ev.get("mag"),
                "place": ev.get("place"),
                "depth_km": ev.get("depth_km"),
                "time": _ts(ev.get("time")),
                "tsunami": ev.get("tsunami"),
            },
            "geometry": {"type": "Point", "coordinates": [ev["lng"], ev["lat"]]},
        }
        for ev in quakes.get("events", [])
        if ev.get("lat") is not None and ev.get("lng") is not None
    ]
    weather_features = [
        {
            "type": "Feature",
            "properties": {
                "label": "Weather station",
                "city": c.get("city"),
                "temperature_c": c.get("temperature_c"),
                "weather": rt.weather_label(c.get("weather_code")),
                "humidity": c.get("relative_humidity"),
                "wind_kmh": c.get("wind_speed_kmh"),
            },
            "geometry": {"type": "Point", "coordinates": [c["lng"], c["lat"]]},
        }
        for c in weather.get("cities", [])
        if c.get("lat") is not None and c.get("lng") is not None
    ]

    feeds = [
        {
            "id": "live_usgs_earthquakes",
            "name": "Live Earthquakes — last 24h (USGS)",
            "provider_id": "realtime",
            "data_type": "Vector",
            "phenomenons": ["earthquake"],
            "source": "REAL",
            "real": True,
            "simulated": False,
            "satellite": "USGS seismic network",
            "resolution": "point events",
            "bbox": {"min_lng": -180, "min_lat": -90, "max_lng": 180, "max_lat": 90},
            "description": "Real-time earthquake events streamed from the USGS "
                           "Earthquake Hazards Program (magnitude, depth, place).",
            "observed_at": quakes.get("observed_at"),
            "temporal": {"start": "", "end": now.isoformat(), "count": len(quake_features)},
            "tags": ["live", "earthquake", "seismic", "real"],
            "geojson_preview": as_feature_collection(
                quake_features, {"title": "Live earthquakes", "real": True}
            ),
        },
        {
            "id": "live_weather_cities",
            "name": "Live Weather — global cities (Open-Meteo)",
            "provider_id": "realtime",
            "data_type": "Time-Series",
            "phenomenons": ["cyclone", "drought"],
            "source": "REAL",
            "real": True,
            "simulated": False,
            "satellite": "Open-Meteo (NOAA/GFS)",
            "resolution": "city station",
            "bbox": {"min_lng": -125, "min_lat": -34, "max_lng": 140, "max_lat": 61},
            "description": "Live current and forecast weather for seven global "
                           "cities, refreshed from Open-Meteo.",
            "observed_at": weather.get("observed_at"),
            "temporal": {"start": "", "end": now.isoformat(), "count": len(weather_features)},
            "tags": ["live", "weather", "climate", "real"],
            "geojson_preview": as_feature_collection(
                weather_features, {"title": "Live weather stations", "real": True}
            ),
        },
    ]
    return {"feeds": feeds, "updated_at": now.isoformat()}


def _ts(ms) -> str | None:
    if not ms:
        return None
    try:
        return rt.datetime.fromtimestamp(ms / 1000, rt.timezone.utc).isoformat()
    except Exception:
        return None