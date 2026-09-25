"""Live check against the running SatQuery backend (127.0.0.1:8000)."""
import httpx

BASE = "http://127.0.0.1:8000"


def main():
    with httpx.Client(timeout=20) as c:
        r = c.post(
            f"{BASE}/api/auth/register",
            json={
                "name": "LiveCheck",
                "email": "livecheck@satquery.ai",
                "password": "Password1",
                "confirm_password": "Password1",
            },
        )
        print("register", r.status_code)
        token = r.json().get("access_token", "")
        if not token:
            token = c.post(
                f"{BASE}/api/auth/login",
                json={"email": "livecheck@satquery.ai", "password": "Password1"},
            ).json().get("access_token", "")
        h = {"Authorization": f"Bearer {token}"}

        r = c.get(f"{BASE}/api/v1/maps/catalog", headers=h)
        print("maps/catalog", r.status_code, "total=", r.json().get("total"))
        cats = r.json().get("categories", [])
        print("categories:", [f"{x['id']}:{x['count']}" for x in cats])

        for key, bbox in [
            ("isarithmic", "68,6,98,38"),
            ("flow", None),
            ("choropleth", None),
            ("dem_3d", None),
        ]:
            url = f"{BASE}/api/v1/maps/layers/{key}"
            if bbox:
                url += f"?bbox={bbox}"
            rr = c.get(url, headers=h)
            feats = rr.json().get("data", {}).get("features", []) if rr.status_code == 200 else []
            print(f"layers/{key}", rr.status_code, "features=", len(feats))

        r = c.get(f"{BASE}/api/v1/maps/layers/cadastral", headers=h)
        print("layers/cadastral (user tier)", r.status_code)

        r = c.get(f"{BASE}/api/health")
        print("health", r.status_code, r.json().get("storage", {}).get("backend"))


if __name__ == "__main__":
    main()