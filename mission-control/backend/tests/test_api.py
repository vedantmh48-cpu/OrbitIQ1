"""Smoke tests for the Mission Control API.

Run from the backend folder:  python -m pytest tests -q
"""
from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_health():
    res = client.get("/api/health")
    assert res.status_code == 200
    body = res.json()
    assert body["status"] == "nominal"
    assert body["version"]


def test_overview_aggregates():
    res = client.get("/api/overview")
    assert res.status_code == 200
    body = res.json()
    assert body["missions"]["total"] >= 1
    assert body["fleet"]["total"] == 6
    assert "alerts" in body


def test_mission_crud_flow():
    # create
    res = client.post(
        "/api/missions",
        json={
            "name": "Coastal Flood Watch",
            "satellite": "SENTINEL-2A",
            "target": "Delta lowlands · Sector C2",
            "region": "Bay Corridor",
            "priority": "high",
            "objective": "Weekly flood-extent refresh for civil protection.",
        },
    )
    assert res.status_code == 201
    mission = res.json()
    assert mission["status"] == "planned"
    assert mission["code"].startswith("MC-")
    mid = mission["id"]

    # list includes it
    names = [m["name"] for m in client.get("/api/missions").json()]
    assert "Coastal Flood Watch" in names

    # update status + progress
    res = client.patch(f"/api/missions/{mid}", json={"status": "in-progress", "progress": 33})
    assert res.status_code == 200
    updated = res.json()
    assert updated["status"] == "in-progress"
    assert updated["progress"] == 33

    # invalid status rejected
    res = client.patch(f"/api/missions/{mid}", json={"status": "flying"})
    assert res.status_code == 422

    # fetch single + delete
    assert client.get(f"/api/missions/{mid}").status_code == 200
    assert client.delete(f"/api/missions/{mid}").status_code == 204
    assert client.get(f"/api/missions/{mid}").status_code == 404


def test_satellites_listed():
    sats = client.get("/api/satellites").json()
    ids = {s["id"] for s in sats}
    assert "sa-07" in ids and "ge-17" in ids


def test_telemetry_advances_and_histories():
    first = client.get("/api/telemetry/sa-07").json()
    second = client.get("/api/telemetry/sa-07").json()
    assert first["satellite"] == "SENTINEL-2A"
    assert len(first["history"]) >= 1
    # each poll appends a new sample, so history grows
    assert len(second["history"]) == len(first["history"]) + 1
    assert {"link", "battery", "temp", "altitude", "signal", "data"} <= set(
        second["current"].keys()
    )
    assert client.get("/api/telemetry/nope").status_code == 404


def test_alerts_acknowledge():
    alerts = client.get("/api/alerts").json()
    unacked = next(a for a in alerts if not a["acknowledged"])
    res = client.patch(f"/api/alerts/{unacked['id']}", json={"acknowledged": True})
    assert res.status_code == 200
    assert res.json()["acknowledged"] is True
    assert client.patch("/api/alerts/nope", json={"acknowledged": True}).status_code == 404


def test_unknown_endpoint_returns_json_404():
    assert client.get("/api/does-not-exist").status_code == 404


def test_frontend_index_served():
    res = client.get("/")
    assert res.status_code == 200
    assert "Mission Control" in res.text