"""Comprehensive smoke test for the new report endpoints (PDF/DOCX/Google)."""
import io
import zipfile

from fastapi.testclient import TestClient

from app.main import app


def main():
    with TestClient(app) as c:
        r = c.post("/api/auth/login", json={"email": "demo@satquery.ai", "password": "Demo@123"})
        if r.status_code != 200:
            r = c.post(
                "/api/auth/register",
                json={"name": "Demo", "email": "demo@satquery.ai",
                      "password": "Demo@123", "confirm_password": "Demo@123"},
            )
        auth = {"Authorization": f"Bearer {r.json()['access_token']}"}

        q = c.post(
            "/api/queries",
            headers=auth,
            json={"text": "Show flood affected areas in Kerala in August 2024 using SAR data"},
        )
        assert q.status_code == 200, q.text
        rid = q.json()["result_id"]
        print("run query ->", q.status_code, "result", rid)

        # PDF (server)
        pdf = c.get(f"/api/reports/{rid}/pdf", headers=auth)
        print("pdf ->", pdf.status_code, pdf.headers.get("content-type"), len(pdf.content), "bytes")
        assert pdf.content[:4] == b"%PDF", "PDF magic wrong"

        # DOCX
        doc = c.get(f"/api/reports/{rid}/docx", headers=auth)
        print("docx ->", doc.status_code, doc.headers.get("content-type"), len(doc.content), "bytes")
        zf = zipfile.ZipFile(io.BytesIO(doc.content))
        names = zf.namelist()
        print("docx members:", names)
        assert "word/document.xml" in names and "[Content_Types].xml" in names
        xml = zf.read("word/document.xml").decode("utf-8")
        assert "Executive summary" in xml and "Key statistics" in xml
        assert zf.testzip() is None, "corrupt zip"

        # Google status + start flow (unconfigured -> requires setup)
        gs = c.get(f"/api/reports/{rid}/google/status", headers=auth)
        print("google/status ->", gs.status_code, gs.json())
        gd = c.post(f"/api/reports/{rid}/google-doc", headers=auth)
        print("google-doc ->", gd.status_code, gd.json())
        assert gd.json().get("requires_setup") is True

        # HTML / MD / CSV / GeoJSON
        for fmt in ("html", "markdown", "csv", "geojson"):
            rr = c.get(f"/api/reports/{rid}/{fmt}", headers=auth)
            print(fmt, "->", rr.status_code, len(rr.content), "bytes")
            assert rr.status_code == 200

        # result bundle now exposes google_doc_url
        bundle = c.get(f"/api/results/{rid}", headers=auth).json()
        assert "google_doc_url" in bundle
        print("ALL NEW REPORT ENDPOINTS OK")


if __name__ == "__main__":
    main()