"""Tests for the historical change-analysis feature (op: ``change-analysis``).

Covers the dependency-free raster engine, geocoding, query->technique mapping,
the VLM report template, artifact encoders (PNG/GeoTIFF) and the full HTTP
journey (job -> result bundle -> image/mask/report endpoints).
"""
from __future__ import annotations

from datetime import date

import pytest
import time

from app.services.change_analysis import geocoding as geo_mod
from app.services.change_analysis import engine as engine_mod
from app.services.change_analysis import raster as rx
from app.services.change_analysis import vlm as vlm_mod


def simple_location(text=None, lat=None, lng=None):
    from app.schemas import ChangeLocation

    return ChangeLocation(text=text, latitude=lat, longitude=lng)


# ---------------------------------------------------------------------------
# Geocoding
# ---------------------------------------------------------------------------


class TestGeocoding:
    def test_coordinates_aoi(self):
        aoi = geo_mod.geocode_coordinates(19.076, 72.8777, buffer_km=1.0)
        assert aoi["kind"] == "gps-point"
        assert aoi["bbox"]["min_lng"] < aoi["bbox"]["max_lng"]
        assert aoi["bbox"]["min_lat"] < aoi["bbox"]["max_lat"]
        assert 0.5 < aoi["area_km2"] < 10.0
        assert aoi["center"] == {"lat": 19.076, "lng": 72.8777}

    def test_gazetteer(self):
        aoi = geo_mod.geocode_gazetteer("Mumbai")
        assert aoi is not None
        assert aoi["source"] == "gazetteer"
        assert aoi["name"] == "Mumbai"
        assert aoi["bbox"]["min_lat"] < aoi["bbox"]["max_lat"]

    def test_unknown_location_raises(self):
        with pytest.raises(geo_mod.LocationError):
            geo_mod.resolve_location(simple_location(text="Atlantisz City"))


# ---------------------------------------------------------------------------
# Raster engine
# ---------------------------------------------------------------------------


class TestRaster:
    BBOX = {"min_lng": 72.8, "min_lat": 18.9, "max_lng": 73.0, "max_lat": 19.1}

    def test_scene_deterministic(self):
        s1a = rx.build_scene(date(2015, 1, 1), self.BBOX, 40, 40, evolution=0.0)
        s1b = rx.build_scene(date(2015, 1, 1), self.BBOX, 40, 40, evolution=0.0)
        assert s1a["bands"]["nir"] == s1b["bands"]["nir"]

    def test_indices_bounded(self):
        s = rx.build_scene(date(2016, 6, 1), self.BBOX, 40, 40, evolution=0.0)
        for idx in ("ndvi", "ndwi", "ndbi"):
            for row in s[idx]:
                for v in row:
                    assert -1.0 <= v <= 1.0

    def test_evolution_changes_scene(self):
        s1 = rx.build_scene(date(2015, 1, 1), self.BBOX, 60, 60, evolution=0.0)
        s2 = rx.build_scene(date(2020, 1, 1), self.BBOX, 60, 60, evolution=1.0)
        built_1 = sum(1 for r in s1["classes"] for c in r if c == rx.BUILT)
        built_2 = sum(1 for r in s2["classes"] for c in r if c == rx.BUILT)
        water_1 = sum(1 for r in s1["classes"] for c in r if c == rx.WATER)
        water_2 = sum(1 for r in s2["classes"] for c in r if c == rx.WATER)
        assert built_2 > built_1       # construction expansion
        assert water_2 <= water_1      # water-line retreat

    def test_png_encoder(self):
        data = rx.write_png(4, 4, bytes(4 * 4 * 3), color_type=2)
        assert data[:8] == b"\x89PNG\r\n\x1a\n"

    def test_geotiff_encoder_parses(self):
        from app.services.geotools import parse_geotiff

        rows = [[50, 120], [200, 255], [0, 30]]
        data = rx.write_geotiff(rows, min_lng=72.0, max_lat=19.0,
                                pixel_w=0.001, pixel_h=0.001)
        info = parse_geotiff(data)
        assert info["dimensions"]["width"] == 2
        assert info["dimensions"]["height"] == 3
        assert info["crs"]["epsg"] == 4326
        assert info["bounds"]["min_lng"] == pytest.approx(72.0)
        assert info["bounds"]["max_lat"] == pytest.approx(19.0)


# ---------------------------------------------------------------------------
# Query interpretation
# ---------------------------------------------------------------------------


class TestQueryMapping:
    def test_building_query_picks_ndbi(self):
        techs = engine_mod.select_techniques("Track new building construction")
        assert "ndbi" in techs
        interp = vlm_mod.interpret_query("Track new building construction", techs)
        assert "built-up" in interp["lens"]

    def test_water_query_picks_ndwi(self):
        techs = engine_mod.select_techniques("Monitor water body shrinkage")
        assert "ndwi" in techs

    def test_requested_techniques_respected(self):
        techs = engine_mod.select_techniques("anything", ["ndvi"])
        assert techs[0] == "ndvi"


# ---------------------------------------------------------------------------
# Engine end-to-end
# ---------------------------------------------------------------------------


