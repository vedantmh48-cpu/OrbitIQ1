"""Smoke test for the multimodal RS/geospatial assistant upgrades."""
from fastapi.testclient import TestClient

from app.main import app


def main():
    with TestClient(app) as c:
        r = c.post("/api/auth/login", json={"email": "demo@satquery.ai", "password": "Demo@123"})
        if r.status_code != 200:
            r = c.post("/api/auth/register",
                       json={"name": "Demo", "email": "demo@satquery.ai",
                             "password": "Demo@123", "confirm_password": "Demo@123"})
        h = {"Authorization": f"Bearer {r.json()['access_token']}"}

        print("=== 1. Geospatial capabilities ===")
        cap = c.get("/api/geospatial/capabilities", headers=h)
        print("capabilities:", cap.status_code, cap.json())

        print("\n=== 2. Index definitions ===")
        idx = c.get("/api/geospatial/indexes", headers=h).json()["indexes"]
        print("indexes:", [i["id"] for i in idx])

        print("\n=== 3. GeoTIFF demo parse ===")
        gp = c.get("/api/geospatial/demo/parse", headers=h)
        g = gp.json()
        print("parse status:", gp.status_code, "| EPSG:", g["crs"]["epsg"],
              "| bounds:", g["bounds"], "| dims:", g["dimensions"])
        assert g["crs"]["epsg"] == 4326
        assert g["footprint_wkt"]

        print("\n=== 4. NDVI spectral-index computation ===")
        nd = c.post("/api/geospatial/indexes/run", headers=h,
                    params={"index": "ndvi", "location": "Punjab"}).json()
        print("index:", nd["requested_index"], "| mean:", nd["stats"]["mean_index"],
              "| positive cells:", nd["stats"]["positive_cells"],
              "| area:", nd["stats"]["positive_area_km2"], "km2")

        print("\n=== 5. Full pipeline NDVI query (execution trace) ===")
        q = c.post("/api/queries", headers=h,
                   json={"text": "Compute NDVI vegetation health for Punjab using Sentinel-2 optical data"})
        body = q.json()
        print("query:", q.status_code, "| result:", body.get("result_id"))
        res = c.get(f"/api/results/{body['result_id']}", headers=h).json()
        trace = res.get("execution_trace") or {}
        print("op:", res["op"], "| label:", res.get("label"))
        print("modality:", (res.get("modality") or {}).get("label"))
        print("trace tools:", trace.get("tools"))
        print("trace steps:", len(trace.get("steps", [])))
        assert res["op"] in ("ndvi", "classification", "time-series")
        assert trace.get("steps"), "execution_trace missing on result"
        assert res.get("modality"), "modality missing on result"
        # Verification now includes spectral-bounds check
        print("verification checks:", [cch["name"] for cch in (res.get("verification") or {}).get("checks", [])])

        print("\n=== 6. Full pipeline SAR-backscatter query ===")
        q2 = c.post("/api/queries", headers=h,
                    json={"text": "Analyse SAR backscatter intensity for the Kerala coast using Sentinel-1 radar data"})
        res2 = c.get(f"/api/results/{q2.json()['result_id']}", headers=h).json()
        print("op:", res2["op"], "| mean sigma-dB:", (res2.get("stats") or {}).get("mean_sigma_db"),
              "| modality:", (res2.get("modality") or {}).get("id"))

        print("\n=== 7. Upload GeoTIFF parse ===")
        from app.services.geotools import make_demo_geotiff
        data = make_demo_geotiff(epsg=3857, width=48, height=48, min_lng=0, min_lat=0, max_lng=1, max_lat=1)
        up = c.post("/api/geospatial/parse", headers=h,
                    files={"file": ("demo-3857.tif", data, "image/tiff")})
        u = up.json()
        print("upload parse:", up.status_code, "| EPSG:", u["crs"]["epsg"],
              "| model:", u["crs"]["model_type"], "| bounds:", u.get("bounds"))

        print("\nALL MULTIMODAL ASSISTANT CHECKS OK")


if __name__ == "__main__":
    main()