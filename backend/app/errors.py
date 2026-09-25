"""Global exception handlers -> consistent JSON error envelope."""
from __future__ import annotations

import json

from fastapi import FastAPI, HTTPException, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException


def app_error(status_code: int, detail: str, code: str | None = None, headers: dict | None = None):
    """Build an HTTPException whose ``code`` machine-key is preserved in the
    JSON error envelope (``{"error", "detail", "code"}``)."""
    exc = HTTPException(status_code=status_code, detail=detail, headers=headers)
    if code:
        setattr(exc, "code", code)
    return exc


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(StarletteHTTPException)
    async def http_exception_handler(request: Request, exc: StarletteHTTPException):
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "error": True,
                "detail": str(exc.detail),
                "code": getattr(exc, "code", "HTTP_ERROR"),
            },
        )

    @app.exception_handler(RequestValidationError)
    async def validation_handler(request: Request, exc: RequestValidationError):
        errors = exc.errors()
        messages = []
        for e in errors:
            loc = ".".join(str(x) for x in e.get("loc", []) if x != "body")
            messages.append(f"{loc}: {e.get('msg', 'invalid value')}")
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content={
                "error": True,
                "detail": "; ".join(messages),
                "code": "VALIDATION_ERROR",
                "fields": _clean_errors(errors),
            },
        )


def _clean_errors(errors) -> list[dict]:
    """Strip non-JSON-serializable contexts (Pydantic v2 'ctx').
    """
    out = []
    for e in errors:
        clean = {k: v for k, v in e.items() if k != "ctx"}
        ctx = e.get("ctx")
        if ctx:
            try:
                json.dumps(ctx)
            except (TypeError, ValueError):
                clean["ctx"] = {str(k): str(v) for k, v in ctx.items()}
        out.append(clean)
    return out

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(request: Request, exc: Exception):
        from .middleware import logger

        logger.exception("Unhandled error on %s %s", request.method, request.url.path)
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={
                "error": True,
                "detail": "An internal error occurred. Please try again later.",
                "code": "INTERNAL_ERROR",
            },
        )