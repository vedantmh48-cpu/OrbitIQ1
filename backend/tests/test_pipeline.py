"""End-to-end pipeline tests: understanding, query, results, reports, settings."""
import json


def test_understand_endpoint(auth_headers, client):
    r = client.post(
        "/api/queries/understand",
        headers=auth_headers,
        json={"text": "Show flood affected areas in Kerala in August 2024 using SAR data"},
    )
    assert r.status_code == 200
    u = r.json()
    assert u["location"] == "Kerala"
    assert u["date_start"] == "2024-08-01"
    assert u["date_end"] == "2024-08-31"
    assert u["phenomenon"] == "flood"
    assert u["data_type"] == "SAR"
    assert u["agent"] == "sar"


def test_full_pipeline(auth_headers, client):
    r = client.post(
        "/api/queries",
        headers=auth_headers,
        json={"text": "Show flood affected areas in Kerala in August 2024 using SAR data"},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == "completed"
    result_id = body["result_id"]
    assert result_id

    detail = client.get(f"/api/results/{result_id}", headers=auth_headers)
    assert detail.status_code == 200
    res = detail.json()
    assert res["op"] == "flood-mapping"
    assert res["stats"]["affected_area_km2"] > 0
    assert res["geojson"]["features"]
    assert res["verification"]["status"] in ("passed", "failed")
    assert res["summary"]["narrative"]
    assert res["simulated"] is True  # provenance transparency


def test_time_series_pipeline(auth_headers, client):
    r = client.post("/api/queries", headers=auth_headers,
                    json={"text": "Analyse the urban expansion trend in Bengaluru from 2015 to 2024"})
    assert r.status_code == 200, r.text
    rid = r.json()["result_id"]
    res = client.get(f"/api/results/{rid}", headers=auth_headers).json()
    assert res["op"] in ("time-series", "change-detection", "classification")
    assert res["charts"].get("timeseries") is not None


def test_dataset_catalog_and_providers(auth_headers, client):
    ds = client.get("/api/datasets", headers=auth_headers)
    assert ds.status_code == 200
    assert len(ds.json()) >= 11
    pv = client.get("/api/datasets/providers", headers=auth_headers).json()
    ids = {p["id"] for p in pv}
    assert {"demo", "stac", "sentinel", "landsat"} <= ids


def test_reports_downloads(auth_headers, client):
    r = client.post("/api/queries", headers=auth_headers,
                    json={"text": "Show flood affected areas in Kerala in August 2024 using SAR data"})
    rid = r.json()["result_id"]
    for fmt in ("geojson", "csv", "markdown", "html", "pdf"):
        rr = client.get(f"/api/reports/{rid}/{fmt}", headers=auth_headers)
        assert rr.status_code == 200, f"{fmt} failed"


def test_saved_analyses(auth_headers, client):
    rid = _latest_result_id(auth_headers, client)
    sv = client.post("/api/saved", headers=auth_headers,
                     json={"result_id": rid, "name": "Pinned", "notes": "for review"})
    assert sv.status_code == 200
    lst = client.get("/api/saved", headers=auth_headers)
    assert any(s["name"] == "Pinned" for s in lst.json())


def test_settings_roundtrip_and_protection(auth_headers, client):
    r = client.put("/api/users/settings", headers=auth_headers, json={"theme": "light"})
    assert r.status_code == 200
    assert client.get("/api/users/settings", headers=auth_headers).json()["theme"] == "light"

    # orphan results can't be read by another user
    me = client.get("/api/users/me", headers=auth_headers).json()
    other = client.post("/api/auth/register", json={
        "name": "Other", "email": "other@test.ai",
        "password": "Password1", "confirm_password": "Password1"})
    other_h = {"Authorization": f"Bearer {other.json()['access_token']}"}
    rid = _latest_result_id(auth_headers, client)
    denied = client.get(f"/api/results/{rid}", headers=other_h)
    assert denied.status_code == 403


def _latest_result_id(auth_headers, client):
    r = client.post("/api/queries", headers=auth_headers,
                    json={"text": "Classify land cover in Punjab and find the dominant crop class"})
    return r.json()["result_id"]


def test_history_records_queries(auth_headers, client):
    client.post("/api/queries", headers=auth_headers,
                json={"text": "Show flood affected areas in Kerala in August 2024 using SAR data"})
    hist = client.get("/api/queries/history", headers=auth_headers)
    assert hist.status_code == 200
    assert len(hist.json()) >= 1


def test_rate_limits_public_health():
    from fastapi.testclient import TestClient
    from app.main import app

    with TestClient(app) as c:
        assert c.get("/api/health").status_code == 200
        assert c.get("/api/about").status_code == 200