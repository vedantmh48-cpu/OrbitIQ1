"""Mission Control backend dev launcher: python run.py"""
import sys

import uvicorn

# Windows terminals (cp1252) choke on unicode glyphs; force UTF-8 so startup
# output can never crash the launcher before uvicorn runs.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

from app.config import HOST, PORT  # noqa: E402

if __name__ == "__main__":
    print(f"Mission Control backend -> http://{HOST}:{PORT}  (API docs: /docs)")
    uvicorn.run(
        "app.main:app",
        host=HOST,
        port=PORT,
        reload=False,
        log_level="info",
    )