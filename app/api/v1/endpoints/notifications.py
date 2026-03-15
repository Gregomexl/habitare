import uuid
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from sqlalchemy import select
from app.api.deps import AsyncSessionDep, TenantIdDep, set_rls
from app.core.ws_manager import ws_manager
from app.models.notification import Notification
from app.schemas.notification import NotificationResponse

router = APIRouter(tags=["notifications"])


@router.websocket("/ws/dashboard")
async def dashboard_ws(websocket: WebSocket, tenant_id: str):
    """Real-time check-in event stream for staff dashboard."""
    try:
        tid = uuid.UUID(tenant_id)
    except ValueError:
        await websocket.close(code=1008)
        return

    await ws_manager.connect(tid, websocket)
    try:
        while True:
            # Keep connection alive — we only push, don't receive
            await websocket.receive_text()
    except WebSocketDisconnect:
        ws_manager.disconnect(tid, websocket)


@router.get("/notifications/", response_model=list[NotificationResponse])
async def list_notifications(
    db: AsyncSessionDep,
    tenant_id: TenantIdDep,
    limit: int = 50,
    offset: int = 0,
):
    async with db.begin():
        await set_rls(db, tenant_id)
        result = await db.execute(
            select(Notification)
            .order_by(Notification.created_at.desc())
            .limit(min(limit, 200))
            .offset(offset)
        )
        return result.scalars().all()
