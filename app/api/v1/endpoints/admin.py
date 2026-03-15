"""Admin endpoints — SUPER_ADMIN only. No set_rls() — tenants table has no RLS."""
import uuid
from datetime import datetime

from fastapi import APIRouter, HTTPException
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError

from app.api.deps import AsyncSessionDep, RequireSuperAdminDep
from app.models.tenant import Tenant
from app.schemas.tenant import TenantCreate, TenantResponse, TenantUpdate

router = APIRouter(prefix="/admin", tags=["admin"])


@router.get("/tenants/", response_model=list[TenantResponse])
async def list_tenants(
    current_user: RequireSuperAdminDep,
    db: AsyncSessionDep,
    limit: int = 50,
    offset: int = 0,
):
    """List all tenants. SUPER_ADMIN only."""
    async with db.begin():
        result = await db.execute(
            select(Tenant).order_by(Tenant.created_at.desc()).limit(min(limit, 200)).offset(offset)
        )
        return result.scalars().all()


@router.get("/stats/")
async def get_stats(current_user: RequireSuperAdminDep, db: AsyncSessionDep):
    """Platform stats. SUPER_ADMIN only."""
    async with db.begin():
        tenant_count = await db.execute(text("SELECT COUNT(*) FROM tenants"))
        return {"total_tenants": tenant_count.scalar()}


@router.post("/tenants/", response_model=TenantResponse, status_code=201)
async def create_tenant(
    body: TenantCreate,
    current_user: RequireSuperAdminDep,
    db: AsyncSessionDep,
):
    """Create a new tenant. SUPER_ADMIN only. No set_rls() — tenants has no RLS."""
    tenant = Tenant(
        name=body.name,
        slug=body.slug,
        subscription_tier=body.subscription_tier,
        settings=body.settings,
    )
    try:
        async with db.begin():
            db.add(tenant)
    except IntegrityError:
        raise HTTPException(status_code=409, detail="Slug already in use")
    return tenant


@router.put("/tenants/{tenant_id}", response_model=TenantResponse)
async def update_tenant(
    tenant_id: uuid.UUID,
    body: TenantUpdate,
    current_user: RequireSuperAdminDep,
    db: AsyncSessionDep,
):
    """Update a tenant. SUPER_ADMIN only."""
    async with db.begin():
        result = await db.execute(select(Tenant).where(Tenant.id == tenant_id))
        tenant = result.scalar_one_or_none()
        if not tenant:
            raise HTTPException(status_code=404, detail="Tenant not found")

        if body.name is not None:
            tenant.name = body.name
        if body.subscription_tier is not None:
            tenant.subscription_tier = body.subscription_tier
        if body.settings is not None:
            tenant.settings = body.settings
        tenant.updated_at = datetime.utcnow()

    return tenant
