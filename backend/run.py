"""Backend dev launcher.

    python run.py            # backend-only API server
    python run.py --reload   # with hot reload on code changes

For the full app (backend API + Vite frontend, single command) run
``python run.py`` from the project root instead.
"""
from __future__ import annotations

import sys
from pathlib import Path

# Make `from app...` work no matter which directory this script is run from.
_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

import uvicorn

from app.config import settings

if __name__ == "__main__":
    reload_enabled = "--reload" in sys.argv or "reload" in sys.argv
    try:
        settings.DATA_DIR.mkdir(parents=True, exist_ok=True)
    except OSError:
        pass
    uvicorn.run(
        "app.main:app",
        host=settings.HOST,
        port=settings.PORT,
        reload=reload_enabled,
        log_level="info",
    )