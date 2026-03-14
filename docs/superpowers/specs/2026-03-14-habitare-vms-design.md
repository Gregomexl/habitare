# Habitare VMS — Phase 2 Design Spec

**Date:** 2026-03-14
**Project:** Habitare QR-Based Visitor Management System
**Phase:** 2 — Visitor Management Core
**Stack:** FastAPI · PostgreSQL 17 (RLS) · SQLAlchemy 2.0 async · Python 3.13

---

## Prerequisites

Phase 1 auth endpoints must be complete before Phase 2 implementation starts:
- `POST /auth/login` (JWT issue)
- `POST /auth/refresh` (refresh token rotation)
- `POST /auth/logout`
- `GET /users/me`

All of these are planned in `PHASE_1_PLAN.md` stages 2.1–2.6 and must be shipped first.

---

## Overview

Phase 2 implements the core Visitor Management System on top of the Phase 1 authentication foundation. The system handles two first-class visitor flows — pre-registration and walk-in — converging at a shared QR-based check-in mechanism. Visitors receive a shareable pass link (displayable on their phone or saveable as an image) which staff scan using the web app camera.

---

## Architecture

**Pattern:** Modular Monolith — all features live in the existing FastAPI app as internal modules with strict boundaries. No new deployable services.

**Key principle:** Build on what exists. The `TenantMixin`, `AsyncSession` + RLS pattern, and `Annotated` dependency injection from Phase 1 are used unchanged across all new modules.

---

## Actors

| Role | Description | Auth |
|------|-------------|------|
| Visitor | External guest arriving at a property | No account — uses pass link token |
| Property Staff (`TENANT_USER`) | Reception desk, handles check-in | JWT |
| Property Admin (`PROPERTY_ADMIN`) | Configures tenant settings, manages staff | JWT |
| Super Admin (`SUPER_ADMIN`) | Habitare platform operator | JWT |

---

## Data Model

All new tables include `tenant_id` via `TenantMixin` with PostgreSQL RLS enforced via `SET LOCAL app.current_tenant_id`. This is the same pattern as Phase 1.

### New Tables

#### `visitors`
Reusable visitor profile. The same person visiting multiple times reuses one record.

**Deduplication rule:** If `email` is provided and matches an existing `visitor.email` within the same tenant, the existing record is reused — no new record created. Walk-ins with no email always create a new record.

| Field | Type | Notes |
|-------|------|-------|
| id | UUID PK | |
| tenant_id | UUID FK | RLS |
| name | str | required |
| email | str | nullable — used for deduplication |
| phone | str | nullable |
| photo_url | str | nullable, stored in object storage |
| vehicle_plate | str | nullable |
| created_at | datetime | |

#### `visits`
One record per visit event. Tracks the full lifecycle.

**Walk-in nullability:** `host_id` is nullable. Walk-in visitors may not have a specific host. When `host_id` is null, email notification is skipped — WebSocket notification to all connected staff is still fired.

**Walk-in vs scheduled:** `scheduled_at` is null for walk-ins. The `SCHEDULED` status for walk-ins means "registered but not yet scanned" — the QR is immediately valid and the first scan transitions to `CHECKED_IN`.

| Field | Type | Notes |
|-------|------|-------|
| id | UUID PK | |
| tenant_id | UUID FK | RLS |
| visitor_id | UUID FK → visitors | required |
| host_id | UUID FK → users | **nullable** — null for walk-ins with no specific host |
| purpose | str | |
| status | enum | SCHEDULED, CHECKED_IN, CHECKED_OUT, CANCELLED |
| scheduled_at | datetime | **nullable** — null for walk-ins |
| checked_in_at | datetime | nullable |
| checked_out_at | datetime | nullable |
| created_at | datetime | |

#### `qr_codes`
One QR code per visit. Type determines validation behavior.

**What the QR encodes:** The QR image encodes only the raw `code` UUID string — not a URL. Staff open the authenticated scanner view in the web app, point the camera at the visitor's phone screen, the browser extracts the UUID, and the app calls `GET /qr/{code}` with the staff's JWT. The visitor's phone never calls the scan endpoint directly.

