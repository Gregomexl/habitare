# Habitare — Phase 6 Design Spec

**Date:** 2026-03-15
**Project:** Habitare QR-Based Visitor Management System
**Phase:** 6 — Admin UI (Next.js Dashboard)
**Stack:** Next.js 15 · App Router · React 19 · Tailwind CSS · shadcn/ui · TanStack Query · TanStack Table

---

## Goal

Build a client-side admin dashboard that lets property staff manage visits, visitors, invitations, and users via the existing FastAPI backend (Phases 1–5). The UI runs in the browser; the backend is unchanged.

---

## Scope

### In scope

- **Login page** — email + password form, JWT stored in localStorage, redirect to dashboard on success
- **Visits page** — list of today's check-ins (default landing), searchable/sortable DataTable
- **Visitors page** — list of all visitors for the tenant, DataTable
- **Invitations page** — list of QR invitations with status badges, DataTable
- **Users page** — list of tenant users (PROPERTY_ADMIN+ only), DataTable, create/deactivate actions
- **Settings page** — current user profile edit form
- **Collapsible sidebar** — icon-only collapse, role-based nav item visibility
- **Auth protection** — client-side redirect to `/login` when no token; 401 response clears session
- **Shared API client** — single `lib/api.ts` fetch wrapper with auth header injection and error envelope parsing

### Out of scope

- Resident-facing QR scan screen (separate app, Phase 8)
- Real-time WebSocket updates (Phase 8)
- Email template preview
- Tenant creation UI (SUPER_ADMIN only, CLI/migration for now)
- Mobile-native app
- Dark/light mode toggle (dark-only)

---

## Architecture

### Repository layout

The frontend lives at `frontend/` inside the existing monorepo. The FastAPI backend and Next.js frontend are separate processes; the frontend calls the API over HTTP.

```
habitare/
  app/                  # FastAPI backend (unchanged)
  frontend/             # Next.js app (new)
    app/
    components/
    lib/
    providers.tsx
  docker-compose.yml    # backend infra only; frontend runs via npm
```

### Next.js configuration

- **App Router** with route groups: `(auth)` for public pages, `(dashboard)` for protected pages
- All components are `"use client"` — no server components, no server actions, no RSC data fetching. This keeps the auth model simple (localStorage) and avoids the mismatch between server-rendered HTML and client auth state.
- `NEXT_PUBLIC_API_URL` env var points to the FastAPI server (e.g., `http://localhost:8001` in dev, `https://habitare.yourdomain.com` in production)

### Auth flow

1. User submits login form → `POST /auth/login` → receive `{ access_token, refresh_token }`
2. Both tokens written to `localStorage`
3. `AuthContext` decodes the JWT (no signature verify — we trust our own API) to extract `user_id`, `tenant_id`, `role`, `email`
4. `<ProtectedRoute>` in `(dashboard)/layout.tsx` reads `AuthContext`; if no token → `redirect('/login')`
5. On 401 from any API call → `api.ts` clears localStorage and calls `window.location.href = '/login'`
6. Logout → `POST /auth/logout` → clear localStorage → redirect to `/login`

No cookie, no server session, no middleware. The `middleware.ts` file is omitted — client-side protection is sufficient for an admin-only internal tool.

### API client (`lib/api.ts`)

Single `apiFetch` function:
- Prepends `NEXT_PUBLIC_API_URL`
- Reads `access_token` from `localStorage` and injects `Authorization: Bearer <token>`
- Parses the Phase 5 error envelope `{ error: { code, message, detail, request_id } }`
- On 401: clears localStorage, redirects to `/login`
- Returns typed JSON or throws `ApiError` with `{ code, message, detail, status }`

No axios, no SWR — `fetch` + TanStack Query for caching/loading states.

### State management

- **Auth state**: React context (`AuthContext`) — `{ user, token, login, logout, isLoading }`
- **Server state**: TanStack Query (`@tanstack/react-query`) — one query per page, invalidation on mutations
- **Local UI state**: `useState` per component — no global store needed

### Component architecture

