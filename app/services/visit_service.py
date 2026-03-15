"""Visit service — lifecycle management for visits."""
import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.visit import Visit, VisitStatus


class VisitStateError(Exception):
    """Raised when a visit transition is invalid."""


class VisitService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def get_by_id(self, visit_id: uuid.UUID) -> Visit | None:
        result = await self.db.execute(select(Visit).where(Visit.id == visit_id))
        return result.scalar_one_or_none()

    async def create(
        self,
        *,
        tenant_id: uuid.UUID,
        visitor_id: uuid.UUID,
        purpose: str,
        host_id: uuid.UUID | None = None,
        scheduled_at: datetime | None = None,
    ) -> Visit:
        visit = Visit(
            tenant_id=tenant_id,
            visitor_id=visitor_id,
            host_id=host_id,
            purpose=purpose,
            status=VisitStatus.SCHEDULED,
            scheduled_at=scheduled_at,
        )
        self.db.add(visit)
        await self.db.flush()
        return visit

    async def check_in(self, visit_id: uuid.UUID) -> Visit:
        visit = await self.get_by_id(visit_id)
        if visit is None:
            raise VisitStateError("Visit not found")
        if visit.status != VisitStatus.SCHEDULED:
            raise VisitStateError(f"Cannot check in a visit with status {visit.status}")
        visit.status = VisitStatus.CHECKED_IN
        visit.checked_in_at = datetime.now(timezone.utc)
        await self.db.flush()
        return visit

    async def check_out(self, visit_id: uuid.UUID) -> Visit:
        visit = await self.get_by_id(visit_id)
        if visit is None:
            raise VisitStateError("Visit not found")
        if visit.status != VisitStatus.CHECKED_IN:
            raise VisitStateError(f"Cannot check out a visit with status {visit.status}")
        visit.status = VisitStatus.CHECKED_OUT
        visit.checked_out_at = datetime.now(timezone.utc)
        await self.db.flush()
        return visit

    async def cancel(self, visit_id: uuid.UUID) -> Visit:
        visit = await self.get_by_id(visit_id)
        if visit is None:
            raise VisitStateError("Visit not found")
        if visit.status in (VisitStatus.CHECKED_OUT, VisitStatus.CANCELLED):
            raise VisitStateError(f"Cannot cancel a visit with status {visit.status}")
        visit.status = VisitStatus.CANCELLED
        await self.db.flush()
        return visit

    async def list(
        self,
        *,
        status: VisitStatus | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[Visit]:
        q = select(Visit).order_by(Visit.created_at.desc()).limit(limit).offset(offset)
        if status:
            q = q.where(Visit.status == status)
        result = await self.db.execute(q)
        return list(result.scalars().all())