**TIME_BOUNDED validity window:** Valid from 1 hour before `visit.scheduled_at` until 30 minutes after. This gives the visitor a grace window while preventing codes from being valid all day.

**ONE_TIME validity window:** Valid for 30 minutes from creation time.

| Field | Type | Notes |
|-------|------|-------|
| id | UUID PK | |
| tenant_id | UUID FK | RLS |
| visit_id | UUID FK → visits | |
| code | UUID | **UNIQUE constraint in DB** — used as the scannable token |
| type | enum | ONE_TIME, TIME_BOUNDED |
| valid_from | datetime | required |
| valid_until | datetime | required |
| used_at | datetime | nullable — set on first scan for ONE_TIME; nullable for TIME_BOUNDED |
| is_revoked | bool | default false |
| created_at | datetime | |

#### `invitations`
Pass link token. Created for both pre-reg and walk-in flows — it is the mechanism for delivering the pass link to the visitor regardless of channel.

**Status transitions:**
- `PENDING` → created, not yet opened
- `VIEWED` → visitor opened the pass link page (set on first `GET /pass/{token}` call)
- `EXPIRED` → `expires_at` passed or explicitly revoked via `POST /invitations/{id}/revoke`

There is no auto-transition to a separate "accepted" state — the QR scan itself (handled on `visits`) is the acceptance signal.

| Field | Type | Notes |
|-------|------|-------|
| id | UUID PK | |
| tenant_id | UUID FK | RLS |
| visit_id | UUID FK → visits | |
| sent_to_email | str | nullable |
| token | str | signed value, used in pass link URL |
| status | enum | PENDING, VIEWED, EXPIRED |
| sent_at | datetime | nullable |
| expires_at | datetime | |
| created_at | datetime | |

#### `notifications`
Audit log of staff-facing notifications (email to host + WebSocket to dashboard). Visitor-facing communications (pass link delivery) are not logged here — they are tracked via `invitations.sent_at`.

**`recipient_id` nullability:** Nullable. Null when `visit.host_id` is null (walk-in with no specific host). WebSocket notifications to all connected staff are logged with `recipient_id = null` and `channel = WEBSOCKET`.

| Field | Type | Notes |
|-------|------|-------|
| id | UUID PK | |
| tenant_id | UUID FK | RLS |
| visit_id | UUID FK → visits | |
| channel | enum | EMAIL, WEBSOCKET |
| recipient_id | UUID FK → users | **nullable** — null for broadcast WS or when host is absent |
| status | enum | QUEUED, SENT, FAILED |
| payload | JSONB | |
| sent_at | datetime | nullable |
| created_at | datetime | |

---

## API Structure

All routes under `/api/v1/`. Role annotations show minimum required role. All list endpoints accept `limit` (default 50, max 200) and `offset` (default 0) query params.

### Existing (Phase 1 shells — prerequisite)
```
POST /auth/login
POST /auth/refresh
POST /auth/logout
GET  /users/me
PUT  /users/me
GET  /users/          [PROPERTY_ADMIN]
POST /users/          [PROPERTY_ADMIN]
```

### Visitors
```
GET  /visitors/       [TENANT_USER] list — ?search=, limit, offset
POST /visitors/       [TENANT_USER] create or return existing (email dedup)
GET  /visitors/{id}   [TENANT_USER]
PUT  /visitors/{id}   [TENANT_USER]
```

### Visits
```
GET  /visits/                    [TENANT_USER] list — ?status=, ?date=, limit, offset
POST /visits/                    [TENANT_USER] create (scheduled or walk-in)
GET  /visits/{id}                [TENANT_USER]
POST /visits/{id}/check-in       [TENANT_USER]
POST /visits/{id}/check-out      [TENANT_USER]
POST /visits/{id}/cancel         [TENANT_USER]
```