```
frontend/
  app/
    (auth)/
      login/
        page.tsx                  # Login form
    (dashboard)/
      layout.tsx                  # AppLayout + ProtectedRoute wrapper
      page.tsx                    # Redirect → /visits
      visits/page.tsx             # Visits DataTable
      visitors/page.tsx           # Visitors DataTable
      invitations/page.tsx        # Invitations DataTable
      users/page.tsx              # Users DataTable (PROPERTY_ADMIN+)
      settings/page.tsx           # Profile edit form
  components/
    ui/                           # shadcn/ui generated components
    layout/
      AppLayout.tsx               # SidebarProvider + AppSidebar + main content
      AppSidebar.tsx              # shadcn Sidebar, nav items, role filtering
      ProtectedRoute.tsx          # Reads auth, redirects if no token
      UserMenu.tsx                # Avatar dropdown (profile, logout)
    data-table/
      DataTable.tsx               # Generic TanStack Table wrapper
      columns/
        visits.tsx                # ColumnDef[] for visits
        visitors.tsx              # ColumnDef[] for visitors
        invitations.tsx           # ColumnDef[] for invitations
        users.tsx                 # ColumnDef[] for users
    forms/
      LoginForm.tsx               # Controlled form, react-hook-form + zod
      CreateUserForm.tsx          # Modal form for POST /users/
      SettingsForm.tsx            # Profile update form
  lib/
    api.ts                        # apiFetch wrapper
    auth.ts                       # AuthContext, useAuth hook, token decode
    utils.ts                      # cn(), formatDate(), statusBadgeVariant()
  providers.tsx                   # QueryClientProvider + AuthProvider
```

---

## Design System

### Color palette (dark-only)

| Token | Value | Use |
|---|---|---|
| Background | `#09090B` | Page background |
| Card | `#111113` | Card, sidebar, table row |
| Border | `#27272A` | Dividers, inputs |
| Primary | `#EAB308` (amber-500) | CTA buttons, active nav, accent |
| Text | `#FAFAFA` | Primary text |
| Muted | `#A1A1AA` | Secondary text, placeholders |
| Success | `#22C55E` | SENT / CHECKED_IN badges |
| Warning | `#F97316` | PENDING badges |
| Danger | `#EF4444` | FAILED / inactive badges |

Applied via Tailwind CSS custom theme extension in `tailwind.config.ts`. shadcn components configured with `zinc` base and overridden CSS variables to match.

### Sidebar

- `shadcn/ui Sidebar` with `collapsible="icon"` — collapses to icon-only at narrow viewports
- Nav items: Visits (CalendarDays icon), Visitors (Users icon), Invitations (QrCode icon), Users (Shield icon — hidden if role is `TENANT_USER`), Settings (Settings icon)
- Active item highlighted with primary amber background
- User avatar + name in sidebar footer; click → logout

### Data tables

All list views share the `<DataTable>` component:
- TanStack Table with client-side sorting, column filtering, pagination (10 rows/page)
- Search input above table (filters by primary text column)
- Column headers clickable for sort (asc/desc/none)
- Status columns render `<Badge>` with color from `statusBadgeVariant()`
- Actions column (where applicable) renders a `<DropdownMenu>` per row

---

## Pages

### Login (`/login`)

- Email + password inputs, submit button
- On success: store tokens, redirect to `/visits`
- On error: show error message from API envelope
- Form validation: `react-hook-form` + `zod` (email format, non-empty password)

### Visits (`/visits`) — default landing

- DataTable of visits: Visitor name, Unit, Check-in time, Status, Host
- Default filter: today's date (passed as query param to API)
- Date picker above table to change the day
- Status badge: CHECKED_IN (success), PENDING (warning), CHECKED_OUT (muted)

### Visitors (`/visitors`)

- DataTable: Full name, Email, Phone, Unit, Last visit date
- Search by name or email
- Click row → visit history panel (slide-over or drawer)

### Invitations (`/invitations`)

- DataTable: Host, Visitor name, Created at, Expires at, Status
- Status badge: ACTIVE (success), EXPIRED (muted), USED (muted), CANCELLED (danger)
- "Create invitation" button → modal form (host, visitor email, expiry)

### Users (`/users`) — PROPERTY_ADMIN+ only

