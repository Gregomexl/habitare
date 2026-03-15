"""
Habitare - QR-Based Visitor Management System
FastAPI Application Entry Point
"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(
    title="Habitare API",
    description="QR-Based Visitor Management System",
    version="0.1.0",
)

# CORS middleware (will be configured from settings later)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

from app.api.v1.endpoints.visitors import router as visitors_router
from app.api.v1.endpoints.visits import router as visits_router
from app.api.v1.endpoints.invitations import router as invitations_router
from app.api.v1.endpoints.qr import router as qr_router
from app.api.v1.endpoints.notifications import router as notifications_router
from app.api.v1.endpoints.admin import router as admin_router

API_PREFIX = "/api/v1"
app.include_router(visitors_router, prefix=API_PREFIX)
app.include_router(visits_router, prefix=API_PREFIX)
app.include_router(invitations_router, prefix=API_PREFIX)  # /invitations/ and /pass/ routes
app.include_router(qr_router, prefix=API_PREFIX)
app.include_router(notifications_router, prefix=API_PREFIX)
app.include_router(admin_router, prefix=API_PREFIX)


@app.get("/")
async def root():
    """Health check endpoint."""
    return {
        "status": "ok",
        "message": "Habitare API is running",
        "version": "0.1.0"
    }


@app.get("/health")
async def health_check():
    """Detailed health check endpoint."""
    return {
        "status": "healthy",
        "service": "habitare-api",
        "version": "0.1.0"
    }
