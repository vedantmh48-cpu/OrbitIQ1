"""Tests for the real-time weather forecast + natural calamity prediction engine.

The realtime service is network-dependent, so these tests bypass the network and
the on-disk cache via monkeypatched ``_get_json`` / ``_cache_get`` / ``_cache_set``
and assert the endpoint contracts + scoring behaviour.
"""
from datetime import datetime, timedelta, timezone

import pytest

from app.services import realtime as rt


def _dates(n):
    today = datetime.now(timezone.utc)
    return [(today - timedelta(days=i)).strftime("%Y-%m-%d") for i in range(n)]


def _hours(n):
    start = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0)
    return [(start + timedelta(hours=i)).strftime("%Y-%m-%dT%H:%M") for i in range(n)]


def _fake_meteo(url, params, timeout=6.0):
    """Deterministic canned Open-Meteo-style response."""
    return {
        "timezone": "UTC",
        "current": {
            "temperature_2m": 29.0,
            "relative_humidity_2m": 58,
            "apparent_temperature": 31.0,
            "weather_code": 2,
            "wind_speed_10m": 18.0,
            "wind_direction_10m": 200.0,
            "precipitation": 0.0,
            "cloud_cover": 40,
            "pressure_msl": 1008.0,
            "surface_pressure": 1006.0,
            "is_day": 1,
            "uv_index": 6.0,
            "visibility": 20.0,
        },
        "current_units": {"temperature_2m": "°C", "wind_speed_10m": "km/h"},
        "hourly": {
            "time": _hours(48),
            "temperature_2m": [29.0 + (i % 8) * 0.6 for i in range(48)],
            "apparent_temperature": [31.0 + (i % 8) * 0.6 for i in range(48)],
            "precipitation_probability": [0, 10, 20, 5] * 12,
            "precipitation": [0.0] * 48,
            "weather_code": [2] * 48,
            "wind_speed_10m": [18.0] * 48,
            "wind_direction_10m": [200.0] * 48,
            "relative_humidity_2m": [58] * 48,
            "cloud_cover": [40] * 48,
            "pressure_msl": [1008.0] * 48,
        },
        "daily": {
            "time": _dates(7),
            "weather_code": [2, 2, 61, 61, 95, 3, 3],
            "temperature_2m_max": [33, 34, 31, 30, 29, 32, 33],
            "temperature_2m_min": [23, 24, 23, 22, 21, 22, 23],
            "apparent_temperature_max": [36, 37, 33, 32, 31, 34, 35],
            "precipitation_sum": [0, 0, 12, 24, 30, 4, 1],
            "precipitation_probability_max": [10, 20, 65, 80, 90, 45, 30],
            "wind_speed_10m_max": [22, 24, 38, 55, 72, 26, 18],
            "wind_direction_10m_dominant": [180, 180, 170, 160, 150, 160, 170],
            "uv_index_max": [8, 8, 6, 5, 4, 6, 7],
            "relative_humidity_2m_mean": [55, 52, 66, 72, 78, 60, 54],
            "sunrise": ["06:00"] * 7,
            "sunset": ["18:30"] * 7,
        },
    }


def _fake_usgs(url, params, timeout=6.0):
    """Canned USGS GeoJSON feed with one strong recent quake near Tokyo.

    GeoJSON coordinates are ``[longitude, latitude, depth]`` — (139°E, 35°N)
    puts the M5.8 event just off Tokyo.
    """
    now_ms = datetime.now(timezone.utc).timestamp() * 1000
    return {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "id": "test-eq-1",
                "properties": {
                    "mag": 5.8,
                    "place": "10 km S of Test City",
                    "time": now_ms,
                    "tsunami": 0,
                    "url": "https://example.test/event/us1",
                    "felt": 42,
                    "magType": "mb",
                    "mmi": 4.0,
                    "updated": now_ms,
                },
                "geometry": {"type": "Point", "coordinates": [139.0, 35.0, 10.0]},
            },
            {
                "type": "Feature",
                "id": "test-eq-2",
                "properties": {
                    "mag": 3.2,
                    "place": "mid-ocean",
                    "time": now_ms - 12 * 3600 * 1000,
                    "tsunami": 0,
                    "url": "https://example.test/event/us2",
                },
                "geometry": {"type": "Point", "coordinates": [-45.0, -35.0, 33.0]},
            },
        ],
    }


def _fake_geocode(url, params, timeout=6.0):
    """Canned Open-Meteo geocoding response for a place-name search."""
    return {
        "results": [
            {
                "name": "Bengaluru",
                "latitude": 12.9716,
                "longitude": 77.5946,
                "country": "India",
                "country_code": "IN",
                "admin1": "Karnataka",
                "timezone": "Asia/Kolkata",
                "population": 8443675,
            },
            {
                "name": "Bengaluru West",
                "latitude": 12.94,
                "longitude": 77.54,
                "country": "India",
                "country_code": "IN",
                "admin1": "Karnataka",
                "population": 100_000,
            },
        ]
    }


@pytest.fixture()
def rt_offline(monkeypatch):
    """Bypass the realtime network layer + the on-disk cache."""
    monkeypatch.setattr(rt, "_cache_get", lambda key: None)
    monkeypatch.setattr(rt, "_cache_set", lambda key, value: value)

    def fake_get(url, params, timeout=6.0):
        if "usgs" in url:
            return _fake_usgs(url, params)
        if "geocoding" in url:
            return _fake_geocode(url, params)
        return _fake_meteo(url, params)

    monkeypatch.setattr(rt, "_get_json", fake_get)


