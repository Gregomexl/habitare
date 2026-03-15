import uuid
from datetime import datetime, timedelta, timezone
from fastapi import APIRouter, HTTPException
from fastapi.responses import Response
from sqlalchemy import select
from app.api.deps import AsyncSessionDep, CurrentUserDep, set_rls
from app.models.qr_code import QRCode, QRCodeType
from app.models.invitation import Invitation
from app.schemas.qr_code import QRCodeResponse, QRScanResponse
from app.services.qr_service import QRService, QRValidationError
from app.services.visit_service import VisitService

router = APIRouter(prefix="/qr", tags=["qr"])


@router.get("/{code}", response_model=QRScanResponse)
async def scan_qr(code: uuid.UUID, db: AsyncSessionDep, current_user: CurrentUserDep):
    """Staff scan endpoint. Validates QR, triggers check-in + notifications."""
    from app.services.notification_service import NotificationService
    from app.models.user import User
    from app.models.visitor import Visitor

    async with db.begin():
        await set_rls(db, current_user.tenant_id)
        qr_service = QRService(db)
        try:
            qr = await qr_service.validate_and_consume(code)
        except QRValidationError as e:
            raise HTTPException(status_code=e.http_status, detail=str(e))

        visit_service = VisitService(db)
        visit = await visit_service.check_in(qr.visit_id)

        visitor_result = await db.execute(select(Visitor).where(Visitor.id == visit.visitor_id))
        visitor = visitor_result.scalar_one()

        host_email = None
        if visit.host_id:
            host_result = await db.execute(select(User).where(User.id == visit.host_id))
            host = host_result.scalar_one_or_none()
            host_email = host.email if host else None

        visit_id = visit.id
        visitor_name = visitor.name
        checked_in_at = visit.checked_in_at
        host_id = visit.host_id

    notif_service = NotificationService(db)
    await notif_service.notify_checkin(
        tenant_id=current_user.tenant_id,
        visit_id=visit_id,
        host_id=host_id,
        visitor_name=visitor_name,
        host_email=host_email,
    )

    return QRScanResponse(
        visit_id=visit_id,
        visitor_name=visitor_name,
        checked_in_at=checked_in_at,
    )


@router.get("/{code}/image.png")
async def get_qr_image(code: uuid.UUID, token: str, db: AsyncSessionDep):
    """Return PNG QR image. Protected by invitation token query param (public — no JWT)."""
    try:
        tenant_id_str, _ = token.split(".", 1)
        tenant_id = uuid.UUID(tenant_id_str)
    except (ValueError, AttributeError):
        raise HTTPException(status_code=401, detail="Invalid token")

    async with db.begin():
        await set_rls(db, tenant_id)
        qr_result = await db.execute(select(QRCode).where(QRCode.code == code))
        qr = qr_result.scalar_one_or_none()
        if not qr:
            raise HTTPException(status_code=404, detail="QR code not found")
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
async def revoke_qr(code: uuid.UUID, db: AsyncSessionDep, current_user: CurrentUserDep):
    async with db.begin():
        await set_rls(db, current_user.tenant_id)
        result = await db.execute(select(QRCode).where(QRCode.code == code))
        qr = result.scalar_one_or_none()
        if not qr:
            raise HTTPException(status_code=404, detail="QR code not found")
        qr.is_revoked = True
    return {"detail": "QR code revoked"}


@router.post("/{visit_id}/generate", response_model=QRCodeResponse, status_code=201)
async def generate_qr(visit_id: uuid.UUID, db: AsyncSessionDep, current_user: CurrentUserDep):
    """Explicit QR generation — walk-in fast path."""
    now = datetime.now(timezone.utc)
    async with db.begin():
        await set_rls(db, current_user.tenant_id)
        qr = QRCode(
            tenant_id=current_user.tenant_id,
            visit_id=visit_id,
            type=QRCodeType.ONE_TIME,
            valid_from=now,
            valid_until=now + timedelta(minutes=30),
        )
        db.add(qr)
        await db.flush()
    return qr
