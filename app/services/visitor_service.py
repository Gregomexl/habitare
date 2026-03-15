"""Visitor service — CRUD with email-based deduplication within tenant."""
import uuid
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.visitor import Visitor


class VisitorService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def create_or_get(
        self,
        *,
        tenant_id: uuid.UUID,
        name: str,
        email: str | None = None,
        phone: str | None = None,
        photo_url: str | None = None,
        vehicle_plate: str | None = None,
    ) -> Visitor:
        """Return existing visitor if email matches within tenant; create otherwise.

        Dedup: if email is not None and matches an existing visitor in the same tenant,
        the existing record is returned. Walk-ins (email=None) always create a new record.
        Concurrent creates with the same email may raise IntegrityError — caller must handle.
        Tenant isolation is enforced by RLS (SET LOCAL app.current_tenant_id).
        """
        if email is not None:
            result = await self.db.execute(
                select(Visitor).where(
                    Visitor.tenant_id == tenant_id,
                    Visitor.email == email,
                )
            )
            existing = result.scalar_one_or_none()
            if existing:
                return existing

        visitor = Visitor(
            tenant_id=tenant_id,
            name=name,
            email=email,
            phone=phone,
            photo_url=photo_url,
            vehicle_plate=vehicle_plate,
        )
        self.db.add(visitor)
        await self.db.flush()
        return visitor

    async def get_by_id(self, visitor_id: uuid.UUID) -> Visitor | None:
        result = await self.db.execute(
            select(Visitor).where(Visitor.id == visitor_id)
        )
        return result.scalar_one_or_none()

    async def update(
        self,
        visitor: Visitor,
        *,
        name: str | None = None,
        phone: str | None = None,
        vehicle_plate: str | None = None,
    ) -> Visitor:
        if name is not None:
            visitor.name = name
        if phone is not None:
            visitor.phone = phone
        if vehicle_plate is not None:
            visitor.vehicle_plate = vehicle_plate
        await self.db.flush()
        return visitor

    async def list(
        self,
        *,
        search: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[Visitor]:
        q = select(Visitor)
        if search:
            q = q.where(
                Visitor.name.ilike(f"%{search}%") | Visitor.email.ilike(f"%{search}%")
            )
        q = q.order_by(Visitor.created_at.desc()).limit(limit).offset(offset)
        result = await self.db.execute(q)
        return list(result.scalars().all())
