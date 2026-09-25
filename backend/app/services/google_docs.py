"""Google Docs report integration (optional).

Lets a user push a SatQuery analysis report straight into Google Docs and then
download the PDF of the same analysis from the app.

Two tiers are supported:

1. **Full integration** — when ``GOOGLE_CLIENT_ID`` / ``GOOGLE_CLIENT_SECRET``
   and a matching ``GOOGLE_REDIRECT_URI`` are configured in ``backend/.env``,
   the app runs a real OAuth 2.0 flow (user consent) and creates the report as
   a brand-new Google Document in the user's Drive via the Google Docs API.
2. **Offline tier** — when the above is not configured, the UI still offers a
   Google-Docs-compatible ``.docx`` download that opens directly in
   Google Docs / MS Word, so the feature never breaks.

The service degrades gracefully: every public function returns ``None`` /
``False`` when the Google client libraries or credentials are missing.
"""
from __future__ import annotations

import base64
import json

from ..config import settings
from . import reporting

try:  # optional integration
    from google.oauth2.credentials import Credentials  # noqa: F401
    from google_auth_oauthlib.flow import Flow
    from googleapiclient.discovery import build  # noqa: F401
    _GOOGLE_OK = True
except Exception:  # pragma: no cover
    _GOOGLE_OK = False

SCOPES = [
    "https://www.googleapis.com/auth/documents",
    "https://www.googleapis.com/auth/drive.file",
]


def google_docs_available() -> bool:
    """Whether a real Google Docs upload can run (creds + libs present)."""
    if not _GOOGLE_OK:
        return False
    return bool(
        settings.GOOGLE_CLIENT_ID
        and settings.GOOGLE_CLIENT_SECRET
        and settings.GOOGLE_REDIRECT_URI
    )


def _flow(state: str | None = None) -> Flow | None:
    """Build an OAuth flow instance from the app credentials."""
    if not google_docs_available():
        return None
    client_config = {
        "web": {
            "client_id": settings.GOOGLE_CLIENT_ID,
            "client_secret": settings.GOOGLE_CLIENT_SECRET,
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
            "redirect_uris": [settings.GOOGLE_REDIRECT_URI],
        }
    }
    try:
        return Flow.from_client_config(
            client_config,
            scopes=SCOPES,
            redirect_uri=settings.GOOGLE_REDIRECT_URI,
            state=state,
        )
    except Exception:
        return None


def authorization_url(user_id: str, result_id: str) -> str | None:
    """Build the Google consent URL; ``state`` carries the caller context."""
    if not google_docs_available():
        return None
    state = base64.urlsafe_b64encode(
        json.dumps({"user_id": user_id, "result_id": result_id}).encode()
    ).decode()
    flow = _flow(state=state)
    if flow is None:
        return None
    try:
        url, _ = flow.authorization_url(
            access_type="offline", include_granted_scopes="true", prompt="consent"
        )
        return url
    except Exception:
        return None
