"""FastAPI exception handlers — structured error envelope for all error paths.

All handlers return:
    {"error": {"code": str, "message": str, "detail": any, "request_id": str | None}}

Registered in app/main.py on StarletteHTTPException (not fastapi.HTTPException)
so routing-level 404/405 errors also use the envelope.
"""
import logging

from fastapi import Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from slowapi.errors import RateLimitExceeded
from starlette.exceptions import HTTPException as StarletteHTTPException

logger = logging.getLogger(__name__)


def _request_id(request: Request) -> str | None:
    return getattr(request.state, "request_id", None)


async def http_exception_handler(request: Request, exc: StarletteHTTPException) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        content={"error": {
            "code": f"HTTP_{exc.status_code}",
            "message": str(exc.detail),
            "detail": None,
            "request_id": _request_id(request),
        }},
    )


async def validation_exception_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    return JSONResponse(
        status_code=422,
        content={"error": {
            "code": "VALIDATION_ERROR",
            "message": "Invalid request body",
            "detail": exc.errors(),
            "request_id": _request_id(request),
        }},
    )


async def rate_limit_handler(request: Request, exc: RateLimitExceeded) -> JSONResponse:
    return JSONResponse(
        status_code=429,
        content={"error": {
            "code": "RATE_LIMIT_EXCEEDED",
            "message": "Too many requests",
            "detail": None,
            "request_id": _request_id(request),
        }},
    )


async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    logger.exception("Unhandled error on %s %s: %s", request.method, request.url.path, exc)
    return JSONResponse(
        status_code=500,
        content={"error": {
            "code": "INTERNAL_ERROR",
            "message": "An internal error occurred",
            "detail": None,
            "request_id": _request_id(request),
        }},
    )
