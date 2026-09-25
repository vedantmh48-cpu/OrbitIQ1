"""CORS configuration: env parsing, normalization and preflight behaviour.

The production symptom being guarded against is an ``OPTIONS`` preflight that
Starlette answers with ``400 Disallowed CORS origin`` (the browser then reports
"CORS error / Failed to fetch") while plain ``GET`` calls keep working.
"""
from __future__ import annotations

import re

import pytest
from fastapi.middleware.cors import CORSMiddleware
from starlette.applications import Starlette
from starlette.responses import PlainTextResponse
from starlette.routing import Route

from app.config import (
    DEV_FRONTEND_ORIGINS,
    Settings,
    normalize_origin,
    split_origin_list,
)

VERCEL_ORIGIN = "https://orbit-iq-lovat.vercel.app"
PREVIEW_ORIGIN = "https://orbit-iq-lovat-git-main-user.vercel.app"

PREFLIGHT_HEADERS = {
    "Access-Control-Request-Method": "POST",
    "Access-Control-Request-Headers": "content-type",
}


def _settings(
    monkeypatch,
    *,
    frontend=VERCEL_ORIGIN,
    environment="production",
    cors=None,
    regex=None,
) -> Settings:
    """A ``Settings`` instance with controlled origin/env values."""
    instance = Settings()
    instance.FRONTEND_ORIGIN = frontend  # type: ignore[misc]
    instance.ENVIRONMENT = environment  # type: ignore[misc]
    for name, value in (("CORS_ORIGINS", cors), ("CORS_ORIGIN_REGEX", regex)):
        if value is None:
            monkeypatch.delenv(name, raising=False)
        else:
            monkeypatch.setenv(name, value)
    return instance


# ---------------------------------------------------------------------------
# Parsing / normalization
# ---------------------------------------------------------------------------


def test_single_url_is_parsed():
    assert split_origin_list(VERCEL_ORIGIN) == [VERCEL_ORIGIN]


def test_comma_separated_values_are_parsed():
    raw = f"{VERCEL_ORIGIN}, https://orbitiq.example.com"
    assert split_origin_list(raw) == [VERCEL_ORIGIN, "https://orbitiq.example.com"]


def test_semicolon_and_whitespace_separated_values_are_parsed():
    raw = f"{VERCEL_ORIGIN};  https://a.example.com\thttps://b.example.com"
    assert split_origin_list(raw) == [
        VERCEL_ORIGIN,
        "https://a.example.com",
        "https://b.example.com",
    ]


def test_json_array_is_parsed():
    raw = f'["{VERCEL_ORIGIN}", "https://orbitiq.example.com"]'
    assert split_origin_list(raw) == [VERCEL_ORIGIN, "https://orbitiq.example.com"]


def test_normalize_origin_strips_quotes_whitespace_and_trailing_slash():
    assert normalize_origin(" https://orbit-iq-lovat.vercel.app/ ") == VERCEL_ORIGIN
    assert normalize_origin(f'"{VERCEL_ORIGIN}/"') == VERCEL_ORIGIN


# ---------------------------------------------------------------------------
# Allow-list resolution
# ---------------------------------------------------------------------------


def test_production_allows_exactly_the_configured_origins(monkeypatch):
    s = _settings(monkeypatch, cors=VERCEL_ORIGIN)
    assert s.cors_origins == [VERCEL_ORIGIN]
    assert "*" not in s.cors_origins
    # FRONTEND_ORIGIN and CORS_ORIGINS are both honoured (deduplicated).
    assert s.configured_cors_origins == [VERCEL_ORIGIN]


def test_production_accepts_single_url_with_trailing_slash(monkeypatch):
    s = _settings(monkeypatch, cors=f"{VERCEL_ORIGIN}/")
    assert s.cors_origins == [VERCEL_ORIGIN]


def test_production_merges_multiple_origins(monkeypatch):
    s = _settings(monkeypatch, cors="https://a.example.com,https://b.example.com")
    assert s.cors_origins == [
        "https://a.example.com",
        "https://b.example.com",
        VERCEL_ORIGIN,
    ]


def test_frontend_origin_accepts_a_list_too(monkeypatch):
    s = _settings(
        monkeypatch,
        frontend=f"{VERCEL_ORIGIN}, https://orbitiq.example.com",
        cors="",
    )
    assert s.cors_origins == [VERCEL_ORIGIN, "https://orbitiq.example.com"]



def test_development_keeps_localhost_support(monkeypatch):
    s = _settings(
        monkeypatch,
        frontend="http://localhost:5173",
        environment="development",
        cors="",
    )
    assert s.cors_origins == sorted(DEV_FRONTEND_ORIGINS)
    assert "http://127.0.0.1:5173" in s.cors_origins


def test_production_drops_loopback_dev_origins(monkeypatch):
    s = _settings(monkeypatch, cors=VERCEL_ORIGIN)
    assert "http://localhost:5173" not in s.cors_origins
    assert "http://127.0.0.1:5173" not in s.cors_origins


# ---------------------------------------------------------------------------
# Vercel preview deployments
# ---------------------------------------------------------------------------


