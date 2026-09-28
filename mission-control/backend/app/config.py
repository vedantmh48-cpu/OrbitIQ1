"""Mission Control - runtime configuration.

Kept dependency-light on purpose: every setting has a sane default so the
service boots with zero configuration and gets its values overridden by
environment variables only when they are actually provided.
"""
from __future__ import annotations

import os
from pathlib import Path

APP_NAME = "Mission Control"
VERSION = "1.0.0"

HOST = os.getenv("MC_HOST", "127.0.0.1")
PORT = int(os.getenv("MC_PORT", "8100"))

# Root of the backend package (…/mission-control/backend)
BASE_DIR = Path(__file__).resolve().parent.parent

# The static frontend lives next to the backend: …/mission-control/frontend
FRONTEND_DIR = Path(os.getenv("MC_FRONTEND_DIR", BASE_DIR.parent / "frontend"))

# In-memory store keeps this many telemetry samples per satellite (rolling window).
TELEMETRY_HISTORY = int(os.getenv("MC_TELEMETRY_HISTORY", "90"))

# CORS: by default allow the local dev origin of the main SatQuery frontend too.
CORS_ORIGINS = os.getenv(
    "MC_CORS_ORIGINS",
    "http://localhost:5173,http://127.0.0.1:5173",
).split(",")