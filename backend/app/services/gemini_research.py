"""Optional Google Search-grounded research using a server-side Gemini key."""
from __future__ import annotations

import httpx

from ..config import settings


def generate_research(query: str, context: dict) -> dict | None:
    """Return grounded research and source links, or None when unavailable."""
    if not settings.GEMINI_API_KEY:
        return None

    prompt = (
        "Research this satellite/geospatial question using current Google Search. "
        "Write a concise, evidence-based briefing (3-5 factual bullets or short "
        "paragraphs). Prioritize authoritative scientific, government, and data "
        "provider sources. Distinguish measured facts from interpretation; do "
        "not invent satellite observations or claim that this app processed live "
        "imagery. Mention dates when relevant.\n\n"
        f"Question: {query[:1500]}\n"
        f"Parsed context: {context}"
    )
    url = (
        "https://generativelanguage.googleapis.com/v1beta/models/"
        f"{settings.GEMINI_MODEL}:generateContent"
    )
    try:
        response = httpx.post(
            url,
            headers={"x-goog-api-key": settings.GEMINI_API_KEY},
            json={
                "contents": [{"parts": [{"text": prompt}]}],
                "tools": [{"google_search": {}}],
                "generationConfig": {"temperature": 0.2, "maxOutputTokens": 900},
            },
            timeout=settings.GEMINI_TIMEOUT_SECONDS,
        )
        response.raise_for_status()
        payload = response.json()
        candidate = (payload.get("candidates") or [{}])[0]
        parts = (candidate.get("content") or {}).get("parts") or []
        text = "\n".join(p.get("text", "") for p in parts if p.get("text"))
        if not text.strip():
            return None
        metadata = candidate.get("groundingMetadata") or {}
        sources = []
        seen = set()
        for chunk in metadata.get("groundingChunks") or []:
            web = chunk.get("web") or {}
            uri = web.get("uri")
            if uri and uri not in seen:
                seen.add(uri)
                sources.append({"title": web.get("title") or uri, "url": uri})
        return {"text": text.strip(), "sources": sources, "provider": "Google AI Studio"}
    except (httpx.HTTPError, ValueError, KeyError, IndexError):
        # Research enrichment is optional; callers retain the deterministic brief.
        return None
