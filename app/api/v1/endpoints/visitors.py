import uuid
from fastapi import APIRouter, HTTPException
from app.api.deps import AsyncSessionDep, CurrentUserDep, set_rls
from app.schemas.visitor import VisitorCreate, VisitorUpdate, VisitorResponse
from app.services.visitor_service import VisitorService

router = APIRouter(prefix="/visitors", tags=["visitors"])


@router.post("/", response_model=VisitorResponse, status_code=201)
async def create_visitor(body: VisitorCreate, db: AsyncSessionDep, current_user: CurrentUserDep):
    async with db.begin():
        await set_rls(db, current_user.tenant_id)
        service = VisitorService(db)
        visitor = await service.create_or_get(
            tenant_id=current_user.tenant_id,
            name=body.name,
            email=body.email,
            phone=body.phone,
            vehicle_plate=body.vehicle_plate,
        )
    return visitor


@router.get("/", response_model=list[VisitorResponse])
async def list_visitors(
    db: AsyncSessionDep,
    current_user: CurrentUserDep,
    search: str | None = None,
    limit: int = 50,
    offset: int = 0,
):
    async with db.begin():
        await set_rls(db, current_user.tenant_id)
        service = VisitorService(db)
        return await service.list(search=search, limit=min(limit, 200), offset=offset)


@router.get("/{visitor_id}", response_model=VisitorResponse)
async def get_visitor(visitor_id: uuid.UUID, db: AsyncSessionDep, current_user: CurrentUserDep):
    async with db.begin():
        await set_rls(db, current_user.tenant_id)
        service = VisitorService(db)
        visitor = await service.get_by_id(visitor_id)
    if not visitor:
        raise HTTPException(status_code=404, detail="Visitor not found")
    return visitor


@router.put("/{visitor_id}", response_model=VisitorResponse)
async def update_visitor(
    visitor_id: uuid.UUID,
    body: VisitorUpdate,
    db: AsyncSessionDep,
    current_user: CurrentUserDep,
):
    async with db.begin():
        await set_rls(db, current_user.tenant_id)
        service = VisitorService(db)
        visitor = await service.get_by_id(visitor_id)
        if not visitor:
            raise HTTPException(status_code=404, detail="Visitor not found")
        visitor = await service.update(
            visitor, name=body.name, phone=body.phone, vehicle_plate=body.vehicle_plate
        )
    return visitor
