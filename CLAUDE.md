# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Habitare is a QR-based visitor management system built with FastAPI and PostgreSQL. It is in early development (Phase 1: Authentication & Data Persistence). The core architectural concern is **multi-tenancy**: each tenant is a property/building, and all data is isolated using PostgreSQL Row-Level Security (RLS).

## Commands

All commands use `uv` as the package manager.

```bash
# Install dependencies
uv sync

# Start infrastructure (PostgreSQL 17, Redis 7)
docker-compose up -d

# Run application
uv run uvicorn app.main:app --reload

# Database migrations
alembic upgrade head
alembic downgrade -1
alembic revision --autogenerate -m "Description"

# Run all tests
uv run pytest tests/

# Run a single test file
uv run pytest tests/security/test_rls.py -v

# Run a single test
uv run pytest tests/test_models.py::test_name -v
```

## Architecture

### Multi-Tenancy via RLS

The entire application is multi-tenant. `Tenant` records represent properties/buildings. All domain models include `tenant_id` via `TenantMixin` (`app/models/base.py`).

Tenant isolation is enforced at the **database level** using PostgreSQL RLS — not the application layer. Before querying, the application sets a session-local variable:

```sql
SET LOCAL app.current_tenant_id = '<uuid>';
```

The RLS policy on the `users` table uses `current_setting('app.current_tenant_id', TRUE)` to restrict all reads and writes. Tests in `tests/security/test_rls.py` verify this isolation. The `tenant_context()` helper in `tests/conftest.py` manages this for tests.

### Async-First Stack

Everything is async:
- SQLAlchemy 2.0 with `AsyncSession` and `asyncpg` driver
- `Base` extends `AsyncAttrs` (required for async relationship loading)
- Session factory uses `expire_on_commit=False` to prevent detached instance errors
- Alembic migrations use `NullPool` to avoid connection pool issues during migrations

### Configuration

Settings are managed via `app/core/config.py` using `pydantic_settings.BaseSettings`. All env vars are prefixed with `HABITARE_`. The `.env` file is used for development; `.env.example` is the template.

### API Structure

- `app/main.py` — FastAPI app entry point with CORS and health check routes
- `app/api/deps.py` — Dependency injection (`get_db()` yields `AsyncSession`)
- `app/api/v1/endpoints/` — Route handlers (to be populated)
- `app/schemas/` — Pydantic request/response models (to be populated)
- `app/services/` — Business logic layer (to be populated)

### Models

- `User` — email + password (nullable for SSO), role (`TENANT_USER`, `PROPERTY_ADMIN`, `SUPER_ADMIN`), belongs to a tenant
- `Tenant` — property/building with subscription tier (`basic`, `pro`, `enterprise`) and JSONB `settings` field

### Security

- Passwords hashed with Argon2id (`argon2-cffi`)
- JWT tokens: HS256, 30-min access / 14-day refresh (configurable in settings)
- RLS on `users` table with `FORCE ROW LEVEL SECURITY`
- The database user `habitare_app` must be a non-superuser so RLS is enforced
