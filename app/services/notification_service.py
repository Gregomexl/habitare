"""Notification service — email dispatch + WebSocket broadcast.

No retry logic in Phase 2. Failed sends are logged with status=FAILED.
Do NOT use BackgroundTasks for retry — it doesn't support backoff.
"""
import uuid
from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.ws_manager import ws_manager
from app.models.notification import Notification, NotificationChannel, NotificationStatus


class NotificationService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def notify_checkin(
        self,
        *,
        tenant_id: uuid.UUID,
        visit_id: uuid.UUID,
        host_id: uuid.UUID | None,
        visitor_name: str,
        host_email: str | None,
    ) -> None:
        """Fire email (if host set) and WebSocket broadcast."""
        # Email — skipped if no host
        if host_id and host_email:
            await self._send_email(
                tenant_id=tenant_id,
                visit_id=visit_id,
                host_id=host_id,
                host_email=host_email,
                visitor_name=visitor_name,
            )

        # WebSocket — broadcast to all staff in tenant
        await self._broadcast_ws(
            tenant_id=tenant_id,
            visit_id=visit_id,
            visitor_name=visitor_name,
        )

    async def _send_email(
        self,
        *,
        tenant_id: uuid.UUID,
        visit_id: uuid.UUID,
        host_id: uuid.UUID,
        host_email: str,
        visitor_name: str,
    ) -> None:
        """Send check-in email notification. Logs result to notifications table."""
        notification = Notification(
            tenant_id=tenant_id,
            visit_id=visit_id,
            channel=NotificationChannel.EMAIL,
            recipient_id=host_id,
            payload={"to": host_email, "visitor_name": visitor_name},
            status=NotificationStatus.QUEUED,
        )
        self.db.add(notification)
        await self.db.flush()

        try:
            # Phase 2: HTTP POST to SendGrid Mail Send API
            # Requires HABITARE_SENDGRID_API_KEY in settings
            # and HABITARE_FROM_EMAIL for the sender address.
            # If settings.sendgrid_api_key is empty, raises ValueError → FAILED logged.
            import httpx
            from app.core.config import settings
            if not getattr(settings, "sendgrid_api_key", None):
                raise ValueError("HABITARE_SENDGRID_API_KEY not configured")
            async with httpx.AsyncClient() as client:
                resp = await client.post(
                    "https://api.sendgrid.com/v3/mail/send",
                    headers={"Authorization": f"Bearer {settings.sendgrid_api_key}"},
                    json={
                        "personalizations": [{"to": [{"email": host_email}]}],
                        "from": {"email": getattr(settings, "from_email", "noreply@habitare.com")},
                        "subject": f"Visitor {visitor_name} has arrived",
                        "content": [{"type": "text/plain", "value": f"{visitor_name} has checked in."}],
                    },
                    timeout=10.0,
                )
                resp.raise_for_status()
            notification.status = NotificationStatus.SENT
            notification.sent_at = datetime.now(timezone.utc)
        except Exception as exc:
            import logging
            logging.getLogger(__name__).warning("Email send failed for visit %s: %s", visit_id, exc)
            notification.status = NotificationStatus.FAILED

        await self.db.flush()

    async def _broadcast_ws(
        self,
        *,
        tenant_id: uuid.UUID,
        visit_id: uuid.UUID,
        visitor_name: str,
    ) -> None:
        """Broadcast check-in event to all connected staff. Fire-and-forget."""
        notification = Notification(
            tenant_id=tenant_id,
            visit_id=visit_id,
            channel=NotificationChannel.WEBSOCKET,
            recipient_id=None,
            payload={"visitor_name": visitor_name, "visit_id": str(visit_id)},
            status=NotificationStatus.QUEUED,
        )
        self.db.add(notification)
        await self.db.flush()

        try:
            await ws_manager.broadcast(
                tenant_id,
                {"event": "visitor_checked_in", "visitor_name": visitor_name, "visit_id": str(visit_id)},
            )
            notification.status = NotificationStatus.SENT
            notification.sent_at = datetime.now(timezone.utc)
        except Exception:
            notification.status = NotificationStatus.FAILED

        await self.db.flush()