### Invitations & Pass Link
```
POST /invitations/               [TENANT_USER] create invitation + return pass link
GET  /invitations/{id}           [TENANT_USER]
POST /invitations/{id}/revoke    [TENANT_USER] sets status=EXPIRED, revokes QR code

GET  /pass/{token}               PUBLIC — no auth — JSON response with visit snapshot
                                 Sets invitation.status = VIEWED on first call
                                 Frontend renders QR code + visitor info from this response
```

### QR Codes
```
GET  /qr/{code}              [TENANT_USER] scan endpoint — validates + triggers check-in
POST /qr/{visit_id}/generate [TENANT_USER] explicit QR generation (walk-in fast path)
POST /qr/{code}/revoke       [TENANT_USER]
GET  /qr/{code}/image.png    token-protected via invitation token param — raw PNG
```

`GET /qr/{code}/image.png` accepts `?token={invitation_token}` query param for auth. The frontend pass page (`/pass/{token}`) uses the token it has to fetch and display the image.

### Notifications
```
WS  /ws/dashboard            [TENANT_USER] real-time check-in events
GET /notifications/          [TENANT_USER] notification history — limit, offset
```

### Super Admin
```
GET  /admin/tenants/         [SUPER_ADMIN]
POST /admin/tenants/         [SUPER_ADMIN]
PUT  /admin/tenants/{id}     [SUPER_ADMIN]
GET  /admin/stats/           [SUPER_ADMIN]
```

---

## Visit Flows

### Pre-Registration Flow

1. **Staff** creates visit via `POST /visits/` with `scheduled_at` → status: `SCHEDULED`
2. **System** auto-creates `invitation` + `TIME_BOUNDED` QR code (valid 1hr before → 30min after `scheduled_at`) → returns pass link `app.habitare.com/pass/{token}` in response
3. **Staff** copies pass link → shares via WhatsApp/any channel with visitor
4. **Visitor** opens link on phone → `GET /pass/{token}` returns JSON → frontend renders QR code, visitor name, host, date. Invitation status → `VIEWED`. Visitor can save QR image via "Save" button → `GET /qr/{code}/image.png?token={token}`
5. **Arrival:** Staff opens scanner view in web app (camera) → scans visitor's phone screen → browser extracts UUID from QR → calls `GET /qr/{code}` [JWT]
   - Validates: not revoked, within time window
   - Sets `checked_in_at`, visit status → `CHECKED_IN`
   - Fires email (if host_id set) + WebSocket notification
6. **Departure:** Staff taps check-out → `POST /visits/{id}/check-out` → `CHECKED_OUT`

### Walk-In Flow

1. **Visitor arrives unannounced.** Staff registers visitor details in web app
2. **Staff** creates visit via `POST /visits/` without `scheduled_at` → status: `SCHEDULED`, `host_id` nullable
3. **System** auto-creates `ONE_TIME` QR code (valid 30 min from now) + invitation with pass link
4. **Staff** copies pass link → shares with visitor on the spot (WhatsApp/shows screen)
5. **Visitor** opens link, sees QR code, optionally saves image
6. **Scan:** Same as step 5 above — `GET /qr/{code}` validates ONE_TIME (rejects if already used)
   - Sets `used_at`, visit status → `CHECKED_IN`
   - Fires WebSocket to all connected staff; email skipped if `host_id` is null
7. **Departure:** Same check-out flow

---

## QR Validation Logic

Implemented in `QRService.validate_and_consume(code, tenant_id)`:

1. Code exists? If not → 404
2. Belongs to tenant? (RLS enforces this at DB level — no explicit check needed)
3. `is_revoked = true`? → 410 Gone
4. `TIME_BOUNDED`: `valid_from ≤ now ≤ valid_until`? If not → 403 Expired
5. `ONE_TIME`: `used_at is None`? If not → 409 Already Used
6. All pass → set `used_at = now`, call `VisitService.check_in(visit_id)`, call `NotificationService.notify_checkin(visit_id, tenant_id)`

---

## Notification Pipeline

