"""ARQ job: delete expired and revoked refresh tokens."""
import logging
from sqlalchemy import text
from app.core.database import async_session

logger = logging.getLogger(__name__)


async def cleanup_expired_tokens(ctx: dict) -> None:
    """Delete refresh tokens that are expired (>30d) or revoked (>7d).

    refresh_tokens has no RLS — no SET LOCAL needed.
    """
    async with async_session() as db:
        async with db.begin():
            result = await db.execute(
                text(
                    "DELETE FROM refresh_tokens "
                    "WHERE expires_at < now() - interval '30 days' "
                    "   OR (revoked_at IS NOT NULL AND revoked_at < now() - interval '7 days') "
                    "RETURNING id"
                )
            )
            deleted = len(result.fetchall())
            logger.info("cleanup_expired_tokens: deleted %d tokens", deleted)
