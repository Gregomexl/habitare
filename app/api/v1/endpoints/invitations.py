import uuid
from fastapi import APIRouter, HTTPException
from sqlalchemy import select
from app.api.deps import AsyncSessionDep, TenantIdDep, set_rls
from app.models.invitation import Invitation, InvitationStatus
from app.models.qr_code import QRCode
from app.models.user import User
from app.models.visit import Visit
from app.models.visitor import Visitor
from app.schemas.invitation import InvitationCreate, InvitationResponse, PassLinkResponse
from app.services.invitation_service import InvitationService

router = APIRouter(tags=["invitations"])


def _get_base_url() -> str:
    """Read base_url from settings. Add HABITARE_BASE_URL to .env for production."""
    from app.core.config import settings
    return getattr(settings, "base_url", "http://localhost:8000")


@router.post("/invitations/", response_model=InvitationResponse, status_code=201)
async def create_invitation(body: InvitationCreate, db: AsyncSessionDep, tenant_id: TenantIdDep):
    async with db.begin():
        await set_rls(db, tenant_id)
        service = InvitationService(db)
        invitation = await service.create(
            tenant_id=tenant_id,
            visit_id=body.visit_id,
            sent_to_email=body.sent_to_email,
        )
    response = InvitationResponse.model_validate(invitation)
    response.pass_link = InvitationService.build_pass_url(invitation.token, base_url=_get_base_url())
    return response


@router.get("/invitations/{invitation_id}", response_model=InvitationResponse)
async def get_invitation(invitation_id: uuid.UUID, db: AsyncSessionDep, tenant_id: TenantIdDep):
    async with db.begin():
        await set_rls(db, tenant_id)
        result = await db.execute(select(Invitation).where(Invitation.id == invitation_id))
        invitation = result.scalar_one_or_none()
    if not invitation:
        raise HTTPException(status_code=404, detail="Invitation not found")
    return invitation


@router.post("/invitations/{invitation_id}/revoke")
async def revoke_invitation(invitation_id: uuid.UUID, db: AsyncSessionDep, tenant_id: TenantIdDep):
    async with db.begin():
        await set_rls(db, tenant_id)
        result = await db.execute(select(Invitation).where(Invitation.id == invitation_id))
        invitation = result.scalar_one_or_none()
        if not invitation:
            raise HTTPException(status_code=404, detail="Invitation not found")
        service = InvitationService(db)
        await service.revoke(invitation)
        # Also revoke associated QR codes (may be more than one)
        qr_result = await db.execute(select(QRCode).where(QRCode.visit_id == invitation.visit_id))
        for qr in qr_result.scalars().all():
            qr.is_revoked = True
    return {"detail": "Invitation revoked"}


@router.get("/pass/{token}", response_model=PassLinkResponse)
async def get_pass(token: str, db: AsyncSessionDep):
    """Public endpoint — no auth. Returns visit snapshot for pass link page.

    Token format: "{tenant_id}.{random}" — the tenant_id prefix is extracted to
    set RLS context so the query runs within the correct tenant without bypassing
    row security or requiring a superuser connection.
    """
    # Extract tenant_id from token prefix to enable RLS
    try:
        tenant_id_str, _ = token.split(".", 1)
        tenant_id = uuid.UUID(tenant_id_str)
    except (ValueError, AttributeError):
        raise HTTPException(status_code=410, detail="This pass link has expired.")

    from datetime import datetime, timezone

    async with db.begin():
        await set_rls(db, tenant_id)

        result = await db.execute(
            select(Invitation).where(Invitation.token == token)
        )
        invitation = result.scalar_one_or_none()
        if not invitation:
            raise HTTPException(status_code=410, detail="This pass link has expired.")

        expires_at = invitation.expires_at
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=timezone.utc)
        if invitation.status == InvitationStatus.EXPIRED or datetime.now(timezone.utc) > expires_at:
            raise HTTPException(status_code=410, detail="This pass link has expired.")

        # Mark as viewed (no-op if already VIEWED or EXPIRED)
        service = InvitationService(db)
        await service.mark_viewed(invitation)

        # Fetch visit snapshot within tenant RLS context
        visit_result = await db.execute(select(Visit).where(Visit.id == invitation.visit_id))
        visit = visit_result.scalar_one_or_none()
        if not visit:
            raise HTTPException(status_code=410, detail="This pass link has expired.")

        visitor_result = await db.execute(select(Visitor).where(Visitor.id == visit.visitor_id))
        visitor = visitor_result.scalar_one_or_none()
        visitor_name = visitor.name if visitor else "Unknown"

        host_name = None
        if visit.host_id:
            host_result = await db.execute(select(User).where(User.id == visit.host_id))
            host = host_result.scalar_one_or_none()
            host_name = host.full_name if host else None

        # Get active QR code
        qr_result = await db.execute(
            select(QRCode)
            .where(QRCode.visit_id == invitation.visit_id, QRCode.is_revoked.is_(False))
            .order_by(QRCode.created_at.desc())
            .limit(1)
        )
        qr = qr_result.scalar_one_or_none()
        qr_code_url = f"/api/v1/qr/{qr.code}/image.png?token={token}" if qr else ""

    return PassLinkResponse(
        visitor_name=visitor_name,
        host_name=host_name,
        scheduled_at=visit.scheduled_at,
        qr_code_url=qr_code_url,
        expires_at=expires_at,
    )
