"""Application configuration loaded from environment / .env file.

All secrets are overridable through environment variables. The repository ships
with a .env.example; a local .env is optional (sensible dev defaults are used).
"""
from __future__ import annotations

import os
from pathlib import Path

try:  # python-dotenv is optional at import time
    from dotenv import load_dotenv

    _ENV_FILE = Path(__file__).resolve().parent.parent / ".env"
    if _ENV_FILE.exists():
        load_dotenv(_ENV_FILE, override=False)
except Exception:  # pragma: no cover
    pass


def _env_flag(name: str, default: bool) -> bool:
    """Read a boolean environment flag (``1/true/yes/on`` -> True)."""
    raw = os.getenv(name)
    if raw is None or not str(raw).strip():
        return default
    return str(raw).strip().lower() in ("1", "true", "yes", "on")


def normalize_app_password(raw: str) -> str:
    """Google App Passwords are shown as ``abcd efgh ijkl mnop`` - the spaces
    are cosmetic, so they are stripped before use."""
    return (raw or "").replace(" ", "").replace("\u00a0", "").strip()


class Settings:
    """Centralised, typed access to every environment setting."""

    APP_NAME = os.getenv("APP_NAME", "SatQuery AI")
    VERSION = "1.0.0"
    ENVIRONMENT = os.getenv("ENVIRONMENT", "development")

    # --- Backend ---
    HOST = os.getenv("HOST", "0.0.0.0")
    PORT = int(os.getenv("PORT", "").strip() or "8000")
    FRONTEND_ORIGIN = os.getenv("FRONTEND_ORIGIN", "http://localhost:5173")

    # --- MongoDB ---
    MONGO_URI = os.getenv("MONGO_URI", "mongodb://localhost:27017")
    MONGO_DB = os.getenv("MONGO_DB", "satquery_dev")
    # "auto" -> try MongoDB, fall back to local JSON store if unavailable.
    # "off"  -> always use the local JSON store. "on" -> require MongoDB.
    DB_MODE = os.getenv("DB_MODE", "auto").lower()

    # --- Auth store / sessions (v1 auth vertical slice) ---
    # "auto"     -> PostgreSQL (PostGIS) when reachable, else legacy store.
    # "postgres" -> require PostgreSQL (fail fast if unreachable).
    # "compat"   -> always use the legacy document store (Mongo / local JSON).
    AUTH_STORE = os.getenv("AUTH_STORE", "auto").lower()
    POSTGRES_DSN = os.getenv(
        "POSTGRES_DSN", "postgresql://postgres:postgres@localhost:5432/satquery"
    )
    REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
    REDIS_ENABLED = os.getenv("REDIS_ENABLED", "auto").lower()

    # OTP / verification codes
    AUTH_OTP_TTL_MINUTES = int(os.getenv("AUTH_OTP_TTL_MINUTES", "10"))
    # Pending password-change payloads expire after this window.
    AUTH_PASSWORD_CHANGE_TTL_MINUTES = int(
        os.getenv("AUTH_PASSWORD_CHANGE_TTL_MINUTES", "10")
    )
    # Default inactivity auto-logout for new accounts (5 / 15 / 30 / 60).
    DEFAULT_INACTIVITY_TIMEOUT_MINUTES = int(
        os.getenv("DEFAULT_INACTIVITY_TIMEOUT_MINUTES", "15")
    )
    # Government/Defense organizations are clamped to a maximum idle window
    # and never offered a "Never" option.
    GOV_MAX_INACTIVITY_TIMEOUT_MINUTES = int(
        os.getenv("GOV_MAX_INACTIVITY_TIMEOUT_MINUTES", "15")
    )
    # Minimum interval between lazy in-memory `last_seen_at` touches.
    SESSION_IDLE_TOUCH_SECONDS = int(os.getenv("SESSION_IDLE_TOUCH_SECONDS", "5"))

    # --- Auth / security ---
    JWT_SECRET = os.getenv(
        "JWT_SECRET",
        "satquery-dev-only-secret-change-me-4829f0a1b2",
    )
    JWT_ALGORITHM = "HS256"
    JWT_ACCESS_TTL_HOURS = int(os.getenv("JWT_ACCESS_TTL_HOURS", "2"))
    JWT_REFRESH_TTL_DAYS = int(os.getenv("JWT_REFRESH_TTL_DAYS", "30"))
    PASSWORD_RESET_TTL_MINUTES = int(os.getenv("PASSWORD_RESET_TTL_MINUTES", "30"))

    # --- Rate limiting ---
    RATE_LIMIT_ENABLED = os.getenv("RATE_LIMIT_ENABLED", "true").lower() == "true"
    RATE_LIMIT_PER_MINUTE = int(os.getenv("RATE_LIMIT_PER_MINUTE", "240"))
    RATE_LIMIT_AUTH_PER_MINUTE = int(os.getenv("RATE_LIMIT_AUTH_PER_MINUTE", "30"))

    # --- Paths ---
    BASE_DIR = Path(__file__).resolve().parent.parent  # backend/
    DATA_DIR = Path(os.getenv("DATA_DIR", str(BASE_DIR / "data"))).resolve()
    LOCAL_DB_FILE = Path(os.getenv("LOCAL_DB_FILE", str(DATA_DIR / "local_db.json"))).resolve()
    SEED_FLAG_FILE = Path(os.getenv("SEED_FLAG_FILE", str(DATA_DIR / ".seeded"))).resolve()
    LOG_FILE = Path(os.getenv("LOG_FILE", str(DATA_DIR / "satquery.log"))).resolve()

    # --- Demo / real satellite providers ---
    # auto  -> use demo (simulated) datasets unless a real provider key exists
    # on    -> demo datasets are required for instant usability
    # off   -> never use demo datasets; only real providers (may return nothing)
    DEMO_MODE = os.getenv("DEMO_MODE", "auto").lower()
    LLM_API_KEY = os.getenv("LLM_API_KEY", "")
    LLM_MODEL = os.getenv("LLM_MODEL", "")
    # Google AI Studio Gemini key for optional Google Search-grounded research.
    GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "") or os.getenv("GOOGLE_AI_STUDIO_API_KEY", "")
    GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
    GEMINI_TIMEOUT_SECONDS = int(os.getenv("GEMINI_TIMEOUT_SECONDS", "45"))

    # --- Historical change analysis (Date 1 -> Date 2, op: change-analysis) ---
    # Dedicated "what changed between two dates at this place?" pipeline that
    # georeferences a place name / GPS coordinate, retrieves (or synthesises)
    # before/after imagery, runs spectral + change-vector analysis and renders an
    # AI-readable evidence report. Everything degrades to the deterministic demo
    # engine when no credentials are present, and stays honestly labelled.
    CHANGE_ANALYSIS_ENABLED = _env_flag("CHANGE_ANALYSIS_ENABLED", True)
    # Maximum synthetic raster cells used by the demo change engine
    # (lower = faster; higher = finer spatial detail).
    CHANGE_MAX_CELLS = int(os.getenv("CHANGE_MAX_CELLS", "16900"))
    # Edge length (px) of the rendered before/after/heatmap PNG composites.
    CHANGE_IMAGE_SIZE = int(os.getenv("CHANGE_IMAGE_SIZE", "360"))
    # AOI padding (km) around a raw GPS point input.
    CHANGE_DEFAULT_BUFFER_KM = float(os.getenv("CHANGE_DEFAULT_BUFFER_KM", "1.0"))
    # auto -> query STAC Earth Search for the dates and keep real scene metadata;
    # raster-level processing falls back to the deterministic demo engine when
    # (a) no scenes are found or (b) the raster/GDAL stack is not installed.
    # demo -> always synthetic demo scenes (offline, instant, clearly labelled).
    CHANGE_IMAGERY_MODE = os.getenv("CHANGE_IMAGERY_MODE", "auto").lower()
    # Vision-language synthesis: auto -> use CHANGE_LLM_API_KEY when configured,
    # else the built-in deterministic report generator; none/off -> never call.
    CHANGE_LLM_PROVIDER = os.getenv("CHANGE_LLM_PROVIDER", "auto").lower()
    CHANGE_LLM_API_KEY = os.getenv("CHANGE_LLM_API_KEY", "") or LLM_API_KEY
    CHANGE_LLM_BASE_URL = os.getenv(
        "CHANGE_LLM_BASE_URL", "https://api.openai.com/v1"
    ).rstrip("/")
    CHANGE_LLM_MODEL = os.getenv("CHANGE_LLM_MODEL", "gpt-4o-mini")
    CHANGE_LLM_TIMEOUT_SECONDS = int(os.getenv("CHANGE_LLM_TIMEOUT_SECONDS", "60"))

    def change_artifact_dir(self) -> Path:  # noqa: N803 - mirrors DATA_DIR style
        """Directory where change-analysis renders (PNG/GeoTIFF) are stored."""
        return self.DATA_DIR / "change_analysis"

    # Real provider credentials (used only when provided)
    SENTINEL_CLIENT_ID = os.getenv("SENTINEL_CLIENT_ID", "")
    SENTINEL_CLIENT_SECRET = os.getenv("SENTINEL_CLIENT_SECRET", "")
    LANDSAT_API_KEY = os.getenv("LANDSAT_API_KEY", "")
    EARTHDATA_USERNAME = os.getenv("EARTHDATA_USERNAME", "")
    EARTHDATA_PASSWORD = os.getenv("EARTHDATA_PASSWORD", "")

    # --- E-mail delivery (SMTP) - Gmail-ready by default ---
    # Defaults target Gmail (smtp.gmail.com:587 + STARTTLS); any standards
    # compliant relay works.
    #   SMTP_USERNAME -> the mailbox that authenticates (Gmail address).
    #   SMTP_PASSWORD -> a Google *App Password* (16 chars). Spaces are
    #                    stripped automatically. Credentials come from the
    #                    environment only: never hard-coded, never logged and
    #                    never returned by the API.
    #   MAIL_ENABLED  -> auto (default) sends when host + username + password
    #                    are present; true/false force the behaviour;
    #                    false keeps the local OTP "demo_code" fallback.
    MAIL_MODE = os.getenv("MAIL_ENABLED", "auto").strip().lower()
    SMTP_HOST = os.getenv("SMTP_HOST", "smtp.gmail.com").strip()
    SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
    SMTP_USERNAME = (os.getenv("SMTP_USERNAME") or os.getenv("SMTP_USER", "")).strip()
    # Backwards-compatible alias (older code/tests referenced SMTP_USER).
    SMTP_USER = SMTP_USERNAME
    SMTP_PASSWORD = normalize_app_password(
        os.getenv("SMTP_PASSWORD") or os.getenv("GMAIL_APP_PASSWORD", "")
    )
    # Gmail requires the envelope sender to be the authenticated mailbox, so
    # an empty SMTP_FROM falls back to SMTP_USERNAME.
    SMTP_FROM = (
        os.getenv("SMTP_FROM", "").strip() or SMTP_USERNAME or "no-reply@satquery.ai"
    )
    SMTP_FROM_NAME = os.getenv("SMTP_FROM_NAME", "SatQuery AI").strip() or "SatQuery AI"
    SMTP_REPLY_TO = os.getenv("SMTP_REPLY_TO", "").strip()
    SMTP_USE_STARTTLS = _env_flag("SMTP_USE_STARTTLS", True)
    SMTP_USE_SSL = _env_flag("SMTP_USE_SSL", False)
    SMTP_TIMEOUT_SECONDS = int(os.getenv("SMTP_TIMEOUT_SECONDS", "15"))
    # "New sign-in" security notification e-mails (after login / MFA).
    LOGIN_NOTIFICATION_ENABLED = _env_flag("LOGIN_NOTIFICATION_ENABLED", True)
    # Public base URL used inside e-mail links (falls back to the frontend).
    APP_PUBLIC_URL = (
        os.getenv("APP_PUBLIC_URL", "").strip()
        or os.getenv("FRONTEND_ORIGIN", "http://localhost:5173")
    )
    # Snapshot kept for backwards compatibility - prefer ``mail_enabled()``,
    # which re-evaluates the current configuration (and is test friendly).
    MAIL_ENABLED = bool(SMTP_HOST and SMTP_USERNAME and SMTP_PASSWORD) and MAIL_MODE not in (
        "false",
        "off",
        "no",
        "0",
    )

    # --- Google Docs report export (OAuth) ---
    # Configure these to push analyses straight into Google Docs:
    #   GOOGLE_CLIENT_ID / GOOGLE_CLIENT_SECRET / GOOGLE_REDIRECT_URI
    # When absent the feature falls back to a Google-Docs-compatible .docx.
    GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID", "")
    GOOGLE_CLIENT_SECRET = os.getenv("GOOGLE_CLIENT_SECRET", "")
    GOOGLE_REDIRECT_URI = os.getenv(
        "GOOGLE_REDIRECT_URI", "http://localhost:8000/api/reports/google/callback"
    )

    @property
    def cors_origins(self) -> list[str]:
        origins = {self.FRONTEND_ORIGIN}
        for raw in os.getenv("CORS_ORIGINS", "").split(","):
            if raw.strip():
                origins.add(raw.strip())
        return sorted(origins)

    def demo_enabled(self) -> bool:
        """Whether simulated demo data may be used for a given pipeline."""
        if self.DEMO_MODE == "off":
            return False
        if self.DEMO_MODE == "on":
            return True
        # auto: demo is used as long as no real provider credentials exist.
        return not (self.SENTINEL_CLIENT_ID or self.LANDSAT_API_KEY)

    # --- E-mail ---------------------------------------------------------

    def mail_credentials_present(self) -> bool:
        """True when host + authenticating mailbox + app password are set."""
        return bool(self.SMTP_HOST and self.SMTP_USERNAME and self.SMTP_PASSWORD)

    def mail_enabled(self) -> bool:
        """Whether real SMTP delivery should be attempted.

        ``MAIL_ENABLED=false`` always wins; otherwise mail is sent as soon as
        the credentials exist. Without credentials the OTP flows fall back to
        the local ``demo_code`` behaviour.
        """
        if (self.MAIL_MODE or "auto").lower() in ("false", "off", "no", "0"):
            return False
        return self.mail_credentials_present()

    def sender_header(self) -> str:
        """RFC 5322 ``From`` header, e.g. ``SatQuery AI <no-reply@satquery.ai>``."""
        name = "".join(
            ch for ch in (self.SMTP_FROM_NAME or "") if ch not in '<>"\r\n,'
        ).strip()
        return f"{name} <{self.SMTP_FROM}>" if name else self.SMTP_FROM


settings = Settings()