def test_forecast_endpoint(client, auth_headers, rt_offline):
    """GET /api/realtime/forecast returns current + hourly + 7-day daily series."""
    r = client.get("/api/realtime/forecast", headers=auth_headers)
    assert r.status_code == 200
    body = r.json()
    assert body["real"] is True
    assert len(body["cities"]) == 7
    city = body["cities"][0]
    assert set(city["current"]) >= {"temperature_c", "weather_code", "wind_speed_kmh"}
    assert len(city["daily"]) == 7
    assert len(city["hourly"]) >= 24
    first_day = city["daily"][0]
    assert "temperature_max_c" in first_day and "precipitation_probability_max" in first_day


def test_predictions_endpoint(client, auth_headers, rt_offline):
    """GET /api/realtime/predictions returns score, level & indicators per hazard."""
    r = client.get("/api/realtime/predictions", headers=auth_headers)
    assert r.status_code == 200
    body = r.json()
    assert len(body["cities"]) == 7
    assert body["methodology"]
    first = body["cities"][0]
    assert 0 <= first["max_score"] <= 100
    ids = {h["id"] for h in first["hazards"]}
    assert {"earthquake", "flood", "storm", "heatwave", "wildfire", "thunderstorm"} <= ids
    for hazard in first["hazards"]:
        assert 0 <= hazard["score"] <= 100
        assert hazard["level"] in ("Low", "Moderate", "High", "Extreme")
        assert hazard["confidence"] in ("Low", "Medium", "High")
        assert isinstance(hazard["recommendation"], str) and hazard["recommendation"]


def test_seismic_score_isolates_nearby_strong_quake(rt_offline):
    """A strong recent quake near Tokyo must raise its score above far cities."""
    now = datetime.now(timezone.utc)
    quakes = [
        {"lat": 35.0, "lng": 139.0, "mag": 7.1,
         "time": now.timestamp() * 1000, "place": "Test City Area"},
    ]
    tokyo, _ = rt._earthquake_score(35.68, 139.69, quakes)
    mumbai, _ = rt._earthquake_score(19.076, 72.8777, quakes)
    assert tokyo > 25
    assert tokyo > mumbai


def test_hazard_levels_boundaries():
    assert rt._hazard_level(0) == "Low"
    assert rt._hazard_level(24.9) == "Low"
    assert rt._hazard_level(25) == "Moderate"
    assert rt._hazard_level(49.9) == "Moderate"
    assert rt._hazard_level(50) == "High"
    assert rt._hazard_level(74.9) == "High"
    assert rt._hazard_level(75) == "Extreme"
    assert rt._hazard_level(100) == "Extreme"


# ---------------------------------------------------------------------------
# Location-aware forecast & predictions
# ---------------------------------------------------------------------------


def test_geocode_endpoint(client, auth_headers, rt_offline):
    """GET /api/realtime/geocode returns accurate coordinate candidates."""
    r = client.get("/api/realtime/geocode", params={"q": "Bengaluru"}, headers=auth_headers)
    assert r.status_code == 200
    results = r.json()["results"]
    assert len(results) == 2
    first = results[0]
    assert first["name"] == "Bengaluru"
    assert abs(first["latitude"] - 12.9716) < 1e-6
    assert abs(first["longitude"] - 77.5946) < 1e-6
    assert "Karnataka" in first["label"]


def test_forecast_custom_location(client, auth_headers, rt_offline):
    """Forecast for a custom lat/lng returns that single location in 7-day detail."""
    r = client.get(
        "/api/realtime/forecast",
        params={"lat": 12.9716, "lng": 77.5946, "name": "Bengaluru"},
        headers=auth_headers,
    )
    assert r.status_code == 200
    body = r.json()
    assert len(body["cities"]) == 1
    city = body["cities"][0]
    assert city["city"] == "Bengaluru"
    assert len(city["daily"]) == 7
    assert len(city["hourly"]) >= 24
    assert "temperature_c" in city["current"]


def test_predictions_custom_location(client, auth_headers, rt_offline):
    """Predictions for a custom lat/lng use that point's forecast + seismic distance."""
    r = client.get(
        "/api/realtime/predictions",
        params={"lat": 35.68, "lng": 139.69, "name": "Tokyo (custom)"},
        headers=auth_headers,
    )
    assert r.status_code == 200
    body = r.json()
    assert len(body["cities"]) == 1
    city = body["cities"][0]
    assert city["city"] == "Tokyo (custom)"
    assert abs(city["lat"] - 35.68) < 1e-3
    ids = {h["id"] for h in city["hazards"]}
    assert {"earthquake", "flood", "storm", "heatwave", "wildfire", "thunderstorm"} <= ids
    # Close to the fake M5.8 quake at (35,139): seismic risk must be elevated.
    eq = next(h for h in city["hazards"] if h["id"] == "earthquake")
    assert eq["score"] >= 25


def test_custom_location_requires_both_coords_or_valid_ranges(client, auth_headers, rt_offline):
    assert client.get(
        "/api/realtime/forecast", params={"lat": 12.9}, headers=auth_headers
    ).status_code == 422
    assert client.get(
        "/api/realtime/predictions", params={"lat": 999, "lng": 12}, headers=auth_headers
    ).status_code == 422
    assert client.get(
        "/api/realtime/geocode", params={"q": "x"}, headers=auth_headers
    ).status_code == 422