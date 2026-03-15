import uuid
from datetime import datetime, timedelta, timezone
from fastapi import APIRouter, HTTPException
from sqlalchemy import select
from app.api.deps import AsyncSessionDep, CurrentUserDep, set_rls
from app.models.qr_code import QRCode, QRCodeType
from app.schemas.visit import VisitCreate, VisitResponse
from app.services.visit_service import VisitService, VisitStateError
from app.services.invitation_service import InvitationService

router = APIRouter(prefix="/visits", tags=["visits"])


def _make_qr(visit_id: uuid.UUID, tenant_id: uuid.UUID, scheduled_at: datetime | None) -> QRCode:
    now = datetime.now(timezone.utc)
    if scheduled_at:
        qr_type = QRCodeType.TIME_BOUNDED
        valid_from = scheduled_at - timedelta(hours=1)
        valid_until = scheduled_at + timedelta(minutes=30)
    else:
        qr_type = QRCodeType.ONE_TIME
        valid_from = now
        valid_until = now + timedelta(minutes=30)
    return QRCode(
        tenant_id=tenant_id,
        visit_id=visit_id,
        type=qr_type,
        valid_from=valid_from,
        valid_until=valid_until,
    )


@router.post("/", response_model=VisitResponse, status_code=201)
async def create_visit(body: VisitCreate, db: AsyncSessionDep, current_user: CurrentUserDep):
    async with db.begin():
        await set_rls(db, current_user.tenant_id)
        service = VisitService(db)
        visit = await service.create(
            tenant_id=current_user.tenant_id,
            visitor_id=body.visitor_id,
            host_id=body.host_id,
            purpose=body.purpose,
            scheduled_at=body.scheduled_at,
        )
        qr = _make_qr(visit.id, current_user.tenant_id, body.scheduled_at)
        db.add(qr)
        inv_service = InvitationService(db)
        await inv_service.create(tenant_id=current_user.tenant_id, visit_id=visit.id)
        await db.flush()
    return visit


@router.get("/", response_model=list[VisitResponse])
async def list_visits(
    db: AsyncSessionDep,
    current_user: CurrentUserDep,
    status: str | None = None,
    limit: int = 50,
    offset: int = 0,
):
    from app.models.visit import VisitStatus
    async with db.begin():
        await set_rls(db, current_user.tenant_id)
        service = VisitService(db)
        try:
            visit_status = VisitStatus(status) if status else None
        except ValueError:
            raise HTTPException(status_code=422, detail=f"Invalid status value: {status}")
        return await service.list(status=visit_status, limit=min(limit, 200), offset=offset)


@router.get("/{visit_id}", response_model=VisitResponse)
async def get_visit(visit_id: uuid.UUID, db: AsyncSessionDep, current_user: CurrentUserDep):
    async with db.begin():
        await set_rls(db, current_user.tenant_id)
        service = VisitService(db)
        visit = await service.get_by_id(visit_id)
    if not visit:
        raise HTTPException(status_code=404, detail="Visit not found")
    return visit


@router.post("/{visit_id}/check-in", response_model=VisitResponse)
async def check_in(visit_id: uuid.UUID, db: AsyncSessionDep, current_user: CurrentUserDep):
    async with db.begin():
        await set_rls(db, current_user.tenant_id)
        service = VisitService(db)
        visit = await service.get_by_id(visit_id)
        if not visit:
            raise HTTPException(status_code=404, detail="Visit not found")
        try:
            visit = await service.check_in(visit.id)
        except VisitStateError as e:
            raise HTTPException(status_code=409, detail=str(e))
    return visit


@router.post("/{visit_id}/check-out", response_model=VisitResponse)
async def check_out(visit_id: uuid.UUID, db: AsyncSessionDep, current_user: CurrentUserDep):
    async with db.begin():
        await set_rls(db, current_user.tenant_id)
        service = VisitService(db)
        visit = await service.get_by_id(visit_id)
        if not visit:
            raise HTTPException(status_code=404, detail="Visit not found")
        try:
            visit = await service.check_out(visit.id)
        except VisitStateError as e:
            raise HTTPException(status_code=409, detail=str(e))
    return visit


@router.post("/{visit_id}/cancel", response_model=VisitResponse)
async def cancel_visit(visit_id: uuid.UUID, db: AsyncSessionDep, current_user: CurrentUserDep):
    async with db.begin():
        await set_rls(db, current_user.tenant_id)
        service = VisitService(db)
        visit = await service.get_by_id(visit_id)
        if not visit:
            raise HTTPException(status_code=404, detail="Visit not found")
        try:
            visit = await service.cancel(visit.id)
        except VisitStateError as e:
            raise HTTPException(status_code=409, detail=str(e))
    return visit
