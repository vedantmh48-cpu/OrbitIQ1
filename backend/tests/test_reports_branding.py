"""Brand-artwork tests: the SatQuery AI logo is embedded in the HTML/PDF report
exports and degrades to a text-only brand when the asset is unavailable."""
import base64
import re

import pytest

PNG_MAGIC = b"\x89PNG\r\n\x1a\n"
IMAGE_XOBJECT = re.compile(rb"/Subtype\s*/Image")


def _analysis(client, auth_headers):
    """Run one analysis; return ``(result_id, stored result document)``."""
    r = client.post(
        "/api/queries",
        headers=auth_headers,
        json={"text": "Show flood affected areas in Kerala in August 2024 using SAR data"},
    )
    assert r.status_code == 200, r.text
    rid = r.json()["result_id"]
    detail = client.get(f"/api/results/{rid}", headers=auth_headers)
    assert detail.status_code == 200, detail.text
    return rid, detail.json()


def test_brand_html_embeds_png_data_uri():
    from app.services import reporting

    markup = reporting.report_brand_html()
    assert "data:image/png;base64," in markup
    payload = markup.split("data:image/png;base64,", 1)[1].split('"', 1)[0]
    assert base64.b64decode(payload).startswith(PNG_MAGIC)


def test_brand_html_falls_back_to_text(monkeypatch, tmp_path):
    from app.services import reporting

    monkeypatch.setattr(reporting, "LOGO_PATH", tmp_path / "missing.png")
    reporting._logo_data_uri.cache_clear()
    try:
        markup = reporting.report_brand_html()
    finally:
        # never leave a cached "no artwork" result behind for other tests
        reporting._logo_data_uri.cache_clear()
    assert "data:image" not in markup
    assert "SatQuery AI" in markup


def test_html_and_pdf_exports_embed_the_logo(auth_headers, client):
    rid, _ = _analysis(client, auth_headers)

    html = client.get(f"/api/reports/{rid}/html", headers=auth_headers)
    assert html.status_code == 200, html.text
    assert "data:image/png;base64," in html.text

    pdf = client.get(f"/api/reports/{rid}/pdf", headers=auth_headers)
    assert pdf.status_code == 200, pdf.text
    assert pdf.headers["content-type"] == "application/pdf"
    assert pdf.content.startswith(b"%PDF-")
    assert IMAGE_XOBJECT.search(pdf.content)


def test_pdf_still_builds_without_the_asset(monkeypatch, tmp_path, auth_headers, client):
    pytest.importorskip("reportlab")
    from app.services import reporting

    _, result = _analysis(client, auth_headers)
    summary = result.get("summary") or {}
    understanding = result.get("understanding") or {}

    branded = reporting.pdf_bytes(result, summary, understanding)
    assert branded and branded.startswith(b"%PDF-")
    assert IMAGE_XOBJECT.search(branded)

    monkeypatch.setattr(reporting, "LOGO_PATH", tmp_path / "missing.png")
    plain = reporting.pdf_bytes(result, summary, understanding)
    assert plain and plain.startswith(b"%PDF-")
    assert not IMAGE_XOBJECT.search(plain)
