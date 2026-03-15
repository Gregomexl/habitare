from fastapi import APIRouter, HTTPException
from sqlalchemy import select, text
from app.api.deps import AsyncSessionDep
from app.models.tenant import Tenant
from app.schemas.tenant import TenantResponse

router = APIRouter(prefix="/admin", tags=["admin"])


@router.get("/tenants/", response_model=list[TenantResponse])
async def list_tenants(db: AsyncSessionDep, limit: int = 50, offset: int = 0):
    """Super admin only — list all tenants. Auth guard added when Phase 1 auth is complete."""
    async with db.begin():
        result = await db.execute(
            select(Tenant).order_by(Tenant.created_at.desc()).limit(min(limit, 200)).offset(offset)
        )
        return result.scalars().all()


@router.get("/stats/")
async def get_stats(db: AsyncSessionDep):
    async with db.begin():
        tenant_count = await db.execute(text("SELECT COUNT(*) FROM tenants"))
        return {"total_tenants": tenant_count.scalar()}
