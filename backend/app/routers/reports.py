"""Report export routes: GeoJSON / CSV / Markdown / HTML / PDF / DOCX and the
optional Google Docs integration (create a Google Doc from the analysis)."""
from __future__ import annotations

import base64
import json

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import PlainTextResponse, RedirectResponse, Response

from ..config import settings
from ..deps import get_current_user
from ..middleware import logger
from ..services import google_docs, reporting
from ..services.summarizer import build_summary
from ..storage import get_db

router = APIRouter(prefix="/api/reports", tags=["reports"])


def _load(result_id: str, user: dict, db) -> dict:
    result = db.find_one("results", {"id": result_id})
    if not result:
        raise HTTPException(status_code=404, detail="Result not found.")
    if result["user_id"] != user["id"] and user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Not your result.")
    return result


def _summary(result: dict) -> dict:
    return result.get("summary") or build_summary(result, result.get("understanding", {}))


def _understanding(result: dict) -> dict:
    return result.get("understanding", {}) or {}


def _dataset(result: dict, db) -> dict | None:
    plan = result.get("agent_plan") or {}
    used = plan.get("datasets_used") or []
    if used:
        return db.find_one("datasets", {"id": used[0]})
    return None


@router.get("/{result_id}/geojson")
def export_geojson(result_id: str, user: dict = Depends(get_current_user), db=Depends(get_db)):
    result = _load(result_id, user, db)
    return Response(
        reporting.geojson_bytes(result),
        media_type="application/geo+json",
        headers={"Content-Disposition": f'attachment; filename="satquery-{result_id[:8]}.geojson"'},
    )


@router.get("/{result_id}/csv")
def export_csv(result_id: str, user: dict = Depends(get_current_user), db=Depends(get_db)):
    result = _load(result_id, user, db)
    return Response(
        reporting.csv_bytes(result),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="satquery-{result_id[:8]}.csv"'},
    )


@router.get("/{result_id}/markdown")
def export_markdown(result_id: str, user: dict = Depends(get_current_user), db=Depends(get_db)):
    result = _load(result_id, user, db)
    md = reporting.markdown_report(
        result, _summary(result), _understanding(result), _dataset(result, db)
    )
    return PlainTextResponse(md, media_type="text/markdown")


@router.get("/{result_id}/html")
def export_html(result_id: str, user: dict = Depends(get_current_user), db=Depends(get_db)):
    result = _load(result_id, user, db)
    html = reporting.html_report(result, _summary(result), _understanding(result))
    return Response(html, media_type="text/html")


@router.get("/{result_id}/pdf")
def export_pdf(result_id: str, user: dict = Depends(get_current_user), db=Depends(get_db)):
    result = _load(result_id, user, db)
    pdf = reporting.pdf_bytes(result, _summary(result), _understanding(result))
    if pdf is None:
        # Graceful fallback: a printable HTML document.
        html = reporting.html_report(result, _summary(result), _understanding(result))
        return Response(
            html,
            media_type="text/html",
            headers={"Content-Disposition": f'attachment; filename="satquery-{result_id[:8]}-print.html"',
                     "X-Fallback-Reason": "reportlab not installed; printed HTML provided"},
        )
    return Response(
        pdf,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="satquery-{result_id[:8]}.pdf"'},
    )


@router.get("/{result_id}/docx")
def export_docx(result_id: str, user: dict = Depends(get_current_user), db=Depends(get_db)):
    """Download a Google-Docs / MS Word compatible .docx report."""
    result = _load(result_id, user, db)
    docx = reporting.docx_bytes(result, _summary(result), _understanding(result))
    return Response(
        docx,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers={"Content-Disposition": f'attachment; filename="satquery-{result_id[:8]}.docx"'},
    )
# ---------------------------------------------------------------------------
# Google Docs integration
# ---------------------------------------------------------------------------


@router.get("/{result_id}/google/status")
def google_doc_status(
    result_id: str,
    user: dict = Depends(get_current_user),
    db=Depends(get_db),
):
    """Report whether the Google integration is configured and if a doc exists."""
    result = _load(result_id, user, db)
    return {
        "available": google_docs.google_docs_available(),
        "google_doc_url": result.get("google_doc_url"),
        "docx_available": True,
        "pdf_available": True,
    }


@router.post("/{result_id}/google-doc")
def create_google_doc_start(
    result_id: str,
    user: dict = Depends(get_current_user),
    db=Depends(get_db),
):
    """Start the Google Docs flow.

    * When Google OAuth is configured → returns the consent URL to redirect to.
    * Otherwise → returns ``requires_setup`` so the UI offers the .docx instead.
    """
    _load(result_id, user, db)
    url = google_docs.authorization_url(user["id"], result_id)
    if not url:
        return {
            "requires_setup": True,
            "message": (
                "Google Docs publishing is not configured on this deployment. "
                "Use the .docx download and open it in Google Docs directly."
            ),
            "docx_endpoint": f"/api/reports/{result_id}/docx",
        }
    return {"authorization_url": url}


@router.get("/google/callback")
def google_callback(
    code: str = Query(""),
    state: str = Query(""),
    error: str = Query(""),
    db=Depends(get_db),
):
    """OAuth callback: exchange the code, create the Google Doc, bounce back."""
    frontend = settings.FRONTEND_ORIGIN
    if error:
        return RedirectResponse(f"{frontend}/results/?docs=failed")
    redirect_to = f"{frontend}/results/"
    try:
        payload = json.loads(base64.urlsafe_b64decode(state.encode()).decode())
        result_id = payload.get("result_id")
        user_id = payload.get("user_id")
        redirect_to = f"{frontend}/results/{result_id}?docs=success"
        if not result_id or not user_id:
            return RedirectResponse(f"{frontend}/results/?docs=failed")
        creds = google_docs.creds_from_code(code, state=state)
        if creds is None:
            return RedirectResponse(f"{frontend}/results/{result_id}?docs=failed")
        result = db.find_one("results", {"id": result_id, "user_id": user_id})
        if not result:
            return RedirectResponse(f"{frontend}/results/?docs=failed")
        out = google_docs.create_google_doc(db, result, creds)
        logger.info("Google Doc created for result %s: %s", result_id[:8], out["url"])
        return RedirectResponse(f"{redirect_to}&url={out['url']}")
    except Exception as exc:
        logger.warning("Google Docs callback failed: %s", exc)
        return RedirectResponse(f"{frontend}/results/?docs=failed")