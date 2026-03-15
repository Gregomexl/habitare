"""
Habitare - QR-Based Visitor Management System
FastAPI Application Entry Point
"""
import logging

from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIASGIMiddleware
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.api.exception_handlers import (
    http_exception_handler,
    rate_limit_handler,
    unhandled_exception_handler,
    validation_exception_handler,
)
from app.api.v1.endpoints.admin import router as admin_router
from app.api.v1.endpoints.auth import router as auth_router
from app.api.v1.endpoints.invitations import router as invitations_router
from app.api.v1.endpoints.notifications import router as notifications_router
from app.api.v1.endpoints.qr import router as qr_router
from app.api.v1.endpoints.users import router as users_router
from app.api.v1.endpoints.visitors import router as visitors_router
from app.api.v1.endpoints.visits import router as visits_router
from app.core.config import settings
from app.core.limiter import limiter
from app.middleware.request_id import RequestIDMiddleware

logger = logging.getLogger(__name__)

app = FastAPI(
    title="Habitare API",
    description="QR-Based Visitor Management System",
    version="0.1.0",
)

# ── Rate limiter ──────────────────────────────────────────────────────────────
app.state.limiter = limiter

# ── Exception handlers ────────────────────────────────────────────────────────
# StarletteHTTPException (not fastapi.HTTPException) catches routing 404/405 too
app.add_exception_handler(StarletteHTTPException, http_exception_handler)
app.add_exception_handler(RequestValidationError, validation_exception_handler)
app.add_exception_handler(RateLimitExceeded, rate_limit_handler)
app.add_exception_handler(Exception, unhandled_exception_handler)

# ── Middleware (outermost registered last — runs first on request) ─────────────
# Order: RequestID → SlowAPI → CORS → route handler
app.add_middleware(CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["X-Request-ID"],
)
app.add_middleware(SlowAPIASGIMiddleware)
app.add_middleware(RequestIDMiddleware)

# ── Startup validation ────────────────────────────────────────────────────────
@app.on_event("startup")
async def validate_config() -> None:
    if settings.email_enabled and not settings.resend_api_key:
        raise RuntimeError(
            "HABITARE_RESEND_API_KEY must be set when HABITARE_EMAIL_ENABLED=true. "
            "Get a free API key at https://resend.com"
        )
    logger.info(
        "Habitare API starting — email_enabled=%s, environment=%s",
        settings.email_enabled,
        settings.environment,
    )

# ── Routers ───────────────────────────────────────────────────────────────────
API_PREFIX = "/api/v1"
app.include_router(auth_router, prefix=API_PREFIX)
app.include_router(users_router, prefix=API_PREFIX)
app.include_router(visitors_router, prefix=API_PREFIX)
app.include_router(visits_router, prefix=API_PREFIX)
app.include_router(invitations_router, prefix=API_PREFIX)
app.include_router(qr_router, prefix=API_PREFIX)
app.include_router(notifications_router, prefix=API_PREFIX)
app.include_router(admin_router, prefix=API_PREFIX)


@app.get("/")
async def root():
    return {"status": "ok", "message": "Habitare API is running", "version": app.version}


@app.get("/health")
async def health_check():
    return {"status": "healthy", "service": "habitare-api", "version": app.version}
