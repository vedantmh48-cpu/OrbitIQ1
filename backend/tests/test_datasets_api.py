"""Tests for the dataset catalogue + provider search routes.

The provider search route hits real external STAC endpoints, so the network
call is faked here; the important contract is that the route's own defaults
never produce a malformed bbox (e.g. ``null`` coordinates).
"""
from app.routers import datasets


class _FakeProvider:
    id = "stac"
    label = "Fake STAC"

    def __init__(self):
        self.calls = []

    def available(self):
        return True

    def search(self, bbox, start, end, data_type, limit=40):
        self.calls.append(bbox)
        return {
            "scenes": [{"id": "s1", "satellite": "Sentinel-2", "date": start[:10], "real": True}],
            "note": "fake",
            "real": True,
        }


def test_search_defaults_never_send_null_bbox(client, auth_headers, monkeypatch):
    """Regression: default bbox must be numeric (a ``null`` min_lng 400s STAC)."""
    provider = _FakeProvider()
    monkeypatch.setattr(datasets, "get_provider", lambda pid, db: provider)

    r = client.get("/api/datasets/search", headers=auth_headers)
    assert r.status_code == 200, r.text
    assert provider.calls, "provider search was never invoked"
    bbox = provider.calls[0]
    assert all(isinstance(v, (int, float)) for v in bbox.values()), bbox
    assert None not in bbox.values()
    assert bbox == {"min_lng": 68.0, "min_lat": 6.0, "max_lng": 98.0, "max_lat": 38.0}


def test_search_respects_explicit_bbox(client, auth_headers, monkeypatch):
    provider = _FakeProvider()
    monkeypatch.setattr(datasets, "get_provider", lambda pid, db: provider)
    r = client.get(
        "/api/datasets/search?min_lng=70&min_lat=8&max_lng=90&max_lat=30",
        headers=auth_headers,
    )
    assert r.status_code == 200, r.text
    bbox = provider.calls[0]
    assert bbox["min_lng"] == 70 and bbox["max_lat"] == 30


def test_search_requires_auth(client):
    assert client.get("/api/datasets/search").status_code in (401, 403)