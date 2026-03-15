"""ARQ job: retry failed email notifications."""
import logging
from datetime import datetime, timezone

import httpx
from sqlalchemy import select, text

from app.core.config import settings
from app.core.database import async_session
from app.models.notification import Notification, NotificationChannel, NotificationStatus

logger = logging.getLogger(__name__)

MAX_RETRIES = 3
RETRY_WINDOW_HOURS = 24


async def retry_failed_notifications(ctx: dict) -> None:
    """Retry FAILED email notifications, grouped by tenant_id to satisfy RLS.

    Skips notifications with retry_count >= MAX_RETRIES or older than RETRY_WINDOW_HOURS.
    """
    async with async_session() as db:
        async with db.begin():
            from app.models.tenant import Tenant
            tenant_result = await db.execute(select(Tenant.id))
            tenant_ids = [row[0] for row in tenant_result.fetchall()]

    for tenant_id in tenant_ids:
        await _retry_for_tenant(tenant_id)


async def _retry_for_tenant(tenant_id) -> None:
    """Process retryable notifications for a single tenant."""
    async with async_session() as db:
        async with db.begin():
            await db.execute(text(f"SET LOCAL app.current_tenant_id = '{tenant_id}'"))

            result = await db.execute(
                select(Notification).where(
                    Notification.tenant_id == tenant_id,
                    Notification.channel == NotificationChannel.EMAIL,
                    Notification.status == NotificationStatus.FAILED,
                    Notification.retry_count < MAX_RETRIES,
                    text(f"created_at > now() - interval '{RETRY_WINDOW_HOURS} hours'"),
                )
            )
            notifications = result.scalars().all()

            for notif in notifications:
                email_to = notif.payload.get("to")
                visitor_name = notif.payload.get("visitor_name", "visitor")

                if not email_to:
                    notif.retry_count += 1
                    continue

                try:
                    if not getattr(settings, "sendgrid_api_key", None):
                        raise ValueError("HABITARE_SENDGRID_API_KEY not configured")
                    async with httpx.AsyncClient() as client:
                        resp = await client.post(
                            "https://api.sendgrid.com/v3/mail/send",
                            headers={"Authorization": f"Bearer {settings.sendgrid_api_key}"},
                            json={
                                "personalizations": [{"to": [{"email": email_to}]}],
                                "from": {"email": getattr(settings, "from_email", "noreply@habitare.com")},
                                "subject": f"Visitor {visitor_name} has arrived",
                                "content": [{"type": "text/plain", "value": f"{visitor_name} has checked in."}],
                            },
                            timeout=10.0,
                        )
                        resp.raise_for_status()
                    notif.status = NotificationStatus.SENT
                    notif.sent_at = datetime.utcnow()
                    logger.info("Retried notification %s: SENT", notif.id)
                except Exception as exc:
                    notif.retry_count += 1
                    logger.warning("Retry failed for notification %s (attempt %d): %s", notif.id, notif.retry_count, exc)
