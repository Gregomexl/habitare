"""
SQLAlchemy Models Package

Import all models here to ensure they are registered with the Base metadata.
This is required for Alembic migrations to detect model changes.
"""
from app.models.base import Base, TenantMixin, TimestampMixin
from app.models.tenant import Tenant
from app.models.user import User, UserRole
from app.models.visitor import Visitor
from app.models.visit import Visit, VisitStatus
from app.models.qr_code import QRCode, QRCodeType
from app.models.invitation import Invitation, InvitationStatus
from app.models.notification import Notification, NotificationChannel, NotificationStatus

__all__ = [
    "Base",
    "TenantMixin",
    "TimestampMixin",
    "Tenant",
    "User",
    "UserRole",
    "Visitor",
    "Visit",
    "VisitStatus",
    "QRCode",
    "QRCodeType",
    "Invitation",
    "InvitationStatus",
    "Notification",
    "NotificationChannel",
    "NotificationStatus",
]
