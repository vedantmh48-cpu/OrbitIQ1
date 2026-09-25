"""Quick API smoke test (no pytest needed): python smoke_test.py"""
import time

from fastapi.testclient import TestClient

from app.main import app


def auth_or_register(c, email="tester@x.com", password="Password1"):
    r = c.post("/api/auth/login", json={"email": email, "password": password})
    if r.status_code == 200:
        return r.json()
    r = c.post(
        "/api/auth/register",
        json={
            "name": "Tester",
            "email": email,
            "password": password,
            "confirm_password": password,
        },
    )
    print("register", r.status_code)
    return r.json()


def main():
    t0 = time.time()
    with TestClient(app) as c:
        r = c.get("/api/health")
        print("health", r.status_code, r.json())

        b = auth_or_register(c)
        h = {"Authorization": f"Bearer {b['access_token']}"}
        r = c.get("/api/users/me", headers=h)
        print("me", r.status_code, r.json().get("email"))

        r = c.get("/api/datasets", headers=h)
        print("datasets", r.status_code, len(r.json()))

        r = c.post(
            "/api/queries",
            headers=h,
            json={"text": "Show flood affected areas in Kerala in August 2024 using SAR data"},
        )
        print("query", r.status_code, r.json())
        rid = r.json().get("result_id")

        r = c.get(f"/api/results/{rid}", headers=h)
        print("result", r.status_code)
        j = r.json()
        print("op:", j.get("op"), "conf:", j.get("confidence"),
              "area:", (j.get("stats") or {}).get("affected_area_km2"))
        print("summary:", (j.get("summary") or {}).get("narrative", "")[:140])

        r = c.post(
            "/api/queries",
            headers=h,
            json={"text": "Compare crop NDVI trend in Punjab over the last 3 months"},
        )
        print("query2", r.status_code, r.json())

        r = c.get(f"/api/reports/{rid}/geojson", headers=h)
        print("geojson download", r.status_code, r.headers.get("content-type"))
        r = c.get(f"/api/reports/{rid}/csv", headers=h)
        print("csv download", r.status_code, r.headers.get("content-type"))
        r = c.get(f"/api/reports/{rid}/markdown", headers=h)
        print("markdown download", r.status_code, len(r.text))

        r = c.post(
            "/api/queries",
            headers=h,
            json={"text": "Detect vessels along the Kochi coast using object detection"},
        )
        print("query3 (objects)", r.status_code, (r.json().get("status") if r.status_code == 200 else r.json()))
    print("elapsed", round(time.time() - t0, 1), "s")


if __name__ == "__main__":
    main()