- DataTable: Name, Email, Role badge, Status (Active/Inactive)
- "Add user" button → modal form (email, name, role)
- Row action: Deactivate / Reactivate (PATCH via `PUT /users/{id}`)
- If `TENANT_USER` hits this page → redirect to `/visits`

### Settings (`/settings`)

- Profile form: Full name, Phone number, Unit number
- Save button → `PUT /users/me`
- Show current email (read-only) and role (read-only)

---

## API Mapping

| Page | Method | Endpoint |
|---|---|---|
| Login | POST | `/auth/login` |
| Logout | POST | `/auth/logout` |
| Visits | GET | `/visits/?date=YYYY-MM-DD` |
| Visitors | GET | `/visitors/` |
| Invitations | GET | `/invitations/` |
| Create invitation | POST | `/invitations/` |
| Users | GET | `/users/` |
| Create user | POST | `/users/` |
| Update user | PUT | `/users/{id}` |
| Profile | GET | `/users/me` |
| Update profile | PUT | `/users/me` |

---

## Error Handling

All API errors are caught in `apiFetch` and thrown as `ApiError`. Each page/mutation:
- Loading state: skeleton rows in DataTable, spinner on buttons
- API error: `toast` notification with `error.message` from envelope
- 401: automatic redirect to login (handled in `api.ts`)
- Validation error (422): form field errors shown inline via react-hook-form

---

## Files Created

| File | Purpose |
|---|---|
| `frontend/package.json` | Next.js 15, React 19, Tailwind, shadcn, TanStack |
| `frontend/tailwind.config.ts` | Custom color palette |
| `frontend/components.json` | shadcn config |
| `frontend/app/layout.tsx` | Root layout with `<Providers>` |
| `frontend/providers.tsx` | QueryClientProvider + AuthProvider |
| `frontend/lib/api.ts` | Fetch wrapper |
| `frontend/lib/auth.ts` | AuthContext, useAuth, decodeToken |
| `frontend/lib/utils.ts` | cn(), formatDate(), statusBadgeVariant() |
| `frontend/components/layout/AppLayout.tsx` | Root dashboard layout |
| `frontend/components/layout/AppSidebar.tsx` | Collapsible sidebar with role filtering |
| `frontend/components/layout/ProtectedRoute.tsx` | Auth guard |
| `frontend/components/layout/UserMenu.tsx` | Avatar dropdown |
| `frontend/components/data-table/DataTable.tsx` | Generic TanStack Table |
| `frontend/components/data-table/columns/visits.tsx` | Visits column defs |
| `frontend/components/data-table/columns/visitors.tsx` | Visitors column defs |
| `frontend/components/data-table/columns/invitations.tsx` | Invitations column defs |
| `frontend/components/data-table/columns/users.tsx` | Users column defs |
| `frontend/components/forms/LoginForm.tsx` | Login form |
| `frontend/components/forms/CreateUserForm.tsx` | Create user modal form |
| `frontend/components/forms/SettingsForm.tsx` | Profile update form |
| `frontend/app/(auth)/login/page.tsx` | Login page |
| `frontend/app/(dashboard)/layout.tsx` | Dashboard layout + ProtectedRoute |
| `frontend/app/(dashboard)/page.tsx` | Root redirect → /visits |
| `frontend/app/(dashboard)/visits/page.tsx` | Visits page |
| `frontend/app/(dashboard)/visitors/page.tsx` | Visitors page |
| `frontend/app/(dashboard)/invitations/page.tsx` | Invitations page |
| `frontend/app/(dashboard)/users/page.tsx` | Users page |
| `frontend/app/(dashboard)/settings/page.tsx` | Settings page |

---

## Security Decisions

| Decision | Choice | Reason |
|---|---|------|
| Auth storage | localStorage | Internal admin tool; simpler than cookie/session; acceptable for property staff on managed devices |
| Token decode | No signature verify | Frontend can't hold the secret; we trust our own API already validated the token |
| Route protection | Client-side only | No server-rendered sensitive data; all data gated by backend auth |
| Role filtering | JWT `role` claim | Claim set by backend at login; frontend uses for UI only, not security |
| API errors | Envelope parse | Phase 5 standardized all errors; frontend reads `error.code` + `error.message` |
