import uuid
from datetime import datetime, timezone
from fastapi import APIRouter, HTTPException
from fastapi.responses import Response
from sqlalchemy import select, text
from app.api.deps import AsyncSessionDep, TenantIdDep
from app.models.qr_code import QRCode
from app.models.invitation import Invitation
from app.schemas.qr_code import QRScanResponse
from app.services.qr_service import QRService, QRValidationError
from app.services.visit_service import VisitService
from app.services.notification_service import NotificationService
from app.models.user import User

router = APIRouter(prefix="/qr", tags=["qr"])


async def _set_rls(db, tenant_id: uuid.UUID) -> None:
    await db.execute(text(f"SET LOCAL app.current_tenant_id = '{tenant_id}'"))


@router.get("/{code}", response_model=QRScanResponse)
async def scan_qr(code: uuid.UUID, db: AsyncSessionDep, tenant_id: TenantIdDep):
    """Staff scan endpoint. Validates QR, triggers check-in + notifications."""
    async with db.begin():
        await _set_rls(db, tenant_id)
        result = await db.execute(select(QRCode).where(QRCode.code == code))
        qr = result.scalar_one_or_none()
        if not qr:
            raise HTTPException(status_code=404, detail="QR code not found")

        try:
            QRService.validate(qr)
        except QRValidationError as e:
            raise HTTPException(status_code=e.http_status, detail=str(e))

        # Mark used for ONE_TIME
        from app.models.qr_code import QRCodeType
        if qr.type == QRCodeType.ONE_TIME:
            qr.used_at = datetime.now(timezone.utc)

        # Check in the visit
        visit_service = VisitService(db)
        visit = await visit_service.check_in(qr.visit_id)

        # Fetch visitor name and host email
        from app.models.visitor import Visitor
        visitor_result = await db.execute(select(Visitor).where(Visitor.id == visit.visitor_id))
        visitor = visitor_result.scalar_one_or_none()
        visitor_name = visitor.name if visitor else "Unknown"

        host_email = None
        if visit.host_id:
            host_result = await db.execute(select(User).where(User.id == visit.host_id))
            host = host_result.scalar_one_or_none()
            host_email = host.email if host else None

        # Notify (fire-and-forget via BackgroundTasks is fine here — no retry needed)
        notif_service = NotificationService(db)
        await notif_service.notify_checkin(
            tenant_id=tenant_id,
            visit_id=visit.id,
            host_id=visit.host_id,
            visitor_name=visitor_name,
            host_email=host_email,
        )

    return QRScanResponse(
        visit_id=visit.id,
        visitor_name=visitor_name,
        checked_in_at=visit.checked_in_at,
    )


@router.get("/{code}/image.png")
async def get_qr_image(code: uuid.UUID, token: str, db: AsyncSessionDep):
    """Return PNG QR image. Protected by invitation token query param.

    Validates that the token belongs to an invitation for this QR code's visit.
    This is a public endpoint — no staff JWT required.
    """
    # Parse tenant_id from token prefix ({tenant_id}.{random})
    try:
        tenant_id_str, _ = token.split(".", 1)
        tenant_id = uuid.UUID(tenant_id_str)
    except (ValueError, AttributeError):
        raise HTTPException(status_code=401, detail="Invalid token")

    async with db.begin():
        await db.execute(text(f"SET LOCAL app.current_tenant_id = '{tenant_id}'"))
        # Confirm QR code exists in this tenant
        qr_result = await db.execute(select(QRCode).where(QRCode.code == code))
        qr = qr_result.scalar_one_or_none()
        if not qr:
            raise HTTPException(status_code=404, detail="QR code not found")
        # Confirm invitation token belongs to this visit
        inv_result = await db.execute(
            select(Invitation).where(
                Invitation.token == token,
                Invitation.visit_id == qr.visit_id,
            )
        )
        if not inv_result.scalar_one_or_none():
            raise HTTPException(status_code=401, detail="Invalid token for this QR code")

    png_bytes = QRService.generate_png(code)
    return Response(content=png_bytes, media_type="image/png")


@router.post("/{code}/revoke")
async def revoke_qr(code: uuid.UUID, db: AsyncSessionDep, tenant_id: TenantIdDep):
    async with db.begin():
        await _set_rls(db, tenant_id)
        result = await db.execute(select(QRCode).where(QRCode.code == code))
        qr = result.scalar_one_or_none()
        if not qr:
            raise HTTPException(status_code=404, detail="QR code not found")
        qr.is_revoked = True
    return {"detail": "QR code revoked"}