def test_preview_regex_is_derived_from_configured_vercel_origin(monkeypatch):
    s = _settings(monkeypatch, cors=VERCEL_ORIGIN)
    assert s.cors_origin_regex is not None
    assert re.fullmatch(s.cors_origin_regex, VERCEL_ORIGIN)
    assert re.fullmatch(s.cors_origin_regex, PREVIEW_ORIGIN)
    assert not re.fullmatch(s.cors_origin_regex, "https://evil.example.com")
    assert not re.fullmatch(
        s.cors_origin_regex, "https://orbit-iq-lovat.vercel.app.evil.com"
    )


def test_preview_regex_absent_without_a_vercel_origin(monkeypatch):
    s = _settings(monkeypatch, frontend="https://app.example.com", cors="")
    assert s.cors_origin_regex is None


def test_preview_regex_can_be_overridden(monkeypatch):
    s = _settings(monkeypatch, cors=VERCEL_ORIGIN, regex=r"^https://preview\.example$")
    assert s.cors_origin_regex == r"^https://preview\.example$"



# ---------------------------------------------------------------------------
# Wiring + real preflight requests (same config the app uses)
# ---------------------------------------------------------------------------


def _middleware_app(s: Settings):
    """Build a Starlette app wired exactly like ``app.main``."""
    app = Starlette(
        routes=[
            Route(
                "/api/v1/auth/login",
                lambda request: PlainTextResponse("ok"),
                methods=["POST"],
            )
        ]
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=s.cors_origins,
        allow_origin_regex=s.cors_origin_regex,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    return app


def test_main_app_wires_settings_into_cors_middleware():
    from app.config import settings
    from app.main import app

    cors = next(m for m in app.user_middleware if m.cls is CORSMiddleware)
    assert cors.kwargs["allow_origins"] == settings.cors_origins
    assert cors.kwargs["allow_origin_regex"] == settings.cors_origin_regex
    assert cors.kwargs["allow_credentials"] is True
    assert cors.kwargs["allow_methods"] == ["*"]
    assert cors.kwargs["allow_headers"] == ["*"]
    assert "*" not in cors.kwargs["allow_origins"]


def test_preflight_for_production_origin_is_not_rejected(monkeypatch):
    from fastapi.testclient import TestClient

    s = _settings(monkeypatch, cors=VERCEL_ORIGIN)
    client = TestClient(_middleware_app(s))
    r = client.options(
        "/api/v1/auth/login", headers={"Origin": VERCEL_ORIGIN, **PREFLIGHT_HEADERS}
    )
    assert r.status_code == 200, r.text
    assert r.headers["access-control-allow-origin"] == VERCEL_ORIGIN
    assert r.headers["access-control-allow-credentials"] == "true"


def test_preflight_for_vercel_preview_origin_is_allowed(monkeypatch):
    from fastapi.testclient import TestClient

    s = _settings(monkeypatch, cors=VERCEL_ORIGIN)
    client = TestClient(_middleware_app(s))
    r = client.options(
        "/api/v1/auth/login", headers={"Origin": PREVIEW_ORIGIN, **PREFLIGHT_HEADERS}
    )
    assert r.status_code == 200, r.text
    assert r.headers["access-control-allow-origin"] == PREVIEW_ORIGIN


def test_preflight_for_unknown_origin_is_rejected(monkeypatch):
    from fastapi.testclient import TestClient

    s = _settings(monkeypatch, cors=VERCEL_ORIGIN)
    client = TestClient(_middleware_app(s))
    r = client.options(
        "/api/v1/auth/login",
        headers={"Origin": "https://evil.example.com", **PREFLIGHT_HEADERS},
    )
    assert r.status_code == 400


def test_app_allows_every_origin_it_advertises(client):
    """The running app must answer every origin its own configuration allows.

    Ambient env values (``ENVIRONMENT`` / ``FRONTEND_ORIGIN`` / ``CORS_ORIGINS``)
    are resolved at import time, so the expectation is derived from the app's
    own settings instead of assuming a development default.
    """
    from app.config import settings

    assert settings.cors_origins, "no CORS origin configured"
    for origin in settings.cors_origins:
        r = client.options(
            "/api/v1/auth/login", headers={"Origin": origin, **PREFLIGHT_HEADERS}
        )
        assert r.status_code == 200, r.text
        assert r.headers["access-control-allow-origin"] == origin
        assert r.headers["access-control-allow-credentials"] == "true"


def test_app_rejects_an_unconfigured_origin(client):
    from app.config import settings

    origin = "https://not-configured.example.com"
    assert origin not in settings.cors_origins
    r = client.options(
        "/api/v1/auth/login", headers={"Origin": origin, **PREFLIGHT_HEADERS}
    )
    assert r.status_code == 400


def test_development_allow_list_covers_both_vite_hostnames(monkeypatch):
    """Development resolution (no overrides) must cover localhost + loopback."""
    monkeypatch.delenv("CORS_ORIGINS", raising=False)
    monkeypatch.delenv("CORS_ORIGIN_REGEX", raising=False)
    from app.config import Settings

    s = Settings()
    s.ENVIRONMENT = "development"
    s.FRONTEND_ORIGIN = "http://localhost:5173"
    assert s.is_production() is False
    assert s.cors_origins == sorted(DEV_FRONTEND_ORIGINS)
    assert "http://127.0.0.1:5173" in s.cors_origins

