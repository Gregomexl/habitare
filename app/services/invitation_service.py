"""Invitation service — pass link token creation and validation."""
import secrets
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.invitation import Invitation, InvitationStatus


class InvitationService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    @staticmethod
    def generate_token(tenant_id: uuid.UUID) -> str:
        """Generate a secure URL-safe token for the pass link.

        Format: "{tenant_id}.{random}" — the tenant_id prefix allows the public
        GET /pass/{token} endpoint to set RLS context without a superuser connection.
        The random suffix provides unguessability. Base64url chars never contain '.',
        so splitting on '.' gives an unambiguous prefix.
        """
        return f"{tenant_id}.{secrets.token_urlsafe(32)}"

    @staticmethod
    def build_pass_url(token: str, *, base_url: str) -> str:
        return f"{base_url.rstrip('/')}/pass/{token}"

    async def create(
        self,
        *,
        tenant_id: uuid.UUID,
        visit_id: uuid.UUID,
        sent_to_email: str | None = None,
        expires_in: timedelta = timedelta(days=7),
    ) -> Invitation:
        invitation = Invitation(
            tenant_id=tenant_id,
            visit_id=visit_id,
            token=self.generate_token(tenant_id),
            sent_to_email=sent_to_email,
            status=InvitationStatus.PENDING,
            expires_at=datetime.now(timezone.utc) + expires_in,
        )
        self.db.add(invitation)
        await self.db.flush()
        return invitation

    async def get_by_token(self, token: str) -> Invitation | None:
        result = await self.db.execute(
            select(Invitation).where(Invitation.token == token)
        )
        return result.scalar_one_or_none()

    async def mark_viewed(self, invitation: Invitation) -> Invitation:
        if invitation.status == InvitationStatus.PENDING:
            invitation.status = InvitationStatus.VIEWED
            await self.db.flush()
        return invitation

    async def revoke(self, invitation: Invitation) -> Invitation:
        invitation.status = InvitationStatus.EXPIRED
        await self.db.flush()
        return invitation

    def is_valid(self, invitation: Invitation) -> bool:
        now = datetime.now(timezone.utc)
        expires_at = invitation.expires_at
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=timezone.utc)
        return invitation.status != InvitationStatus.EXPIRED and now < expires_at
