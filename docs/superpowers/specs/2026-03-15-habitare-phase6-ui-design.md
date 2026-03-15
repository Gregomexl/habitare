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
- **Visitors page** — list of all visitors for the tenant, DataTable, visit history sheet per row
- **Invitations page** — list of QR invitations with status badges, DataTable, create invitation modal
- **Users page** — list of tenant users (PROPERTY_ADMIN+ only), DataTable, create/deactivate actions
- **Settings page** — current user profile edit form
- **Collapsible sidebar** — icon-only collapse, role-based nav item visibility
- **Auth protection** — client-side redirect to `/login` when no token; 401 tries refresh then redirects
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
    next.config.ts      # API proxy rewrites
    .env.local.example  # environment variable template
  docker-compose.yml    # backend infra only; frontend runs via npm
```

### `"use client"` propagation

Next.js App Router files are Server Components by default. In this application, **every file that uses browser APIs** (`localStorage`, `useState`, `useEffect`, `useContext`, TanStack Query hooks, react-hook-form) must carry the `"use client"` directive at the top. This includes all `components/` files, all page files that fetch data or read auth state, and `providers.tsx`.

The **only Server Components** in this app are:
- `frontend/app/layout.tsx` — root HTML shell, just wraps `<Providers>` and renders `{children}`; no browser APIs
- `frontend/app/(dashboard)/page.tsx` — root redirect; uses `redirect('/visits')` from `next/navigation`, which works in Server Components

Everything else is a Client Component. When in doubt, add `"use client"`.

### API proxy (`next.config.ts`)

In development, the Next.js dev server runs on port 3000 and the FastAPI server runs on port 8001. To avoid CORS issues, API calls are proxied through Next.js:

```ts
// frontend/next.config.ts
const nextConfig = {
  async rewrites() {
    return [
      {
        source: '/api/:path*',
        destination: `${process.env.NEXT_PUBLIC_API_URL}/:path*`,
      },
    ]
  },
}
export default nextConfig
```

`apiFetch` in `lib/api.ts` calls `/api/...` paths (not the FastAPI URL directly). In production, `NEXT_PUBLIC_API_URL` is an empty string and `/api/...` routes are reverse-proxied by the production web server (Cloudflare Tunnel / nginx). This keeps CORS out of the picture entirely.

### Auth flow

1. User submits login form → `POST /api/auth/login` → receive `{ access_token, refresh_token }`
2. Both tokens written to `localStorage` (`habitare_access_token`, `habitare_refresh_token`)
3. `AuthContext` decodes the access JWT (no signature verify — we trust our own API) to extract `user_id`, `tenant_id`, `role`, `email`
4. `<ProtectedRoute>` in `(dashboard)/layout.tsx` is a **Client Component** that runs in `useEffect`:
   - If no `access_token` in localStorage → `router.push('/login')` and render `null` until redirect completes
   - This avoids the SSR localStorage access error (localStorage is undefined on the server)
   - While auth is being checked (`isLoading: true` in AuthContext) → render a full-screen spinner, not content
5. On 401 from any API call → `api.ts` attempts token refresh via `POST /api/auth/refresh` with the `refresh_token`
   - If refresh succeeds: store new `access_token`, retry original request
   - If refresh fails (token expired or revoked): clear localStorage, `window.location.href = '/login'`
6. Logout → `POST /api/auth/logout` → clear localStorage → `router.push('/login')`

**Token lifetimes:** Access token expires in 30 minutes (backend setting). Refresh token expires in 14 days. Silent refresh via step 5 means the user stays logged in across the 30-minute boundary without manual re-login.

No cookie, no server session, no `middleware.ts`. Client-side protection is sufficient for an admin-only internal tool.

### API client (`lib/api.ts`)

Single `apiFetch` function:
- Prepends `/api` prefix (routes to FastAPI via Next.js proxy)
- Reads `habitare_access_token` from `localStorage` and injects `Authorization: Bearer <token>`
- Parses the Phase 5 error envelope `{ error: { code, message, detail, request_id } }`
- On 401: attempts silent refresh (see Auth flow step 5); on refresh failure, redirects to login
- Returns typed JSON or throws `ApiError` with `{ code, message, detail, status }`

```ts
// Shape of thrown error
class ApiError extends Error {
  constructor(
    public code: string,
    public message: string,
    public detail: unknown,
    public status: number,
  ) { super(message) }
}
```

No axios, no SWR — `fetch` + TanStack Query for caching/loading states.

### shadcn/ui configuration

`components.json` values:

```json
{
  "style": "default",
  "rsc": false,
  "tailwind": {
    "config": "tailwind.config.ts",
    "css": "app/globals.css",
    "baseColor": "zinc",
    "cssVariables": true
  },
  "aliases": {
    "components": "@/components",
    "utils": "@/lib/utils"
  }
}
```

`rsc: false` because this app has no React Server Components that render shadcn components.

### Color system

Colors are applied via **CSS variables in `app/globals.css`** (the shadcn standard mechanism), not via Tailwind theme extension. The shadcn `zinc` base provides the variable names; we override them for the dark theme:

```css
/* frontend/app/globals.css — dark theme overrides */
:root {
  --background: 240 10% 4%;        /* #09090B */
  --card: 240 5% 7%;               /* #111113 */
  --border: 240 3.7% 15.9%;        /* #27272A */
  --primary: 47.9 95.8% 53.1%;     /* #EAB308 amber-500 */
  --primary-foreground: 240 10% 4%;
  --foreground: 0 0% 98%;          /* #FAFAFA */
  --muted-foreground: 240 5% 64.9%;/* #A1A1AA */
}
```

Semantic badge colors (success/warning/danger) are applied as Tailwind utility classes directly on `<Badge>` — not as CSS variables — since they are only used in `statusBadgeVariant()`.

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
        page.tsx                  # "use client" — Login form page
    (dashboard)/
      layout.tsx                  # Server Component — renders AppLayout + ProtectedRoute
      page.tsx                    # Server Component — redirect('/visits')
      visits/page.tsx             # "use client" — Visits DataTable
      visitors/page.tsx           # "use client" — Visitors DataTable
      invitations/page.tsx        # "use client" — Invitations DataTable
      users/page.tsx              # "use client" — Users DataTable (PROPERTY_ADMIN+)
      settings/page.tsx           # "use client" — Settings form
    globals.css                   # shadcn CSS variables + Tailwind base
    layout.tsx                    # Server Component — <html><body><Providers>
  components/
    ui/                           # shadcn/ui generated components (do not edit)
    layout/
      AppLayout.tsx               # "use client" — SidebarProvider + AppSidebar + main content
      AppSidebar.tsx              # "use client" — shadcn Sidebar, nav items, role filtering
      ProtectedRoute.tsx          # "use client" — useEffect auth check, spinner while loading
      UserMenu.tsx                # "use client" — Avatar dropdown (profile, logout)
    data-table/
      DataTable.tsx               # "use client" — Generic TanStack Table wrapper
      columns/
        visits.tsx                # ColumnDef[] for visits
        visitors.tsx              # ColumnDef[] for visitors
        invitations.tsx           # ColumnDef[] for invitations
        users.tsx                 # ColumnDef[] for users
    forms/
      LoginForm.tsx               # "use client" — react-hook-form + zod
      CreateUserForm.tsx          # "use client" — Modal form for POST /users/
      CreateInvitationForm.tsx    # "use client" — Modal form for POST /invitations/
      SettingsForm.tsx            # "use client" — Profile update form
    visitors/
      VisitorHistorySheet.tsx     # "use client" — shadcn Sheet, shows visit history for one visitor
  lib/
    api.ts                        # apiFetch wrapper (no "use client" needed — not a component)
    auth.ts                       # "use client" — AuthContext, useAuth hook, decodeToken
    utils.ts                      # cn(), formatDate(), statusBadgeVariant()
  providers.tsx                   # "use client" — QueryClientProvider + AuthProvider
  next.config.ts                  # API proxy rewrites
  .env.local.example              # NEXT_PUBLIC_API_URL template
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

### Sidebar

- `shadcn/ui Sidebar` with `collapsible="icon"` — collapses to icon-only at narrow viewports
- Nav items: Visits (CalendarDays icon), Visitors (Users icon), Invitations (QrCode icon), Users (Shield icon — hidden if role is `TENANT_USER`), Settings (Settings icon)
- Active item highlighted with primary amber background
- User avatar + name in sidebar footer; click → logout

### Data tables

All list views share the `<DataTable>` component:
- TanStack Table with **client-side** sorting, column filtering, pagination (10 rows/page)
- All records are fetched in a single request (no server-side pagination). This is acceptable for property-scale datasets (hundreds of records per tenant, not millions). If a tenant grows beyond ~1000 records per table, pagination query params (`?limit=&offset=`) can be added to the API and DataTable in a future phase.
- Search input above table (filters by primary text column)
- Column headers clickable for sort (asc/desc/none)
- Status columns render `<Badge>` with color from `statusBadgeVariant()`
- Actions column (where applicable) renders a `<DropdownMenu>` per row

---

## Pages

### Login (`/login`)

- Email + password inputs, submit button
- On success: store tokens, redirect to `/visits`
- On error: show error message from API envelope (`error.message`)
- Form validation: `react-hook-form` + `zod` (email format, non-empty password)

### Visits (`/visits`) — default landing

- DataTable of visits: Visitor name, Unit, Check-in time, Status, Host
- Default filter: today's date (passed as `?date=YYYY-MM-DD` query param to API)
- Date picker above table to change the day
- Status badge: CHECKED_IN (success), PENDING (warning), CHECKED_OUT (muted)

### Visitors (`/visitors`)

- DataTable: Full name, Email, Phone, Unit, Last visit date
- Search by name or email
- Click row → `<VisitorHistorySheet>` — a shadcn `Sheet` (side panel) that fetches and displays the visitor's past visits via `GET /api/visitors/{id}/visits`

### Invitations (`/invitations`)

- DataTable: Host, Visitor name, Created at, Expires at, Status
- Status badge: ACTIVE (success), EXPIRED (muted), USED (muted), CANCELLED (danger)
- "Create invitation" button → `<CreateInvitationForm>` dialog modal

**`CreateInvitationForm` fields:**
- Visitor email (EmailStr, required)
- Visitor name (string, required)
- Unit number (string, optional)
- Expires at (date picker, required — defaults to +7 days)

**`POST /api/invitations/` request body:**
```json
{
  "visitor_email": "string",
  "visitor_name": "string",
  "unit_number": "string | null",
  "expires_at": "ISO 8601 datetime string"
}
```

### Users (`/users`) — PROPERTY_ADMIN+ only

- DataTable: Name, Email, Role badge, Status (Active/Inactive)
- "Add user" button → `<CreateUserForm>` dialog modal
- Row action dropdown: Deactivate (if active) / Reactivate (if inactive) — calls `PUT /api/users/{id}` with `{ "is_active": false }` or `{ "is_active": true }`
- If `TENANT_USER` hits this page → `useEffect` redirects to `/visits` (same pattern as `ProtectedRoute`)

**`CreateUserForm` fields:**
- Email (EmailStr, required)
- Full name (string, optional)
- Role (select: TENANT_USER | PROPERTY_ADMIN, required — SUPER_ADMIN excluded)

**`POST /api/users/` request body:**
```json
{
  "email": "string",
  "full_name": "string | null",
  "role": "TENANT_USER | PROPERTY_ADMIN"
}
```
Response includes `temp_password` — displayed once in a success dialog the user must copy.

### Settings (`/settings`)

- Profile form: Full name, Phone number, Unit number
- Save button → `PUT /api/users/me`
- Show current email (read-only) and role (read-only)

---

## API Mapping

| Page/Action | Method | Endpoint | Request body |
|---|---|---|---|
| Login | POST | `/api/auth/login` | `{ email, password }` |
| Refresh token | POST | `/api/auth/refresh` | `{ refresh_token }` |
| Logout | POST | `/api/auth/logout` | `{ refresh_token }` |
| Visits list | GET | `/api/visits/?date=YYYY-MM-DD` | — |
| Visitors list | GET | `/api/visitors/` | — |
| Visitor visit history | GET | `/api/visitors/{id}/visits` | — |
| Invitations list | GET | `/api/invitations/` | — |
| Create invitation | POST | `/api/invitations/` | `{ visitor_email, visitor_name, unit_number?, expires_at }` |
| Users list | GET | `/api/users/` | — |
| Create user | POST | `/api/users/` | `{ email, full_name?, role }` |
| Deactivate/reactivate user | PUT | `/api/users/{id}` | `{ is_active: boolean }` |
| Profile (read) | GET | `/api/users/me` | — |
| Profile (update) | PUT | `/api/users/me` | `{ full_name?, phone_number?, unit_number? }` |

---

## Error Handling

All API errors are caught in `apiFetch` and thrown as `ApiError`. Each page/mutation:
- Loading state: skeleton rows in DataTable, spinner on form submit buttons
- API error: `toast` (shadcn `Sonner`) notification with `error.message` from envelope
- 401: silent refresh attempted; on failure → redirect to login (handled in `api.ts`)
- Validation error (422): form field errors shown inline via react-hook-form's `setError`
- Network error (fetch throws): `toast` with generic "Connection error" message

---

## Files Created

| File | Purpose |
|---|---|
| `frontend/package.json` | Next.js 15, React 19, Tailwind, shadcn, TanStack |
| `frontend/next.config.ts` | API proxy rewrites `/api/:path*` → FastAPI |
| `frontend/.env.local.example` | `NEXT_PUBLIC_API_URL=http://localhost:8001` |
| `frontend/tailwind.config.ts` | Tailwind base config (shadcn integration) |
| `frontend/components.json` | shadcn config (`style: default, rsc: false, baseColor: zinc`) |
| `frontend/app/globals.css` | CSS variable overrides for dark palette |
| `frontend/app/layout.tsx` | Root HTML shell, wraps `<Providers>` |
| `frontend/providers.tsx` | QueryClientProvider + AuthProvider |
| `frontend/lib/api.ts` | apiFetch wrapper with proxy prefix + silent refresh |
| `frontend/lib/auth.ts` | AuthContext, useAuth hook, decodeToken |
| `frontend/lib/utils.ts` | cn(), formatDate(), statusBadgeVariant() |
| `frontend/components/layout/AppLayout.tsx` | Root dashboard layout |
| `frontend/components/layout/AppSidebar.tsx` | Collapsible sidebar with role filtering |
| `frontend/components/layout/ProtectedRoute.tsx` | useEffect auth guard, renders spinner while loading |
| `frontend/components/layout/UserMenu.tsx` | Avatar dropdown |
| `frontend/components/data-table/DataTable.tsx` | Generic TanStack Table |
| `frontend/components/data-table/columns/visits.tsx` | Visits column defs |
| `frontend/components/data-table/columns/visitors.tsx` | Visitors column defs |
| `frontend/components/data-table/columns/invitations.tsx` | Invitations column defs |
| `frontend/components/data-table/columns/users.tsx` | Users column defs |
| `frontend/components/forms/LoginForm.tsx` | Login form |
| `frontend/components/forms/CreateUserForm.tsx` | Create user modal form |
| `frontend/components/forms/CreateInvitationForm.tsx` | Create invitation modal form |
| `frontend/components/forms/SettingsForm.tsx` | Profile update form |
| `frontend/components/visitors/VisitorHistorySheet.tsx` | shadcn Sheet with visit history |
| `frontend/app/(auth)/login/page.tsx` | Login page |
| `frontend/app/(dashboard)/layout.tsx` | Server Component — renders AppLayout |
| `frontend/app/(dashboard)/page.tsx` | Server Component — redirect('/visits') |
| `frontend/app/(dashboard)/visits/page.tsx` | Visits page |
| `frontend/app/(dashboard)/visitors/page.tsx` | Visitors page |
| `frontend/app/(dashboard)/invitations/page.tsx` | Invitations page |
| `frontend/app/(dashboard)/users/page.tsx` | Users page |
| `frontend/app/(dashboard)/settings/page.tsx` | Settings page |

---

## Security Decisions

| Decision | Choice | Reason |
|---|---|---|
| Auth storage | localStorage | Internal admin tool; acceptable for property staff on managed devices |
| Token decode | No signature verify | Frontend can't hold the secret; trust our own API's validation |
| Route protection | Client-side only (`useEffect`) | Avoids SSR localStorage access errors; no sensitive data server-rendered |
| Silent token refresh | Yes, on 401 | 30-min access token would otherwise force re-login every session |
| Role filtering | JWT `role` claim | Frontend uses for UI only; backend enforces authorization on every request |
| API proxy | Next.js rewrites | Eliminates CORS configuration entirely; single origin for browser |
| API errors | Envelope parse | Phase 5 standardized all errors; frontend reads `error.code` + `error.message` |
