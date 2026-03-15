import uuid
import logging
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from sqlalchemy import select
from app.api.deps import AsyncSessionDep, CurrentUserDep, set_rls
from app.core.jwt import decode_token
from app.core.ws_manager import ws_manager
from app.models.notification import Notification
from app.schemas.notification import NotificationResponse

logger = logging.getLogger(__name__)
router = APIRouter(tags=["notifications"])

# WebSocket close codes (application-defined, 4000-4999 range per RFC 6455)
_WS_UNAUTHORIZED = 4001  # Invalid or expired JWT


@router.websocket("/ws/dashboard")
async def dashboard_ws(websocket: WebSocket, token: str):
    """Real-time check-in event stream for staff dashboard.

    Auth: pass JWT access token as ?token=<jwt> query param.
    Browser WebSocket API does not support custom headers.
    Close code 4001 = Unauthorized (application-defined).
    """
    try:
        payload = decode_token(token)
        tenant_id = uuid.UUID(payload["tenant_id"])
    except Exception:
        await websocket.close(code=_WS_UNAUTHORIZED)
        return

    await ws_manager.connect(tenant_id, websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        ws_manager.disconnect(tenant_id, websocket)


@router.get("/notifications/", response_model=list[NotificationResponse])
async def list_notifications(
    db: AsyncSessionDep,
    current_user: CurrentUserDep,
    limit: int = 50,
    offset: int = 0,
):
    async with db.begin():
        await set_rls(db, current_user.tenant_id)
        result = await db.execute(
            select(Notification)
            .order_by(Notification.created_at.desc())
            .limit(min(limit, 200))
            .offset(offset)
        )
        return result.scalars().all()
