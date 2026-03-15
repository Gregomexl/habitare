"""QR service — PNG generation, validation, and scan orchestration.

The QR image encodes only the raw UUID string (not a URL).
Staff use an authenticated web app scanner that extracts the UUID
and calls GET /qr/{code} with their JWT.
"""
import io
import uuid
from datetime import datetime, timezone
from typing import Any

import qrcode
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.qr_code import QRCode, QRCodeType


class QRValidationError(Exception):
    """Raised when QR validation fails. Message is user-facing."""
    def __init__(self, message: str, http_status: int) -> None:
        super().__init__(message)
        self.http_status = http_status


class QRService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    @staticmethod
    def validate(qr: Any) -> None:
        """Validate a QRCode ORM object. Raises QRValidationError on failure.

        Validation order:
        1. is_revoked → 410
        2. TIME_BOUNDED: time window check → 403
        3. ONE_TIME: time window check → 403, replay check → 409
        """
        now = datetime.now(timezone.utc)

        if qr.is_revoked:
            raise QRValidationError("QR code has been revoked", http_status=410)

        valid_from = qr.valid_from.replace(tzinfo=timezone.utc) if qr.valid_from.tzinfo is None else qr.valid_from
        valid_until = qr.valid_until.replace(tzinfo=timezone.utc) if qr.valid_until.tzinfo is None else qr.valid_until

        if qr.type == QRCodeType.TIME_BOUNDED:
            if not (valid_from <= now <= valid_until):
                raise QRValidationError("QR code has expired or is not yet valid", http_status=403)

        if qr.type == QRCodeType.ONE_TIME:
            if not (valid_from <= now <= valid_until):
                raise QRValidationError("QR code has expired", http_status=403)
            if qr.used_at is not None:
                raise QRValidationError("QR code already used", http_status=409)

    async def validate_and_consume(self, code: uuid.UUID) -> QRCode:
        """Fetch QR code by `code` UUID, validate, mark used, and return the record.

        The caller (endpoint) is responsible for:
        - Calling VisitService.check_in(qr.visit_id) after this returns
        - Calling NotificationService.notify_checkin(...) after check-in commits

        Raises:
          QRValidationError — with http_status set to appropriate HTTP code.
          Includes 404 if code does not exist.
        """
        result = await self.db.execute(
            select(QRCode).where(QRCode.code == code)
        )
        qr = result.scalar_one_or_none()
        if qr is None:
            raise QRValidationError("QR code not found", http_status=404)

        self.validate(qr)

        if qr.type == QRCodeType.ONE_TIME:
            qr.used_at = datetime.now(timezone.utc)
            await self.db.flush()

        return qr

    @staticmethod
    def generate_png(code: uuid.UUID) -> bytes:
        """Generate a PNG QR code image encoding the raw UUID string.

        Returns raw PNG bytes suitable for streaming as image/png.
        """
        qr = qrcode.QRCode(
            error_correction=qrcode.constants.ERROR_CORRECT_M,
            box_size=10,
            border=4,
        )
        qr.add_data(str(code))
        qr.make(fit=True)
        img = qr.make_image(fill_color="black", back_color="white")
        buffer = io.BytesIO()
        img.save(buffer, format="PNG")
        return buffer.getvalue()
