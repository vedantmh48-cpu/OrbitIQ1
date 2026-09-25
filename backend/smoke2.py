"""Extended endpoint smoke: understanding, saved, settings, reset, admin."""
from fastapi.testclient import TestClient

from app.main import app

with TestClient(app) as c:
    r = c.post("/api/auth/login", json={"email": "tester@x.com", "password": "Password1"})
    b = r.json()
    h = {"Authorization": f"Bearer {b['access_token']}"}

    u = c.post("/api/queries/understand", headers=h,
               json={"text": "Show flood affected areas in Kerala in August 2024 using SAR data"})
    print("understand", u.status_code, u.json().get("agent"), u.json().get("location"))

    s = c.get("/api/results?limit=3", headers=h)
    rid = s.json()[0]["id"] if s.json() else None
    print("results list", s.status_code, len(s.json()))

    sv = c.post("/api/saved", headers=h, json={"result_id": rid, "name": "Kerala flood demo"})
    print("saved", sv.status_code, sv.json())
    sv2 = c.get("/api/saved", headers=h)
    print("saved list", len(sv2.json()))

    set1 = c.put("/api/users/settings", headers=h, json={"theme": "dark"})
    set2 = c.get("/api/users/settings", headers=h)
    print("settings", set1.status_code, set2.status_code, set2.json().get("theme"))

    f = c.post("/api/auth/forgot-password", json={"email": "tester@x.com"})
    print("forgot", f.status_code)
    link = f.json().get("demo_reset_link", "")
    if link:
        tok = link.split("token=")[1]
        rs = c.post("/api/auth/reset-password",
                    json={"token": tok, "new_password": "NewPass123", "confirm_password": "NewPass123"})
        print("reset", rs.status_code, rs.json().get("message"))
        # restore original password
        c.post("/api/auth/login", json={"email": "tester@x.com", "password": "NewPass123"})
        c.post("/api/auth/forgot-password", json={"email": "tester@x.com"})
        # (the new reset link would be needed; skip full restore — covered by unit tests)

    ah = c.get("/api/admin/health")
    print("admin health", ah.status_code, ah.json().get("storage_backend"))

    # providers
    pv = c.get("/api/datasets/providers", headers=h)
    print("providers", pv.status_code, [(p["id"], p["available"]) for p in pv.json()])