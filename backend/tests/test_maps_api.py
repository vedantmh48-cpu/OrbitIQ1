"""Map catalog & dynamic layer API tests."""
from app.map_catalog import (
    CATALOG_BY_KEY,
    DISCRETE_CLASSES,
    MAP_CATALOG,
    _generate_isolines,
    clamp_bbox,
)


def _auth(client):
    r = client.post(
        "/api/auth/register",
        json={"name": "Map Tester", "email": "maps@satquery.ai",
              "password": "Password1", "confirm_password": "Password1"},
    )
    assert r.status_code == 201
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def test_catalog_has_all_five_categories(client, db_env):
    h = _auth(client)
    r = client.get("/api/v1/maps/catalog", headers=h)
    assert r.status_code == 200
    body = r.json()
    assert body["total"] >= 30  # cadastral (analyst tier) is hidden for a `user`
    category_ids = {c["id"] for c in body["categories"]}
    assert category_ids == {"general", "statistical", "environmental", "property", "digital"}

    # Every required cartographic family is present (cadastral is tier-gated and
    # asserted separately below).
    keys = {m["key"] for m in body["maps"]}
    required = {
        "physical", "political", "topographic", "road", "historical",
        "thematic", "choropleth", "isarithmic", "dot_distribution",
        "proportional_symbol", "cartogram", "dasymetric", "flow",
        "cartographic_anamorphose", "heat",
        "climate", "economic_resource", "geological", "biomes_vegetation",
        "bathymetric", "soil_pedological", "epidemiological",
        "aeronautical", "nautical", "zoning_land_use",
        "time_series", "mental_cognitive", "dem_3d",
    }
    assert required <= keys
    assert "cadastral" not in keys  # analyst+ tier

    # Each entry exposes the schema fields spec'd in the table.
    for m in body["maps"]:
        assert m["map_id"] and m["key"] and m["title"] and m["category"]
        assert "is_3d_supported" in m and "is_temporal" in m and "legend" in m


def test_catalog_search_and_filter(client, db_env):
    h = _auth(client)
    r = client.get("/api/v1/maps/catalog?category=digital", headers=h)
    assert r.status_code == 200
    assert {m["key"] for m in r.json()["maps"]} == {"time_series", "mental_cognitive", "dem_3d", "hillshade"}

    r = client.get("/api/v1/maps/catalog?q=choropleth", headers=h)
    assert r.status_code == 200
    assert any("choropleth" in m["key"] or "choropleth" in m["title"].lower() for m in r.json()["maps"])

    r = client.get("/api/v1/maps/catalog?category=bogus", headers=h)
    assert r.status_code == 422


def test_catalog_permission_tier_restricts_cadastral(client, db_env):
    h = _auth(client)  # role = user
    body = client.get("/api/v1/maps/catalog", headers=h).json()
    keys = {m["key"] for m in body["maps"]}
    assert "cadastral" not in keys  # analyst+ tier
    r = client.get("/api/v1/maps/layers/cadastral", headers=h)
    assert r.status_code == 403


def test_layer_config_returns_dynamic_geojson(client, db_env):
    h = _auth(client)
    r = client.get("/api/v1/maps/layers/choropleth?bbox=68,6,98,38", headers=h)
    assert r.status_code == 200
    body = r.json()
    assert body["entry"]["key"] == "choropleth"
    assert body["data"]["type"] == "FeatureCollection"
    assert body["data"]["features"]
    assert all(f["geometry"]["type"] == "Polygon" for f in body["data"]["features"])
    # Server colors each cell so no client-side palette lookup is needed.
    assert all(f["properties"]["color"] for f in body["data"]["features"])

    r = client.get("/api/v1/maps/layers/flow", headers=h)
    assert all(f["geometry"]["type"] == "LineString" for f in r.json()["data"]["features"])

    r = client.get("/api/v1/maps/layers/heat", headers=h)
    assert all(f["geometry"]["type"] == "Point" for f in r.json()["data"]["features"])

    r = client.get("/api/v1/maps/layers/dem_3d", headers=h)
    feats = r.json()["data"]["features"]
    assert feats and all("elevation" in f["properties"] for f in feats)


def test_isarithmic_isolines_via_marching_squares(client, db_env):
    h = _auth(client)
    r = client.get("/api/v1/maps/layers/isarithmic?bbox=68,6,98,38", headers=h)
    assert r.status_code == 200
    data = r.json()["data"]
    assert data["type"] == "FeatureCollection"
    assert len(data["levels"]) > 1
    lines = [f for f in data["features"] if f["geometry"]["type"] == "LineString"]
    assert lines
    assert all(f["properties"]["level"] is not None for f in lines)


def test_generator_utilities(db_env):
    bb = clamp_bbox("70,10,90,30")
    assert len(bb) == 4 and bb[0] == 70.0
    fc = _generate_isolines("bathymetric", bb, [0.2, 0.5, 0.8], k=12)
    assert fc["type"] == "FeatureCollection"
    assert MAP_CATALOG  # seed data loads
    assert set(CATALOG_BY_KEY) == {e["key"] for e in MAP_CATALOG}
    assert "choropleth" in DISCRETE_CLASSES


def test_unknown_layer_404(client, db_env):
    h = _auth(client)
    assert client.get("/api/v1/maps/layers/nope", headers=h).status_code == 404