class TestEngine:
    BBOX = {"min_lng": 72.8, "min_lat": 18.9, "max_lng": 73.0, "max_lat": 19.1}

    def test_full_analysis(self, tmp_path):
        out = engine_mod.run_change_analysis(
            aoi={"bbox": self.BBOX, "name": "Mumbai test", "area_km2": 1.0},
            query="Track new building construction",
            date_1=date(2015, 1, 1),
            date_2=date(2020, 1, 1),
            max_cells=2500,
            artifact_dir=tmp_path,
            image_size=90,
        )
        stats = out["stats"]
        assert stats["changed_cells"] > 0
        assert stats["total_cells"] > 0
        assert stats["changed_area_km2"] > 0
        assert stats["pct_changed"] > 0
        assert out["hotspots"]
        assert out["geojson"]["features"]
        assert (tmp_path / "before.png").read_bytes()[:8] == b"\x89PNG\r\n\x1a\n"
        assert (tmp_path / "heatmap.png").read_bytes()[:8] == b"\x89PNG\r\n\x1a\n"
        assert (tmp_path / "change-intensity.tif").read_bytes()[:2] == b"II"

    def test_detection_recovers_synthetic_truth(self, tmp_path):
        out = engine_mod.run_change_analysis(
            aoi={"bbox": self.BBOX, "name": "truth", "area_km2": 1.0},
            query="Show infrastructure change",
            date_1=date(2015, 1, 1),
            date_2=date(2020, 1, 1),
            max_cells=1600,
            artifact_dir=tmp_path,
            image_size=64,
        )
        assert out["stats"]["changed_cells"] > 20


# ---------------------------------------------------------------------------
# HTTP API journey
# ---------------------------------------------------------------------------


def _payload(location, dates=True, overrides=None):
    body = {
        "location": location,
        "date_1": "2015-01-01",
        "date_2": "2020-01-01",
        "query": "Track new building construction",
        "techniques": ["ndbi"],
        "max_cells": 1600,
    }
    if not dates:
        body["date_2"] = "2014-01-01"
    if overrides:
        body.update(overrides)
    return body


def _wait_job(client, headers, job_id, timeout=30):
    deadline = time.time() + timeout
    while time.time() < deadline:
        r = client.get(f"/api/change-analysis/jobs/{job_id}", headers=headers)
        assert r.status_code == 200
        data = r.json()
        if data["status"] in ("completed", "failed"):
            return data
        time.sleep(0.15)
    raise AssertionError(f"change-analysis job {job_id} did not finish (timeout)")


class TestChangeAnalysisApi:
    def test_full_flow(self, client, auth_headers, monkeypatch):
        from app.config import settings

        monkeypatch.setattr(settings, "CHANGE_IMAGERY_MODE", "demo")
        r = client.post(
            "/api/change-analysis",
            json=_payload({"text": "Mumbai"}),
            headers=auth_headers,
        )
        assert r.status_code == 202, r.text
        data = r.json()
        assert data["status"] == "running"
        job_id = data["job_id"]

        job = _wait_job(client, auth_headers, job_id)
        assert job["status"] == "completed"
        result_id = job["result_id"]

        job2 = client.get(f"/api/change-analysis/jobs/{job_id}", headers=auth_headers)
        assert job2.status_code == 200
        assert job2.json()["status"] == "completed"

        res = client.get(f"/api/change-analysis/results/{result_id}", headers=auth_headers)
        assert res.status_code == 200, res.text
        bundle = res.json()
        assert bundle["op"] == "change-analysis"
        assert bundle["stats"]["changed_cells"] > 0
        assert bundle["report_md"]
        assert bundle["hotspots"]
        assert bundle["layers"]

        img = client.get(
            f"/api/change-analysis/results/{result_id}/images/heatmap.png",
            headers=auth_headers,
        )
        assert img.status_code == 200
        assert img.content[:8] == b"\x89PNG\r\n\x1a\n"

        # <img> tags cannot send Authorization headers -> token query path.
        access = auth_headers["Authorization"].replace("Bearer ", "")
        img2 = client.get(
            f"/api/change-analysis/results/{result_id}/images/before.png?token={access}"
        )
        assert img2.status_code == 200
        assert img2.content[:8] == b"\x89PNG\r\n\x1a\n"

        tif = client.get(
            f"/api/change-analysis/results/{result_id}/raster.tif",
            headers=auth_headers,
        )
        assert tif.status_code == 200
        assert tif.content[:2] == b"II"

        masks = client.get(
            f"/api/change-analysis/results/{result_id}/masks.geojson",
            headers=auth_headers,
        )
        assert masks.status_code == 200
        assert masks.json()["features"]

        report = client.get(
            f"/api/change-analysis/results/{result_id}/report.md",
            headers=auth_headers,
        )
        assert report.status_code == 200
        assert "## What changed" in report.text

        generic = client.get(f"/api/results/{result_id}", headers=auth_headers)
        assert generic.status_code == 200

    def test_coordinates_flow(self, client, auth_headers, monkeypatch):
        from app.config import settings

        monkeypatch.setattr(settings, "CHANGE_IMAGERY_MODE", "demo")
        r = client.post(
            "/api/change-analysis",
            json=_payload({"latitude": 19.076, "longitude": 72.8777}),
            headers=auth_headers,
        )
        assert r.status_code == 202, r.text
        job = _wait_job(client, auth_headers, r.json()["job_id"])
        assert job["status"] == "completed"
        assert job["result_id"]

    def test_geocode_preview(self, client, auth_headers):
        r = client.get("/api/change-analysis/geocode?q=Mumbai", headers=auth_headers)
        assert r.status_code == 200
        assert r.json()["aoi"]["name"] == "Mumbai"

    def test_date_order_rejected(self, client, auth_headers):
        r = client.post(
            "/api/change-analysis",
            json=_payload({"text": "Mumbai"}, dates=False),
            headers=auth_headers,
        )
        assert r.status_code == 422

    def test_bad_technique_rejected(self, client, auth_headers):
        r = client.post(
            "/api/change-analysis",
            json=_payload({"text": "Mumbai"}, overrides={"techniques": ["bogus"]}),
            headers=auth_headers,
        )
        assert r.status_code == 422

    def test_requires_auth(self, client):
        r = client.post("/api/change-analysis", json=_payload({"text": "Mumbai"}))
        assert r.status_code in (401, 403)