Triggered from `NotificationService.notify_checkin(visit_id, tenant_id)` after check-in is committed.

**Retry policy:** No automatic retry in Phase 2. Failed sends are logged to `notifications` with `status = FAILED`. Phase 3 will add ARQ-based retry using the Redis already in the stack. Do not implement retry inside `BackgroundTasks` — it does not support backoff.

### Email
- Provider: SendGrid (configurable to SMTP via settings)
- Recipient: `visit.host_id` user's email
- **Skipped** if `visit.host_id` is null
- Delivery: `BackgroundTasks.add_task()` (off request path, no retry in Phase 2)
- Toggled per tenant: `tenant.settings.email_enabled: bool`

### WebSocket
- Endpoint: `WS /ws/dashboard`
- Pattern: in-process `ConnectionManager` singleton — `dict[uuid, list[WebSocket]]` keyed by `tenant_id`
- Location: `app/core/ws_manager.py` (global state, not a service)
- Payload: visit snapshot JSON
- Broadcast to all staff connected to the tenant's dashboard
- Fire-and-forget (use `GET /notifications/` for audit history)

### SMS
Not implemented in Phase 2. Replaced by shareable pass link (WhatsApp-friendly).

---

## Pass Link Page (`/pass/{token}`)

Public JSON endpoint: `GET /api/v1/pass/{token}`

Response:
```json
{
  "visitor_name": "Jane Smith",
  "host_name": "Carlos Reyes",
  "scheduled_at": "2026-03-15T10:00:00Z",
  "qr_code_url": "/api/v1/qr/{code}/image.png?token={token}",
  "expires_at": "2026-03-15T10:30:00Z"
}
```

The frontend renders this as a full-screen pass page. The `qr_code_url` is used by the frontend to display the QR image. "Save image" button triggers a download of the PNG.

On first call: sets `invitation.status = VIEWED`.
If token is expired or revoked: returns 410 with `{"detail": "This pass link has expired."}`.

---

## Module Structure

```
app/
  api/v1/endpoints/
    auth.py               ← Phase 1
    users.py              ← Phase 1
    visitors.py           ← NEW
    visits.py             ← NEW
    invitations.py        ← NEW (includes /pass/{token})
    qr.py                 ← NEW
    notifications.py      ← NEW
    admin.py              ← NEW
  core/
    ws_manager.py         ← NEW (ConnectionManager singleton, global state)
  models/
    visitor.py            ← NEW
    visit.py              ← NEW
    qr_code.py            ← NEW
    invitation.py         ← NEW
    notification.py       ← NEW
  schemas/
    visitor.py            ← NEW
    visit.py              ← NEW
    qr_code.py            ← NEW
    invitation.py         ← NEW
  services/
    visitor_service.py    ← NEW (includes email dedup logic)
    visit_service.py      ← NEW
    qr_service.py         ← NEW (validate_and_consume)
    invitation_service.py ← NEW
    notification_service.py ← NEW
```

---

## Testing Strategy

- **Unit:** `qr_service.validate_and_consume` (expiry, ONE_TIME replay, revocation), `visitor_service` (email dedup), `notification_service` (null host_id guard)
- **Integration:** Full walk-in and pre-reg flows via `httpx` + real async test DB with RLS
- **Security:** Cross-tenant QR scan attempts (extend `tests/security/test_rls.py` pattern); expired token rejection on pass link
- **WebSocket:** `pytest-asyncio` + `starlette.testclient.TestClient`
- **QR generation:** Verify PNG output is scannable (decode generated PNG with a QR library in test)
- **Pagination:** Verify list endpoints respect `limit`/`offset` and never return unbounded results

---

## Out of Scope (Phase 2)

- SMS notifications (replaced by shareable pass link)
- Automatic retry for failed email notifications (Phase 3 — ARQ + Redis)
- Photo capture at check-in (Phase 3)
- Analytics dashboard (Phase 3)
- Printed badge generation
- Native mobile app
- Social login, 2FA, SSO (Phase 1 auth roadmap stages 3–5)
