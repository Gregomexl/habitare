"""ARQ worker entry point.

Run with: uv run arq app.worker.WorkerSettings
"""
from arq import cron
from arq.connections import RedisSettings

from app.core.config import settings
from app.jobs.cleanup_tokens import cleanup_expired_tokens
from app.jobs.retry_notifications import retry_failed_notifications


class WorkerSettings:
    redis_settings = RedisSettings.from_dsn(settings.redis_url)

    functions = [
        retry_failed_notifications,
        cleanup_expired_tokens,
    ]

    cron_jobs = [
        cron(retry_failed_notifications, minute={0, 5, 10, 15, 20, 25, 30, 35, 40, 45, 50, 55}),
        cron(cleanup_expired_tokens, hour=3, minute=0),
    ]