def _build_content_requests(result: dict, summary: dict, understanding: dict) -> list[dict]:
    """Turn a result into Google Docs batchUpdate requests (plain, robust)."""
    title = result.get("label") or "SatQuery Analysis"
    sim = bool((result.get("metadata") or {}).get("simulated", True))
    created = (result.get("created_at") or "").replace("T", " ")[:19]
    feature_count = len((result.get("geojson") or {}).get("features", []))
    lines: list[tuple[str | None, str]] = []
    lines.append((None, title))
    lines.append((None, ""))
    lines.append((None, f"Generated {created} UTC · Confidence {result.get('confidence', 0):.0%} · {feature_count} features"))
    lines.append((None, "⚠ DEMO / simulated data — illustrative only." if sim else "Real catalogue data used."))
    if understanding.get("query_text"):
        lines.append(("h_question", "Original query"))
        lines.append((None, understanding["query_text"]))
    lines.append(("h_exec", "Executive summary"))
    lines.append((None, (summary or {}).get("narrative", "Analysis complete.")))
    for h in (summary or {}).get("highlights", []):
        lines.append((None, f"• {h}"))
    lines.append(("h_stats", "Key statistics"))
    for k, v in reporting._stats_rows(result):
        lines.append((None, f"{k}: {v}"))
    checks = (result.get("verification") or {}).get("checks", [])
    if checks:
        lines.append(("h_verify", "Verification report"))
        for c in checks:
            lvl = c.get("level", "")
            lines.append((None, f"{lvl} — {c.get('name','')}: {c.get('detail','')}"))
    lines.append(("h_method", "Methodology"))
    for step in [
        "1. Query understanding into structured slots.",
        "2. AI agent selection (SAR / Optical / Temporal / Fusion).",
        "3. Data retrieval through provider adapters.",
        "4. Spatial & temporal feature extraction over the AOI.",
        "5. Geometric, statistical and provenance verification.",
        "6. Deterministic AI summary.",
    ]:
        lines.append((None, step))

    body_text = "".join(f"{text}\n" for _, text in lines if text is not None)
    requests: list[dict] = [
        {"insertText": {"location": {"index": 1}, "text": body_text}}
    ]
    # Title paragraph style
    first_nl = body_text.find("\n")
    requests.append({
        "updateParagraphStyle": {
            "range": {"startIndex": 1, "endIndex": 1 + (first_nl if first_nl > 0 else 1)},
            "paragraphStyle": {"namedStyleType": "TITLE"},
            "fields": "namedStyleType",
        }
    })
    headings = {
        "h_question": ("HEADING_2", "sel_query"),
        "h_exec": ("HEADING_1", "h_exec"),
        "h_stats": ("HEADING_1", "h_stats"),
        "h_verify": ("HEADING_1", "h_verify"),
        "h_method": ("HEADING_1", "h_method"),
    }
    pos = 1
    for kind, text in lines:
        seg = 0 if text is None else len(text)
        if kind in headings:
            style, hid = headings[kind]
            requests.append({
                "updateParagraphStyle": {
                    "range": {"startIndex": pos, "endIndex": pos + len(text)},
                    "paragraphStyle": {"namedStyleType": style},
                    "fields": "namedStyleType",
                }
            })
            requests.append({
                "updateParagraphStyle": {
                    "range": {"startIndex": pos, "endIndex": pos + len(text)},
                    "paragraphStyle": {"headingId": hid},
                    "fields": "headingId",
                }
            })
        pos += seg + 1
    return requests


def create_google_doc(db, result: dict, creds) -> dict:
    """Create a Google Doc for an analysis and persist the link on the result."""
    service = build("docs", "v1", credentials=creds, cache_discovery=False)
    summary = result.get("summary") or {}
    understanding = result.get("understanding") or {}
    title = f"SatQuery Report — {result.get('label') or 'Analysis'} ({result['id'][:8]})"
    created = service.documents().create(body={"title": title}).execute()
    doc_id = created.get("documentId")
    requests = _build_content_requests(result, summary, understanding)
    if requests:
        service.documents().batchUpdate(documentId=doc_id, body={"requests": requests}).execute()
    url = f"https://docs.google.com/document/d/{doc_id}/edit"
    db.update("results", result["id"], {"google_doc_url": url, "google_doc_id": doc_id})
    return {"document_id": doc_id, "url": url, "title": title}


def creds_from_code(code: str, state: str | None = None):
    """Exchange an OAuth authorization code for credentials."""
    flow = _flow(state=state)
    if flow is None:
        return None
    try:
        flow.fetch_token(code=code)
        return flow.credentials
    except Exception:
        return None


def docx_for_result(result: dict, summary: dict, understanding: dict) -> bytes:
    """Google-Docs-compatible DOCX (offline tier of the feature)."""
    return reporting.docx_bytes(result, summary, understanding)


def pdf_for_result(result: dict, summary: dict, understanding: dict) -> bytes | None:
    """Server-side PDF export for the same analysis."""
    return reporting.pdf_bytes(result, summary, understanding)


def result_google_link(db, result_id: str) -> str | None:
    result = db.find_one("results", {"id": result_id})
    if not result:
        return None
    return result.get("google_doc_url")