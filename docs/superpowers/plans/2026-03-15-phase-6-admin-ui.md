# Phase 6 Admin UI Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a Next.js 15 App Router admin dashboard for Habitare that lets property staff manage visits, visitors, invitations, and users via the existing FastAPI backend.

**Architecture:** All-client-component SPA in `frontend/` inside the monorepo; API calls proxied through Next.js rewrites (`/api/:path*` → FastAPI on port 8001) to avoid CORS; JWT stored in localStorage with silent refresh on 401; shadcn/ui with dark amber/zinc theme.

**Tech Stack:** Next.js 15 · React 19 · TypeScript · Tailwind CSS · shadcn/ui · TanStack Query v5 · TanStack Table v8 · react-hook-form v7 · zod · jwt-decode · Vitest · Lucide React

**Branch:** `feat/phase-6-admin-ui`

---

## Chunk 1: Foundation

### Task 1: Scaffold Next.js project

**Files:**
- Create: `frontend/` (entire project)
- Create: `frontend/next.config.ts`
- Create: `frontend/.env.local.example`
- Create: `frontend/.env.local`

- [ ] **Step 1: Create Next.js app inside monorepo**

Run from the repo root (`/path/to/habitare/`):

```bash
npx create-next-app@latest frontend \
  --typescript \
  --tailwind \
  --eslint \
  --app \
  --no-src-dir \
  --import-alias "@/*" \
  --yes
```

Expected: Creates `frontend/` with App Router, TypeScript, Tailwind, ESLint configured.

- [ ] **Step 2: Install additional runtime dependencies**

```bash
cd frontend
npm install \
  @tanstack/react-query@^5 \
  @tanstack/react-table@^8 \
  react-hook-form \
  @hookform/resolvers \
  zod \
  jwt-decode \
  lucide-react \
  sonner
```

- [ ] **Step 3: Install dev dependencies (Vitest + testing)**

```bash
npm install -D \
  vitest \
  @vitejs/plugin-react \
  @testing-library/react \
  @testing-library/jest-dom \
  @testing-library/user-event \
  jsdom
```

- [ ] **Step 4: Add Vitest scripts to package.json**

In `frontend/package.json`, add to `"scripts"`:

```json
"test": "vitest run",
"test:watch": "vitest"
```

- [ ] **Step 5: Create `frontend/vitest.config.ts`**

```ts
import { defineConfig } from "vitest/config"
import react from "@vitejs/plugin-react"
import { resolve } from "path"

export default defineConfig({
  plugins: [react()],
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: ["./tests/setup.ts"],
  },
  resolve: {
    alias: {
      "@": resolve(__dirname, "."),
    },
  },
})
```

- [ ] **Step 6: Create `frontend/tests/setup.ts`**

```ts
import "@testing-library/jest-dom"
```

- [ ] **Step 7: Replace `frontend/next.config.ts` with proxy config**

```ts
import type { NextConfig } from "next"

const nextConfig: NextConfig = {
  async rewrites() {
    return [
      {
        source: "/api/:path*",
        destination: `${process.env.API_URL}/:path*`,
      },
    ]
  },
}

export default nextConfig
```

- [ ] **Step 8: Create `frontend/.env.local.example`**

```
API_URL=http://localhost:8001
```

- [ ] **Step 9: Create `frontend/.env.local`**

```
API_URL=http://localhost:8001
```

- [ ] **Step 9b: Confirm `.env.local` is gitignored**

```bash
git check-ignore -v frontend/.env.local
```

Expected: a line showing the file is covered by a `.gitignore` rule. If not covered, add to `frontend/.gitignore` (created by `create-next-app`):
```
.env.local
```

(The `create-next-app` scaffold creates `frontend/.gitignore` with `.env.local` already excluded. Verify before committing.)

- [ ] **Step 10: Verify dev server starts**

```bash
npm run dev
```

Expected: Server starts at `http://localhost:3000` with no errors. The default Next.js page loads. `Ctrl+C` to stop.

- [ ] **Step 11: Commit**

```bash
cd ..
git add frontend/
git commit -m "feat(ui): scaffold Next.js 15 app with TanStack, react-hook-form, Vitest"
```

---

### Task 2: Install shadcn/ui and add components

**Files:**
- Modify: `frontend/components.json` (created by shadcn init)
- Modify: `frontend/tailwind.config.ts`
- Create: `frontend/components/ui/` (shadcn generated)

- [ ] **Step 1: Initialize shadcn**

```bash
cd frontend
npx shadcn@latest init \
  --style default \
  --base-color zinc \
  --yes
# If the CLI supports --no-rsc, add it: `--no-rsc`
```

Expected: Creates `components.json`, updates `tailwind.config.ts`, creates `app/globals.css` with CSS variables, creates `lib/utils.ts`.

- [ ] **Step 2: Verify `frontend/components.json` has correct values — especially `"rsc": false`**

The file should contain:

```json
{
  "$schema": "https://ui.shadcn.com/schema.json",
  "style": "default",
  "rsc": false,
  "tsx": true,
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

If `rsc` is not `false`, edit the file to set `"rsc": false`.

- [ ] **Step 3: Add all required shadcn components**

```bash
npx shadcn@latest add \
  sidebar \
  button \
  input \
  badge \
  table \
  dialog \
  sheet \
  sonner \
  skeleton \
  dropdown-menu \
  avatar \
  form \
  label \
  calendar \
  popover \
  card \
  separator \
  scroll-area \
  tooltip \
  --yes
```

Expected: Creates files in `frontend/components/ui/`.

- [ ] **Step 4: Commit**

```bash
cd ..
git add frontend/
git commit -m "feat(ui): add shadcn/ui components"
```

---

### Task 3: lib/utils.ts + color system (globals.css)

**Files:**
- Modify: `frontend/lib/utils.ts` (shadcn created a stub — replace it)
- Modify: `frontend/app/globals.css` (override CSS variables for dark palette)
- Create: `frontend/tests/utils.test.ts`

- [ ] **Step 1: Write the failing tests first**

Create `frontend/tests/utils.test.ts`:

```ts
import { describe, it, expect } from "vitest"
import { formatDate, statusBadgeVariant } from "@/lib/utils"

describe("formatDate", () => {
  it("formats ISO datetime to readable string", () => {
    const result = formatDate("2026-03-15T14:30:00Z")
    // Must contain the date regardless of timezone. Use UTC-pinned impl.
    expect(result).toMatch(/Mar 15, 2026/)
  })

  it("handles date-only string without timezone rollback", () => {
    // "2026-03-15" parsed as UTC midnight — implementation must use timeZone:"UTC"
    // to avoid rolling back to Mar 14 in UTC-west timezones.
    const result = formatDate("2026-03-15")
    expect(result).toMatch(/Mar 15, 2026/)
  })
})

describe("statusBadgeVariant", () => {
  it("returns success style for CHECKED_IN", () => {
    const result = statusBadgeVariant("CHECKED_IN")
    expect(result.className).toContain("green")
  })

  it("returns success style for ACTIVE", () => {
    const result = statusBadgeVariant("ACTIVE")
    expect(result.className).toContain("green")
  })

  it("returns warning style for PENDING", () => {
    const result = statusBadgeVariant("PENDING")
    expect(result.className).toContain("orange")
  })

  it("returns muted style for EXPIRED", () => {
    const result = statusBadgeVariant("EXPIRED")
    expect(result.className).toContain("zinc")
  })

  it("returns danger style for FAILED", () => {
    const result = statusBadgeVariant("FAILED")
    expect(result.className).toContain("red")
  })

  it("returns danger style for CANCELLED", () => {
    const result = statusBadgeVariant("CANCELLED")
    expect(result.className).toContain("red")
  })

  it("is case-insensitive", () => {
    expect(statusBadgeVariant("checked_in").className).toContain("green")
  })
})
```

- [ ] **Step 2: Run tests — expect failures**

```bash
cd frontend
npm test
```

Expected: FAIL — `formatDate` and `statusBadgeVariant` not yet exported from `lib/utils.ts`.

- [ ] **Step 3: Replace `frontend/lib/utils.ts`**

```ts
import { clsx, type ClassValue } from "clsx"
import { twMerge } from "tailwind-merge"

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs))
}

export function formatDate(dateStr: string): string {
  // Use timeZone: "UTC" to prevent date-only strings ("2026-03-15") from rolling
  // back one day in UTC-west timezones. new Date("2026-03-15") parses as UTC midnight.
  return new Date(dateStr).toLocaleDateString("en-US", {
    timeZone: "UTC",
    month: "short",
    day: "numeric",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  })
}

type BadgeStyle = { variant: "default" | "secondary" | "destructive" | "outline"; className: string }

export function statusBadgeVariant(status: string): BadgeStyle {
  switch (status.toUpperCase()) {
    case "CHECKED_IN":
    case "SENT":
    case "ACTIVE":
      return { variant: "default", className: "bg-green-500/20 text-green-400 border border-green-500/30" }
    case "PENDING":
      return { variant: "default", className: "bg-orange-500/20 text-orange-400 border border-orange-500/30" }
    case "CHECKED_OUT":
    case "EXPIRED":
    case "USED":
      return { variant: "secondary", className: "bg-zinc-700/50 text-zinc-400 border border-zinc-600/30" }
    case "FAILED":
    case "CANCELLED":
      return { variant: "destructive", className: "bg-red-500/20 text-red-400 border border-red-500/30" }
    default:
      return { variant: "secondary", className: "bg-zinc-700/50 text-zinc-400 border border-zinc-600/30" }
  }
}
```

- [ ] **Step 4: Run tests — expect pass**

```bash
npm test
```

Expected: All 7 tests PASS.

- [ ] **Step 5: Replace `frontend/app/globals.css` with dark palette overrides**

```css
@tailwind base;
@tailwind components;
@tailwind utilities;

@layer base {
  :root {
    --background: 240 10% 4%;
    --foreground: 0 0% 98%;
    --card: 240 5% 7%;
    --card-foreground: 0 0% 98%;
    --popover: 240 5% 7%;
    --popover-foreground: 0 0% 98%;
    --primary: 47.9 95.8% 53.1%;
    --primary-foreground: 240 10% 4%;
    --secondary: 240 3.7% 15.9%;
    --secondary-foreground: 0 0% 98%;
    --muted: 240 3.7% 15.9%;
    --muted-foreground: 240 5% 64.9%;
    --accent: 240 3.7% 15.9%;
    --accent-foreground: 0 0% 98%;
    --destructive: 0 62.8% 30.6%;
    --destructive-foreground: 0 0% 98%;
    --border: 240 3.7% 15.9%;
    --input: 240 3.7% 15.9%;
    --ring: 47.9 95.8% 53.1%;
    --radius: 0.5rem;
    --sidebar-background: 240 5% 7%;
    --sidebar-foreground: 0 0% 98%;
    --sidebar-primary: 47.9 95.8% 53.1%;
    --sidebar-primary-foreground: 240 10% 4%;
    --sidebar-accent: 240 3.7% 15.9%;
    --sidebar-accent-foreground: 0 0% 98%;
    --sidebar-border: 240 3.7% 15.9%;
    --sidebar-ring: 47.9 95.8% 53.1%;
  }
}

@layer base {
  * {
    @apply border-border;
  }
  body {
    @apply bg-background text-foreground;
  }
}
```

- [ ] **Step 6: Commit**

```bash
cd ..
git add frontend/
git commit -m "feat(ui): lib/utils with statusBadgeVariant + dark palette CSS variables"
```

---

### Task 4: API client (lib/api.ts)

**Files:**
- Create: `frontend/lib/api.ts`
- Create: `frontend/tests/api.test.ts`

- [ ] **Step 1: Write the failing tests**

Create `frontend/tests/api.test.ts`:

```ts
import { describe, it, expect } from "vitest"
import { ApiError } from "@/lib/api"

describe("ApiError", () => {
  it("is an instance of Error", () => {
    const err = new ApiError("HTTP_403", "Forbidden", null, 403)
    expect(err).toBeInstanceOf(Error)
    expect(err).toBeInstanceOf(ApiError)
  })

  it("has correct name", () => {
    const err = new ApiError("HTTP_403", "Forbidden", null, 403)
    expect(err.name).toBe("ApiError")
  })

  it("exposes code, message, detail, status", () => {
    const err = new ApiError("VALIDATION_ERROR", "Invalid body", [{ loc: ["body", "email"] }], 422)
    expect(err.code).toBe("VALIDATION_ERROR")
    expect(err.message).toBe("Invalid body")
    expect(err.detail).toEqual([{ loc: ["body", "email"] }])
    expect(err.status).toBe(422)
  })
})
```

- [ ] **Step 2: Run tests — expect failures**

```bash
cd frontend && npm test
```

Expected: FAIL — `ApiError` not yet exported.

- [ ] **Step 3: Create `frontend/lib/api.ts`**

```ts
// browser-only — uses localStorage and window; import only from Client Components

export class ApiError extends Error {
  constructor(
    public readonly code: string,
    message: string,
    public readonly detail: unknown,
    public readonly status: number,
  ) {
    super(message)
    this.name = "ApiError"
  }
}

let isRefreshing = false
let refreshPromise: Promise<string> | null = null

async function attemptRefresh(): Promise<string> {
  const refreshTok = localStorage.getItem("habitare_refresh_token")
  if (!refreshTok) {
    window.location.href = "/login"
    throw new ApiError("REFRESH_FAILED", "No refresh token", null, 401)
  }

  const resp = await fetch("/api/auth/refresh", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ refresh_token: refreshTok }),
  })

  if (!resp.ok) {
    localStorage.removeItem("habitare_access_token")
    localStorage.removeItem("habitare_refresh_token")
    window.location.href = "/login"
    throw new ApiError("REFRESH_FAILED", "Session expired", null, 401)
  }

  const data = await resp.json()
  localStorage.setItem("habitare_access_token", data.access_token)
  return data.access_token as string
}

export async function apiFetch<T>(
  path: string,
  options: RequestInit = {},
  _isRetry = false,
): Promise<T> {
  const token = localStorage.getItem("habitare_access_token")

  // Note: options.headers must be a plain object literal (not a Headers instance or array)
  // for the spread merge to work correctly. All callers in Phase 6 use plain objects.
  const resp = await fetch(`/api${path}`, {
    ...options,
    headers: {
      "Content-Type": "application/json",
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...(options.headers as Record<string, string> | undefined),
    },
  })

  if (resp.status === 401 && !_isRetry) {
    if (!isRefreshing) {
      isRefreshing = true
      refreshPromise = attemptRefresh().finally(() => {
        isRefreshing = false
        refreshPromise = null
      })
    }
    await refreshPromise
    return apiFetch<T>(path, options, true)
  }

  if (!resp.ok) {
    let payload: Record<string, unknown> = {}
    try {
      payload = await resp.json()
    } catch {
      // non-JSON body
    }
    const envelope = (payload?.error ?? {}) as Record<string, unknown>
    throw new ApiError(
      (envelope.code as string) ?? `HTTP_${resp.status}`,
      (envelope.message as string) ?? resp.statusText,
      envelope.detail ?? null,
      resp.status,
    )
  }

  if (resp.status === 204) return undefined as T
  return resp.json() as Promise<T>
}
```

- [ ] **Step 4: Run tests — expect pass**

```bash
npm test
```

Expected: All 3 ApiError tests PASS (plus the 7 utils tests = 10 total).

- [ ] **Step 5: Commit**

```bash
cd ..
git add frontend/lib/api.ts frontend/tests/api.test.ts
git commit -m "feat(ui): API client with silent refresh and typed ApiError"
```

---

### Task 5: Auth context (lib/auth.ts + providers.tsx)

**Files:**
- Create: `frontend/lib/auth.ts`
- Create: `frontend/providers.tsx`
- Create: `frontend/tests/auth.test.ts`

- [ ] **Step 1: Write the failing tests**

Create `frontend/tests/auth.test.ts`:

```ts
import { describe, it, expect } from "vitest"

// We test only the pure decodeToken function by importing the decode logic
// AuthContext is a React component and is verified via the browser
import { jwtDecode } from "jwt-decode"

// A manually constructed JWT with the correct URL-safe base64 payload segment.
// jwtDecode requires URL-safe base64 (replace + with -, / with _, strip =).
function toBase64Url(obj: object): string {
  return btoa(JSON.stringify(obj))
    .replace(/\+/g, "-")
    .replace(/\//g, "_")
    .replace(/=/g, "")
}

const SAMPLE_TOKEN =
  "eyJhbGciOiJIUzI1NiJ9." +
  toBase64Url({
    user_id: "abc-123",
    tenant_id: "ten-456",
    role: "PROPERTY_ADMIN",
    email: "admin@example.com",
    exp: 9999999999,
  }) +
  ".fakesig"

describe("jwtDecode (token decode used by AuthContext)", () => {
  it("decodes user_id from payload", () => {
    const payload = jwtDecode<{ user_id: string }>(SAMPLE_TOKEN)
    expect(payload.user_id).toBe("abc-123")
  })

  it("decodes role from payload", () => {
    const payload = jwtDecode<{ role: string }>(SAMPLE_TOKEN)
    expect(payload.role).toBe("PROPERTY_ADMIN")
  })

  it("decodes email from payload", () => {
    const payload = jwtDecode<{ email: string }>(SAMPLE_TOKEN)
    expect(payload.email).toBe("admin@example.com")
  })
})
```

- [ ] **Step 2: Run tests — expect pass (jwt-decode is already installed)**

```bash
cd frontend && npm test
```

Expected: All 3 auth tests PASS + 10 previous = 13 total.

- [ ] **Step 3: Create `frontend/lib/auth.ts`**

```ts
"use client"

import { createContext, useContext, useState, useEffect, type ReactNode } from "react"
import { jwtDecode } from "jwt-decode"

interface JwtPayload {
  user_id: string
  tenant_id: string
  role: "TENANT_USER" | "PROPERTY_ADMIN" | "SUPER_ADMIN"
  email: string
  exp: number
}

export interface User {
  id: string
  tenantId: string
  role: "TENANT_USER" | "PROPERTY_ADMIN" | "SUPER_ADMIN"
  email: string
  // Profile fields — not in JWT; loaded separately by Settings page
  fullName?: string | null
  phoneNumber?: string | null
  unitNumber?: string | null
}

interface AuthContextValue {
  user: User | null
  token: string | null
  isLoading: boolean
  login: (accessToken: string, refreshToken: string) => void
  logout: () => void
  // updateUser is used by SettingsForm to sync profile fields after PUT /users/me
  updateUser: (partial: Partial<Omit<User, "id" | "tenantId" | "role">>) => void
}

const AuthContext = createContext<AuthContextValue | null>(null)

function decodeToken(token: string): User {
  const p = jwtDecode<JwtPayload>(token)
  return { id: p.user_id, tenantId: p.tenant_id, role: p.role, email: p.email }
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null)
  const [token, setToken] = useState<string | null>(null)
  const [isLoading, setIsLoading] = useState(true)

  useEffect(() => {
    const stored = localStorage.getItem("habitare_access_token")
    if (stored) {
      try {
        setUser(decodeToken(stored))
        setToken(stored)
      } catch {
        localStorage.removeItem("habitare_access_token")
        localStorage.removeItem("habitare_refresh_token")
      }
    }
    setIsLoading(false)
  }, [])

  function login(accessToken: string, refreshToken: string) {
    localStorage.setItem("habitare_access_token", accessToken)
    localStorage.setItem("habitare_refresh_token", refreshToken)
    setToken(accessToken)
    setUser(decodeToken(accessToken))
  }

  function logout() {
    localStorage.removeItem("habitare_access_token")
    localStorage.removeItem("habitare_refresh_token")
    setToken(null)
    setUser(null)
  }

  function updateUser(partial: Partial<Omit<User, "id" | "tenantId" | "role">>) {
    setUser((prev) => (prev ? { ...prev, ...partial } : null))
  }

  return (
    <AuthContext.Provider value={{ user, token, isLoading, login, logout, updateUser }}>
      {children}
    </AuthContext.Provider>
  )
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext)
  if (!ctx) throw new Error("useAuth must be used within AuthProvider")
  return ctx
}
```

- [ ] **Step 4: Create `frontend/providers.tsx`**

```tsx
"use client"

import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { useState, type ReactNode } from "react"
import { AuthProvider } from "@/lib/auth"
import { Toaster } from "@/components/ui/sonner"

export function Providers({ children }: { children: ReactNode }) {
  const [queryClient] = useState(
    () =>
      new QueryClient({
        defaultOptions: {
          queries: {
            staleTime: 30_000,
            retry: 1,
          },
        },
      }),
  )

  return (
    <QueryClientProvider client={queryClient}>
      <AuthProvider>
        {children}
        <Toaster position="top-right" theme="dark" />
      </AuthProvider>
    </QueryClientProvider>
  )
}
```

- [ ] **Step 5: Run all tests**

```bash
npm test
```

Expected: 13 tests PASS.

- [ ] **Step 6: Commit**

```bash
cd ..
git add frontend/lib/auth.ts frontend/providers.tsx frontend/tests/auth.test.ts
git commit -m "feat(ui): AuthContext with localStorage JWT + QueryClient provider"
```

---

## Chunk 2: Layout + Login

### Task 6: App root layout + dashboard shell pages

**Files:**
- Modify: `frontend/app/layout.tsx`
- Create: `frontend/app/(auth)/login/page.tsx` (placeholder)
- Create: `frontend/app/(dashboard)/layout.tsx`
- Create: `frontend/app/(dashboard)/page.tsx`

- [ ] **Step 1: Replace `frontend/app/layout.tsx`**

```tsx
import type { Metadata } from "next"
import { Inter } from "next/font/google"
import "./globals.css"
import { Providers } from "@/providers"

const inter = Inter({ subsets: ["latin"] })

export const metadata: Metadata = {
  title: "Habitare Admin",
  description: "Visitor management for property staff",
}

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className="dark">
      <body className={inter.className}>
        <Providers>{children}</Providers>
      </body>
    </html>
  )
}
```

- [ ] **Step 2: Create `frontend/app/(auth)/login/page.tsx` (placeholder)**

```tsx
export default function LoginPage() {
  return (
    <main className="flex min-h-screen items-center justify-center bg-background">
      <p className="text-muted-foreground">Login form coming soon</p>
    </main>
  )
}
```

- [ ] **Step 3: Create `frontend/app/(dashboard)/page.tsx`**

```tsx
import { redirect } from "next/navigation"

export default function DashboardRoot() {
  redirect("/visits")
}
```

- [ ] **Step 4: Create `frontend/app/(dashboard)/layout.tsx`**

```tsx
import { AppLayout } from "@/components/layout/AppLayout"

export default function DashboardLayout({ children }: { children: React.ReactNode }) {
  return <AppLayout>{children}</AppLayout>
}
```

Note: `AppLayout` (a Client Component) will be created in Task 7. This layout is a thin Server Component wrapper — it contains no auth logic itself.

- [ ] **Step 5: Create placeholder page files**

Create these five files with identical content temporarily (they get real implementations in Tasks 9-14):

`frontend/app/(dashboard)/visits/page.tsx`:
```tsx
"use client"
export default function VisitsPage() {
  return <div className="p-6 text-foreground">Visits — coming soon</div>
}
```

`frontend/app/(dashboard)/visitors/page.tsx`:
```tsx
"use client"
export default function VisitorsPage() {
  return <div className="p-6 text-foreground">Visitors — coming soon</div>
}
```

`frontend/app/(dashboard)/invitations/page.tsx`:
```tsx
"use client"
export default function InvitationsPage() {
  return <div className="p-6 text-foreground">Invitations — coming soon</div>
}
```

`frontend/app/(dashboard)/users/page.tsx`:
```tsx
"use client"
export default function UsersPage() {
  return <div className="p-6 text-foreground">Users — coming soon</div>
}
```

`frontend/app/(dashboard)/settings/page.tsx`:
```tsx
"use client"
export default function SettingsPage() {
  return <div className="p-6 text-foreground">Settings — coming soon</div>
}
```

- [ ] **Step 6: Commit (even though AppLayout doesn't exist yet — layout.tsx will be a build error until Task 7)**

Skip commit until Task 7 completes — they must be committed together.

---

### Task 7: Layout components (AppLayout, AppSidebar, ProtectedRoute, UserMenu)

**Files:**
- Create: `frontend/components/layout/AppLayout.tsx`
- Create: `frontend/components/layout/AppSidebar.tsx`
- Create: `frontend/components/layout/ProtectedRoute.tsx`
- Create: `frontend/components/layout/UserMenu.tsx`

- [ ] **Step 1: Create `frontend/components/layout/ProtectedRoute.tsx`**

```tsx
"use client"

import { useEffect } from "react"
import { useRouter } from "next/navigation"
import { useAuth } from "@/lib/auth"

export function ProtectedRoute({ children }: { children: React.ReactNode }) {
  const { token, isLoading } = useAuth()
  const router = useRouter()

  useEffect(() => {
    if (!isLoading && !token) {
      router.push("/login")
    }
  }, [isLoading, token, router])

  if (isLoading) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-background">
        <div className="h-8 w-8 animate-spin rounded-full border-4 border-primary border-t-transparent" />
      </div>
    )
  }

  if (!token) return null

  return <>{children}</>
}
```

- [ ] **Step 2: Create `frontend/components/layout/UserMenu.tsx`**

```tsx
"use client"

import { useRouter } from "next/navigation"
import { Avatar, AvatarFallback } from "@/components/ui/avatar"
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu"
import { SidebarMenuButton } from "@/components/ui/sidebar"
import { useAuth } from "@/lib/auth"
import { apiFetch } from "@/lib/api"
import { LogOut, Settings } from "lucide-react"
import { toast } from "sonner"

export function UserMenu() {
  const { user, logout } = useAuth()
  const router = useRouter()

  async function handleLogout() {
    const refreshTok = localStorage.getItem("habitare_refresh_token")
    try {
      await apiFetch("/auth/logout", {
        method: "POST",
        body: JSON.stringify({ refresh_token: refreshTok }),
      })
    } catch {
      // Ignore logout errors — clear session regardless
    }
    logout()
    router.push("/login")
  }

  const initials = user?.email?.slice(0, 2).toUpperCase() ?? "??"

  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <SidebarMenuButton size="lg" className="cursor-pointer">
          <Avatar className="h-8 w-8 rounded-lg">
            <AvatarFallback className="rounded-lg bg-primary text-primary-foreground text-xs font-semibold">
              {initials}
            </AvatarFallback>
          </Avatar>
          <div className="flex flex-col gap-0.5 leading-none">
            <span className="truncate text-sm font-semibold text-foreground">{user?.email}</span>
            <span className="truncate text-xs text-muted-foreground capitalize">
              {user?.role?.toLowerCase().replace("_", " ")}
            </span>
          </div>
        </SidebarMenuButton>
      </DropdownMenuTrigger>
      <DropdownMenuContent side="top" align="start" className="w-56">
        <DropdownMenuLabel className="font-normal">
          <p className="text-xs text-muted-foreground">{user?.email}</p>
        </DropdownMenuLabel>
        <DropdownMenuSeparator />
        <DropdownMenuItem onClick={() => router.push("/settings")}>
          <Settings className="mr-2 h-4 w-4" />
          Settings
        </DropdownMenuItem>
        <DropdownMenuSeparator />
        <DropdownMenuItem onClick={handleLogout} className="text-destructive focus:text-destructive">
          <LogOut className="mr-2 h-4 w-4" />
          Log out
        </DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  )
}
```

- [ ] **Step 3: Create `frontend/components/layout/AppSidebar.tsx`**

```tsx
"use client"

import Link from "next/link"
import { usePathname } from "next/navigation"
import {
  Sidebar,
  SidebarContent,
  SidebarFooter,
  SidebarHeader,
  SidebarMenu,
  SidebarMenuButton,
  SidebarMenuItem,
  SidebarRail,
} from "@/components/ui/sidebar"
import { useAuth } from "@/lib/auth"
import { UserMenu } from "./UserMenu"
import { CalendarDays, Users, QrCode, Shield, Settings } from "lucide-react"

const NAV_ITEMS = [
  { href: "/visits", label: "Visits", icon: CalendarDays, roles: ["TENANT_USER", "PROPERTY_ADMIN", "SUPER_ADMIN"] },
  { href: "/visitors", label: "Visitors", icon: Users, roles: ["TENANT_USER", "PROPERTY_ADMIN", "SUPER_ADMIN"] },
  { href: "/invitations", label: "Invitations", icon: QrCode, roles: ["TENANT_USER", "PROPERTY_ADMIN", "SUPER_ADMIN"] },
  { href: "/users", label: "Users", icon: Shield, roles: ["PROPERTY_ADMIN", "SUPER_ADMIN"] },
  { href: "/settings", label: "Settings", icon: Settings, roles: ["TENANT_USER", "PROPERTY_ADMIN", "SUPER_ADMIN"] },
]

export function AppSidebar() {
  const pathname = usePathname()
  const { user } = useAuth()

  const visibleItems = NAV_ITEMS.filter(
    (item) => !user?.role || item.roles.includes(user.role),
  )

  return (
    <Sidebar collapsible="icon">
      <SidebarHeader className="border-b border-sidebar-border px-4 py-3">
        <span className="text-sm font-bold text-primary group-data-[collapsible=icon]:hidden">
          Habitare
        </span>
        <span className="hidden text-sm font-bold text-primary group-data-[collapsible=icon]:block">H</span>
      </SidebarHeader>

      <SidebarContent>
        <SidebarMenu className="px-2 py-2">
          {visibleItems.map((item) => {
            const isActive = pathname.startsWith(item.href)
            return (
              <SidebarMenuItem key={item.href}>
                <SidebarMenuButton
                  asChild
                  isActive={isActive}
                  tooltip={item.label}
                  className={isActive ? "bg-primary/20 text-primary hover:bg-primary/30" : ""}
                >
                  <Link href={item.href}>
                    <item.icon className="h-4 w-4" />
                    <span>{item.label}</span>
                  </Link>
                </SidebarMenuButton>
              </SidebarMenuItem>
            )
          })}
        </SidebarMenu>
      </SidebarContent>

      <SidebarFooter className="border-t border-sidebar-border p-2">
        <SidebarMenu>
          <SidebarMenuItem>
            <UserMenu />
          </SidebarMenuItem>
        </SidebarMenu>
      </SidebarFooter>
      <SidebarRail />
    </Sidebar>
  )
}
```

- [ ] **Step 4: Create `frontend/components/layout/AppLayout.tsx`**

```tsx
"use client"

import { SidebarInset, SidebarProvider, SidebarTrigger } from "@/components/ui/sidebar"
import { AppSidebar } from "./AppSidebar"
import { ProtectedRoute } from "./ProtectedRoute"
import { Separator } from "@/components/ui/separator"

export function AppLayout({ children }: { children: React.ReactNode }) {
  return (
    <ProtectedRoute>
      <SidebarProvider>
        <AppSidebar />
        <SidebarInset>
          <header className="flex h-14 shrink-0 items-center gap-2 border-b border-border px-4">
            <SidebarTrigger className="-ml-1" />
            <Separator orientation="vertical" className="mx-2 h-4" />
          </header>
          <main className="flex-1 overflow-auto p-6">{children}</main>
        </SidebarInset>
      </SidebarProvider>
    </ProtectedRoute>
  )
}
```

- [ ] **Step 5: Verify dev server compiles**

```bash
cd frontend && npm run dev
```

Expected: No TypeScript/compilation errors. Navigate to `http://localhost:3000` — should redirect to `/visits` which shows "Visits — coming soon" wrapped in the sidebar layout (sidebar shows after auth check, which will redirect to `/login` since no token is stored). `Ctrl+C`.

- [ ] **Step 6: Commit**

```bash
cd ..
git add frontend/
git commit -m "feat(ui): layout components — AppLayout, AppSidebar, ProtectedRoute, UserMenu"
```

---

### Task 8: Login page

**Files:**
- Create: `frontend/components/forms/LoginForm.tsx`
- Modify: `frontend/app/(auth)/login/page.tsx`

- [ ] **Step 1: Create `frontend/components/forms/LoginForm.tsx`**

```tsx
"use client"

import { useForm } from "react-hook-form"
import { zodResolver } from "@hookform/resolvers/zod"
import { z } from "zod"
import { useRouter } from "next/navigation"
import { toast } from "sonner"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { useAuth } from "@/lib/auth"
import { apiFetch, ApiError } from "@/lib/api"

const schema = z.object({
  email: z.string().email("Enter a valid email"),
  password: z.string().min(1, "Password is required"),
})

type FormData = z.infer<typeof schema>

interface LoginResponse {
  access_token: string
  refresh_token: string
}

export function LoginForm() {
  const { login } = useAuth()
  const router = useRouter()

  const {
    register,
    handleSubmit,
    formState: { errors, isSubmitting },
  } = useForm<FormData>({ resolver: zodResolver(schema) })

  async function onSubmit(data: FormData) {
    try {
      const resp = await apiFetch<LoginResponse>("/auth/login", {
        method: "POST",
        body: JSON.stringify(data),
      })
      login(resp.access_token, resp.refresh_token)
      router.push("/visits")
    } catch (err) {
      const message = err instanceof ApiError ? err.message : "Login failed"
      toast.error(message)
    }
  }

  return (
    <Card className="w-full max-w-sm">
      <CardHeader className="text-center">
        <CardTitle className="text-2xl font-bold text-primary">Habitare</CardTitle>
        <CardDescription>Sign in to manage your property</CardDescription>
      </CardHeader>
      <CardContent>
        <form onSubmit={handleSubmit(onSubmit)} className="flex flex-col gap-4">
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="email">Email</Label>
            <Input
              id="email"
              type="email"
              placeholder="admin@example.com"
              autoComplete="email"
              {...register("email")}
            />
            {errors.email && (
              <p className="text-xs text-destructive">{errors.email.message}</p>
            )}
          </div>

          <div className="flex flex-col gap-1.5">
            <Label htmlFor="password">Password</Label>
            <Input
              id="password"
              type="password"
              autoComplete="current-password"
              {...register("password")}
            />
            {errors.password && (
              <p className="text-xs text-destructive">{errors.password.message}</p>
            )}
          </div>

          <Button type="submit" className="w-full bg-primary text-primary-foreground hover:bg-primary/90" disabled={isSubmitting}>
            {isSubmitting ? "Signing in…" : "Sign in"}
          </Button>
        </form>
      </CardContent>
    </Card>
  )
}
```

- [ ] **Step 2: Replace `frontend/app/(auth)/login/page.tsx`**

```tsx
"use client"

import { useEffect } from "react"
import { useRouter } from "next/navigation"
import { useAuth } from "@/lib/auth"
import { LoginForm } from "@/components/forms/LoginForm"

export default function LoginPage() {
  const { token, isLoading } = useAuth()
  const router = useRouter()

  useEffect(() => {
    if (!isLoading && token) {
      router.push("/visits")
    }
  }, [isLoading, token, router])

  return (
    <main className="flex min-h-screen items-center justify-center bg-background px-4">
      <LoginForm />
    </main>
  )
}
```

- [ ] **Step 3: Verify login page renders**

```bash
cd frontend && npm run dev
```

Navigate to `http://localhost:3000/login`. Expected: Dark card with "Habitare" title, email + password inputs, "Sign in" button. `Ctrl+C`.

- [ ] **Step 4: Commit**

```bash
cd ..
git add frontend/
git commit -m "feat(ui): login page with zod validation and JWT storage"
```

---

## Chunk 3: Data Views

### Task 9: Generic DataTable component + column definitions

**Files:**
- Create: `frontend/components/data-table/DataTable.tsx`
- Create: `frontend/components/data-table/columns/visits.tsx`
- Create: `frontend/components/data-table/columns/visitors.tsx`
- Create: `frontend/components/data-table/columns/invitations.tsx`
- Create: `frontend/components/data-table/columns/users.tsx`

- [ ] **Step 1: Create `frontend/components/data-table/DataTable.tsx`**

```tsx
"use client"

import { useState } from "react"
import {
  type ColumnDef,
  type ColumnFiltersState,
  type SortingState,
  flexRender,
  getCoreRowModel,
  getFilteredRowModel,
  getPaginationRowModel,
  getSortedRowModel,
  useReactTable,
} from "@tanstack/react-table"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Skeleton } from "@/components/ui/skeleton"

interface DataTableProps<TData, TValue> {
  columns: ColumnDef<TData, TValue>[]
  data: TData[]
  isLoading?: boolean
  searchColumn?: string
  searchPlaceholder?: string
  toolbar?: React.ReactNode
}

export function DataTable<TData, TValue>({
  columns,
  data,
  isLoading,
  searchColumn,
  searchPlaceholder = "Search…",
  toolbar,
}: DataTableProps<TData, TValue>) {
  const [sorting, setSorting] = useState<SortingState>([])
  const [columnFilters, setColumnFilters] = useState<ColumnFiltersState>([])

  const table = useReactTable({
    data,
    columns,
    onSortingChange: setSorting,
    onColumnFiltersChange: setColumnFilters,
    getCoreRowModel: getCoreRowModel(),
    getPaginationRowModel: getPaginationRowModel(),
    getSortedRowModel: getSortedRowModel(),
    getFilteredRowModel: getFilteredRowModel(),
    initialState: { pagination: { pageSize: 10 } },
    state: { sorting, columnFilters },
  })

  return (
    <div className="flex flex-col gap-4">
      <div className="flex items-center gap-2">
        {searchColumn && (
          <Input
            placeholder={searchPlaceholder}
            value={(table.getColumn(searchColumn)?.getFilterValue() as string) ?? ""}
            onChange={(e) => table.getColumn(searchColumn)?.setFilterValue(e.target.value)}
            className="max-w-sm"
          />
        )}
        {toolbar}
      </div>

      <div className="rounded-md border border-border">
        <Table>
          <TableHeader>
            {table.getHeaderGroups().map((headerGroup) => (
              <TableRow key={headerGroup.id} className="border-border hover:bg-card">
                {headerGroup.headers.map((header) => (
                  <TableHead
                    key={header.id}
                    className="text-muted-foreground cursor-pointer select-none"
                    onClick={header.column.getToggleSortingHandler()}
                  >
                    {header.isPlaceholder
                      ? null
                      : flexRender(header.column.columnDef.header, header.getContext())}
                    {header.column.getIsSorted() === "asc" ? " ↑" : header.column.getIsSorted() === "desc" ? " ↓" : ""}
                  </TableHead>
                ))}
              </TableRow>
            ))}
          </TableHeader>
          <TableBody>
            {isLoading ? (
              Array.from({ length: 5 }).map((_, i) => (
                <TableRow key={i} className="border-border">
                  {columns.map((_, j) => (
                    <TableCell key={j}>
                      <Skeleton className="h-4 w-full" />
                    </TableCell>
                  ))}
                </TableRow>
              ))
            ) : table.getRowModel().rows.length ? (
              table.getRowModel().rows.map((row) => (
                <TableRow key={row.id} className="border-border hover:bg-card/60 cursor-pointer">
                  {row.getVisibleCells().map((cell) => (
                    <TableCell key={cell.id}>
                      {flexRender(cell.column.columnDef.cell, cell.getContext())}
                    </TableCell>
                  ))}
                </TableRow>
              ))
            ) : (
              <TableRow>
                <TableCell colSpan={columns.length} className="h-24 text-center text-muted-foreground">
                  No results.
                </TableCell>
              </TableRow>
            )}
          </TableBody>
        </Table>
      </div>

      <div className="flex items-center justify-between text-sm text-muted-foreground">
        <span>
          Page {table.getState().pagination.pageIndex + 1} of {table.getPageCount()}
        </span>
        <div className="flex gap-2">
          <Button
            variant="outline"
            size="sm"
            onClick={() => table.previousPage()}
            disabled={!table.getCanPreviousPage()}
          >
            Previous
          </Button>
          <Button
            variant="outline"
            size="sm"
            onClick={() => table.nextPage()}
            disabled={!table.getCanNextPage()}
          >
            Next
          </Button>
        </div>
      </div>
    </div>
  )
}
```

- [ ] **Step 2: Create `frontend/components/data-table/columns/visits.tsx`**

```tsx
"use client"

import type { ColumnDef } from "@tanstack/react-table"
import { Badge } from "@/components/ui/badge"
import { formatDate, statusBadgeVariant } from "@/lib/utils"

export interface Visit {
  id: string
  visitor_name: string
  unit_number: string | null
  checked_in_at: string
  status: string
  host_email: string | null
}

export const visitColumns: ColumnDef<Visit>[] = [
  {
    accessorKey: "visitor_name",
    header: "Visitor",
  },
  {
    accessorKey: "unit_number",
    header: "Unit",
    cell: ({ getValue }) => getValue() ?? "—",
  },
  {
    accessorKey: "checked_in_at",
    header: "Check-in",
    cell: ({ getValue }) => formatDate(getValue() as string),
  },
  {
    accessorKey: "status",
    header: "Status",
    cell: ({ getValue }) => {
      const status = getValue() as string
      const { className } = statusBadgeVariant(status)
      return <Badge className={className}>{status}</Badge>
    },
  },
  {
    accessorKey: "host_email",
    header: "Host",
    cell: ({ getValue }) => getValue() ?? "—",
  },
]
```

- [ ] **Step 3: Create `frontend/components/data-table/columns/visitors.tsx`**

```tsx
"use client"

import type { ColumnDef } from "@tanstack/react-table"
import { formatDate } from "@/lib/utils"

export interface Visitor {
  id: string
  full_name: string
  email: string | null
  phone_number: string | null
  unit_number: string | null
  last_visit_at: string | null
}

export const visitorColumns: ColumnDef<Visitor>[] = [
  {
    accessorKey: "full_name",
    header: "Name",
  },
  {
    accessorKey: "email",
    header: "Email",
    cell: ({ getValue }) => getValue() ?? "—",
  },
  {
    accessorKey: "phone_number",
    header: "Phone",
    cell: ({ getValue }) => getValue() ?? "—",
  },
  {
    accessorKey: "unit_number",
    header: "Unit",
    cell: ({ getValue }) => getValue() ?? "—",
  },
  {
    accessorKey: "last_visit_at",
    header: "Last Visit",
    cell: ({ getValue }) => {
      const v = getValue() as string | null
      return v ? formatDate(v) : "—"
    },
  },
]
```

- [ ] **Step 4: Create `frontend/components/data-table/columns/invitations.tsx`**

```tsx
"use client"

import type { ColumnDef } from "@tanstack/react-table"
import { Badge } from "@/components/ui/badge"
import { formatDate, statusBadgeVariant } from "@/lib/utils"

export interface Invitation {
  id: string
  host_email: string
  visitor_name: string
  created_at: string
  expires_at: string
  status: string
}

export const invitationColumns: ColumnDef<Invitation>[] = [
  {
    accessorKey: "host_email",
    header: "Host",
  },
  {
    accessorKey: "visitor_name",
    header: "Visitor",
  },
  {
    accessorKey: "created_at",
    header: "Created",
    cell: ({ getValue }) => formatDate(getValue() as string),
  },
  {
    accessorKey: "expires_at",
    header: "Expires",
    cell: ({ getValue }) => formatDate(getValue() as string),
  },
  {
    accessorKey: "status",
    header: "Status",
    cell: ({ getValue }) => {
      const status = getValue() as string
      const { className } = statusBadgeVariant(status)
      return <Badge className={className}>{status}</Badge>
    },
  },
]
```

- [ ] **Step 5: Create `frontend/components/data-table/columns/users.tsx`**

```tsx
"use client"

import type { ColumnDef } from "@tanstack/react-table"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu"
import { MoreHorizontal } from "lucide-react"

export interface TenantUser {
  id: string
  full_name: string | null
  email: string
  role: string
  is_active: boolean
}

export function makeUserColumns(
  onToggleActive: (user: TenantUser) => void,
): ColumnDef<TenantUser>[] {
  return [
    {
      accessorKey: "full_name",
      header: "Name",
      cell: ({ getValue }) => getValue() ?? "—",
    },
    {
      accessorKey: "email",
      header: "Email",
    },
    {
      accessorKey: "role",
      header: "Role",
      cell: ({ getValue }) => {
        const role = getValue() as string
        return (
          <Badge variant="outline" className="text-xs capitalize">
            {role.toLowerCase().replace("_", " ")}
          </Badge>
        )
      },
    },
    {
      accessorKey: "is_active",
      header: "Status",
      cell: ({ getValue }) => {
        const active = getValue() as boolean
        return (
          <Badge className={active
            ? "bg-green-500/20 text-green-400 border border-green-500/30"
            : "bg-red-500/20 text-red-400 border border-red-500/30"}>
            {active ? "Active" : "Inactive"}
          </Badge>
        )
      },
    },
    {
      id: "actions",
      cell: ({ row }) => {
        const user = row.original
        return (
          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <Button variant="ghost" className="h-8 w-8 p-0">
                <MoreHorizontal className="h-4 w-4" />
              </Button>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="end">
              <DropdownMenuItem onClick={() => onToggleActive(user)}>
                {user.is_active ? "Deactivate" : "Reactivate"}
              </DropdownMenuItem>
            </DropdownMenuContent>
          </DropdownMenu>
        )
      },
    },
  ]
}
```

- [ ] **Step 6: Commit**

```bash
cd ..
git add frontend/
git commit -m "feat(ui): DataTable component + column definitions for all entities"
```

---

### Task 10: Visits page

**Files:**
- Modify: `frontend/app/(dashboard)/visits/page.tsx`

- [ ] **Step 1: Install `date-fns` (needed for `format`)**

```bash
cd frontend && npm install date-fns
```

- [ ] **Step 2: Replace `frontend/app/(dashboard)/visits/page.tsx`**

```tsx
"use client"

import { useState } from "react"
import { useQuery } from "@tanstack/react-query"
import { toast } from "sonner"
import { format } from "date-fns"
import { Calendar } from "@/components/ui/calendar"
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover"
import { Button } from "@/components/ui/button"
import { CalendarIcon } from "lucide-react"
import { DataTable } from "@/components/data-table/DataTable"
import { visitColumns, type Visit } from "@/components/data-table/columns/visits"
import { apiFetch, ApiError } from "@/lib/api"
import { cn } from "@/lib/utils"

export default function VisitsPage() {
  const [date, setDate] = useState<Date>(new Date())
  const [calOpen, setCalOpen] = useState(false)

  const dateStr = format(date, "yyyy-MM-dd")

  const { data, isLoading } = useQuery<Visit[]>({
    queryKey: ["visits", dateStr],
    queryFn: async () => {
      try {
        return await apiFetch<Visit[]>(`/visits/?date=${dateStr}`)
      } catch (err) {
        toast.error(err instanceof ApiError ? err.message : "Failed to load visits")
        return []
      }
    },
  })

  return (
    <div className="flex flex-col gap-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold text-foreground">Visits</h1>
        <Popover open={calOpen} onOpenChange={setCalOpen}>
          <PopoverTrigger asChild>
            <Button
              variant="outline"
              className={cn("w-48 justify-start text-left font-normal", !date && "text-muted-foreground")}
            >
              <CalendarIcon className="mr-2 h-4 w-4" />
              {format(date, "PPP")}
            </Button>
          </PopoverTrigger>
          <PopoverContent className="w-auto p-0" align="end">
            <Calendar
              mode="single"
              selected={date}
              onSelect={(d) => {
                if (d) { setDate(d); setCalOpen(false) }
              }}
              initialFocus
            />
          </PopoverContent>
        </Popover>
      </div>

      <DataTable
        columns={visitColumns}
        data={data ?? []}
        isLoading={isLoading}
        searchColumn="visitor_name"
        searchPlaceholder="Search by visitor name…"
      />
    </div>
  )
}
```

- [ ] **Step 3: Verify page compiles**

```bash
npm run dev
```

Navigate to `http://localhost:3000/login`, log in with real credentials (backend must be running on port 8001). Expected: Redirected to `/visits`, table shows today's visits (or "No results" if none). `Ctrl+C`.

- [ ] **Step 4: Commit**

```bash
cd ..
git add frontend/
git commit -m "feat(ui): visits page with date picker and DataTable"
```

---

### Task 11: Visitors page + VisitorHistorySheet

**Files:**
- Modify: `frontend/app/(dashboard)/visitors/page.tsx`
- Create: `frontend/components/visitors/VisitorHistorySheet.tsx`

- [ ] **Step 1: Create `frontend/components/visitors/VisitorHistorySheet.tsx`**

```tsx
"use client"

import { useQuery } from "@tanstack/react-query"
import {
  Sheet,
  SheetContent,
  SheetHeader,
  SheetTitle,
  SheetDescription,
} from "@/components/ui/sheet"
import { Badge } from "@/components/ui/badge"
import { ScrollArea } from "@/components/ui/scroll-area"
import { Skeleton } from "@/components/ui/skeleton"
import { apiFetch } from "@/lib/api"
import { formatDate, statusBadgeVariant } from "@/lib/utils"
import type { Visitor } from "@/components/data-table/columns/visitors"

interface VisitHistory {
  id: string
  checked_in_at: string
  status: string
  host_email: string | null
  unit_number: string | null
}

interface VisitorHistorySheetProps {
  visitor: Visitor | null
  onClose: () => void
}

export function VisitorHistorySheet({ visitor, onClose }: VisitorHistorySheetProps) {
  const { data, isLoading } = useQuery<VisitHistory[]>({
    queryKey: ["visitor-visits", visitor?.id],
    queryFn: () => apiFetch<VisitHistory[]>(`/visitors/${visitor!.id}/visits`),
    enabled: !!visitor,
  })

  return (
    <Sheet open={!!visitor} onOpenChange={(open) => { if (!open) onClose() }}>
      <SheetContent className="w-96 bg-card border-border">
        <SheetHeader>
          <SheetTitle className="text-foreground">{visitor?.full_name}</SheetTitle>
          <SheetDescription className="text-muted-foreground">{visitor?.email}</SheetDescription>
        </SheetHeader>

        <ScrollArea className="mt-6 h-[calc(100vh-120px)]">
          <p className="mb-3 text-sm font-semibold text-muted-foreground uppercase tracking-wide">Visit History</p>
          {isLoading ? (
            <div className="flex flex-col gap-3">
              {Array.from({ length: 4 }).map((_, i) => (
                <Skeleton key={i} className="h-16 w-full rounded-md" />
              ))}
            </div>
          ) : data?.length ? (
            <div className="flex flex-col gap-3">
              {data.map((visit) => {
                const { className } = statusBadgeVariant(visit.status)
                return (
                  <div key={visit.id} className="rounded-md border border-border bg-background p-3">
                    <div className="flex items-center justify-between">
                      <span className="text-sm text-foreground">{formatDate(visit.checked_in_at)}</span>
                      <Badge className={className}>{visit.status}</Badge>
                    </div>
                    {visit.host_email && (
                      <p className="mt-1 text-xs text-muted-foreground">Host: {visit.host_email}</p>
                    )}
                  </div>
                )
              })}
            </div>
          ) : (
            <p className="text-sm text-muted-foreground">No visits recorded.</p>
          )}
        </ScrollArea>
      </SheetContent>
    </Sheet>
  )
}
```

- [ ] **Step 2: Add `onRowClick` prop to `frontend/components/data-table/DataTable.tsx`**

Add to the `DataTableProps` interface:
```tsx
onRowClick?: (row: TData) => void
```

Update the `<TableRow>` in the body to call it:
```tsx
<TableRow
  key={row.id}
  className="border-border hover:bg-card/60 cursor-pointer"
  onClick={() => onRowClick?.(row.original)}
>
```

- [ ] **Step 3: Create `frontend/app/(dashboard)/visitors/page.tsx`**

```tsx
"use client"

import { useState } from "react"
import { useQuery } from "@tanstack/react-query"
import { toast } from "sonner"
import { DataTable } from "@/components/data-table/DataTable"
import { visitorColumns, type Visitor } from "@/components/data-table/columns/visitors"
import { VisitorHistorySheet } from "@/components/visitors/VisitorHistorySheet"
import { apiFetch, ApiError } from "@/lib/api"

export default function VisitorsPage() {
  const [selectedVisitor, setSelectedVisitor] = useState<Visitor | null>(null)

  const { data, isLoading } = useQuery<Visitor[]>({
    queryKey: ["visitors"],
    queryFn: async () => {
      try {
        return await apiFetch<Visitor[]>("/visitors/")
      } catch (err) {
        toast.error(err instanceof ApiError ? err.message : "Failed to load visitors")
        return []
      }
    },
  })

  return (
    <div className="flex flex-col gap-6">
      <h1 className="text-2xl font-bold text-foreground">Visitors</h1>

      <DataTable
        columns={visitorColumns}
        data={data ?? []}
        isLoading={isLoading}
        searchColumn="full_name"
        searchPlaceholder="Search by name…"
        onRowClick={setSelectedVisitor}
      />

      <VisitorHistorySheet
        visitor={selectedVisitor}
        onClose={() => setSelectedVisitor(null)}
      />
    </div>
  )
}
```

- [ ] **Step 4: Commit**

```bash
cd ..
git add frontend/
git commit -m "feat(ui): visitors page with VisitorHistorySheet slide-over"
```

---

### Task 12: Invitations page + CreateInvitationForm

**Files:**
- Modify: `frontend/app/(dashboard)/invitations/page.tsx`
- Create: `frontend/components/forms/CreateInvitationForm.tsx`

- [ ] **Step 1: Create `frontend/components/forms/CreateInvitationForm.tsx`**

```tsx
"use client"

import { useForm } from "react-hook-form"
import { zodResolver } from "@hookform/resolvers/zod"
import { z } from "zod"
import { useState } from "react"
import { format, addDays } from "date-fns"
import { toast } from "sonner"
import { useQueryClient } from "@tanstack/react-query"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogFooter,
} from "@/components/ui/dialog"
import { Calendar } from "@/components/ui/calendar"
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover"
import { CalendarIcon } from "lucide-react"
import { apiFetch, ApiError } from "@/lib/api"
import { cn } from "@/lib/utils"

const schema = z.object({
  visitor_email: z.string().email("Enter a valid email"),
  visitor_name: z.string().min(1, "Visitor name is required"),
  unit_number: z.string().optional(),
})

type FormData = z.infer<typeof schema>

interface CreateInvitationFormProps {
  open: boolean
  onClose: () => void
}

export function CreateInvitationForm({ open, onClose }: CreateInvitationFormProps) {
  const queryClient = useQueryClient()
  const [expiresAt, setExpiresAt] = useState<Date>(addDays(new Date(), 7))
  const [calOpen, setCalOpen] = useState(false)

  const {
    register,
    handleSubmit,
    reset,
    setError,
    formState: { errors, isSubmitting },
  } = useForm<FormData>({ resolver: zodResolver(schema) })

  async function onSubmit(data: FormData) {
    try {
      await apiFetch("/invitations/", {
        method: "POST",
        body: JSON.stringify({
          ...data,
          unit_number: data.unit_number || null,
          expires_at: expiresAt.toISOString(),
        }),
      })
      toast.success("Invitation created")
      queryClient.invalidateQueries({ queryKey: ["invitations"] })
      reset()
      setExpiresAt(addDays(new Date(), 7))
      onClose()
    } catch (err) {
      if (err instanceof ApiError && err.status === 422 && Array.isArray(err.detail)) {
        // Map FastAPI validation errors to inline field errors
        for (const item of err.detail as Array<{ loc: string[]; msg: string }>) {
          const field = item.loc[item.loc.length - 1] as keyof FormData
          setError(field, { message: item.msg })
        }
      } else {
        toast.error(err instanceof ApiError ? err.message : "Failed to create invitation")
      }
    }
  }

  return (
    <Dialog open={open} onOpenChange={(o) => { if (!o) onClose() }}>
      <DialogContent className="bg-card border-border">
        <DialogHeader>
          <DialogTitle>Create Invitation</DialogTitle>
        </DialogHeader>
        <form onSubmit={handleSubmit(onSubmit)} className="flex flex-col gap-4 pt-2">
          <div className="flex flex-col gap-1.5">
            <Label>Visitor Email *</Label>
            <Input placeholder="visitor@example.com" {...register("visitor_email")} />
            {errors.visitor_email && <p className="text-xs text-destructive">{errors.visitor_email.message}</p>}
          </div>

          <div className="flex flex-col gap-1.5">
            <Label>Visitor Name *</Label>
            <Input placeholder="Jane Doe" {...register("visitor_name")} />
            {errors.visitor_name && <p className="text-xs text-destructive">{errors.visitor_name.message}</p>}
          </div>

          <div className="flex flex-col gap-1.5">
            <Label>Unit Number</Label>
            <Input placeholder="4B (optional)" {...register("unit_number")} />
          </div>

          <div className="flex flex-col gap-1.5">
            <Label>Expires At *</Label>
            <Popover open={calOpen} onOpenChange={setCalOpen}>
              <PopoverTrigger asChild>
                <Button variant="outline" className={cn("justify-start text-left font-normal")}>
                  <CalendarIcon className="mr-2 h-4 w-4" />
                  {format(expiresAt, "PPP")}
                </Button>
              </PopoverTrigger>
              <PopoverContent className="w-auto p-0">
                <Calendar
                  mode="single"
                  selected={expiresAt}
                  onSelect={(d) => { if (d) { setExpiresAt(d); setCalOpen(false) } }}
                  disabled={(d) => d < new Date()}
                  initialFocus
                />
              </PopoverContent>
            </Popover>
          </div>

          <DialogFooter>
            <Button type="button" variant="outline" onClick={onClose}>Cancel</Button>
            <Button type="submit" disabled={isSubmitting}>
              {isSubmitting ? "Creating…" : "Create"}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}
```

- [ ] **Step 2: Replace `frontend/app/(dashboard)/invitations/page.tsx`**

```tsx
"use client"

import { useState } from "react"
import { useQuery } from "@tanstack/react-query"
import { toast } from "sonner"
import { Button } from "@/components/ui/button"
import { Plus } from "lucide-react"
import { DataTable } from "@/components/data-table/DataTable"
import { invitationColumns, type Invitation } from "@/components/data-table/columns/invitations"
import { CreateInvitationForm } from "@/components/forms/CreateInvitationForm"
import { apiFetch, ApiError } from "@/lib/api"

export default function InvitationsPage() {
  const [createOpen, setCreateOpen] = useState(false)

  const { data, isLoading } = useQuery<Invitation[]>({
    queryKey: ["invitations"],
    queryFn: async () => {
      try {
        return await apiFetch<Invitation[]>("/invitations/")
      } catch (err) {
        toast.error(err instanceof ApiError ? err.message : "Failed to load invitations")
        return []
      }
    },
  })

  return (
    <div className="flex flex-col gap-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold text-foreground">Invitations</h1>
        <Button onClick={() => setCreateOpen(true)}>
          <Plus className="mr-2 h-4 w-4" />
          Create invitation
        </Button>
      </div>

      <DataTable
        columns={invitationColumns}
        data={data ?? []}
        isLoading={isLoading}
        searchColumn="visitor_name"
        searchPlaceholder="Search by visitor name…"
      />

      <CreateInvitationForm open={createOpen} onClose={() => setCreateOpen(false)} />
    </div>
  )
}
```

- [ ] **Step 3: Commit**

```bash
cd ..
git add frontend/
git commit -m "feat(ui): invitations page with CreateInvitationForm modal"
```

---

### Task 13: Users page + CreateUserForm

**Files:**
- Modify: `frontend/app/(dashboard)/users/page.tsx`
- Create: `frontend/components/forms/CreateUserForm.tsx`

- [ ] **Step 1: Create `frontend/components/forms/CreateUserForm.tsx`**

```tsx
"use client"

import { useForm } from "react-hook-form"
import { zodResolver } from "@hookform/resolvers/zod"
import { z } from "zod"
import { useState } from "react"
import { toast } from "sonner"
import { useQueryClient } from "@tanstack/react-query"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogFooter,
} from "@/components/ui/dialog"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import { apiFetch, ApiError } from "@/lib/api"

const schema = z.object({
  email: z.string().email("Enter a valid email"),
  full_name: z.string().optional(),
  phone_number: z.string().optional(),
  unit_number: z.string().optional(),
  role: z.enum(["TENANT_USER", "PROPERTY_ADMIN"]),
})

type FormData = z.infer<typeof schema>

interface CreateUserResponse {
  id: string
  email: string
  temp_password: string
}

interface CreateUserFormProps {
  open: boolean
  onClose: () => void
}

export function CreateUserForm({ open, onClose }: CreateUserFormProps) {
  const queryClient = useQueryClient()
  const [tempPassword, setTempPassword] = useState<string | null>(null)

  const {
    register,
    handleSubmit,
    reset,
    setValue,
    setError,
    formState: { errors, isSubmitting },
  } = useForm<FormData>({
    resolver: zodResolver(schema),
    defaultValues: { role: "TENANT_USER" },
  })

  async function onSubmit(data: FormData) {
    try {
      const resp = await apiFetch<CreateUserResponse>("/users/", {
        method: "POST",
        body: JSON.stringify({
          email: data.email,
          full_name: data.full_name || null,
          phone_number: data.phone_number || null,
          unit_number: data.unit_number || null,
          role: data.role,
        }),
      })
      setTempPassword(resp.temp_password)
      queryClient.invalidateQueries({ queryKey: ["users"] })
      reset()
    } catch (err) {
      if (err instanceof ApiError && err.status === 422 && Array.isArray(err.detail)) {
        // Map FastAPI validation errors to inline field errors
        for (const item of err.detail as Array<{ loc: string[]; msg: string }>) {
          const field = item.loc[item.loc.length - 1] as keyof FormData
          setError(field, { message: item.msg })
        }
      } else {
        toast.error(err instanceof ApiError ? err.message : "Failed to create user")
      }
    }
  }

  function handleClose() {
    setTempPassword(null)
    onClose()
  }

  // Show temp password dialog after creation
  if (tempPassword) {
    return (
      <Dialog open={open} onOpenChange={(o) => { if (!o) handleClose() }}>
        <DialogContent className="bg-card border-border">
          <DialogHeader>
            <DialogTitle>User Created</DialogTitle>
          </DialogHeader>
          <div className="flex flex-col gap-3 py-2">
            <p className="text-sm text-muted-foreground">
              Share this temporary password with the new user. It will not be shown again.
            </p>
            <div className="rounded-md border border-border bg-background p-3 font-mono text-primary text-lg tracking-widest text-center">
              {tempPassword}
            </div>
          </div>
          <DialogFooter>
            <Button onClick={handleClose}>Done</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    )
  }

  return (
    <Dialog open={open} onOpenChange={(o) => { if (!o) handleClose() }}>
      <DialogContent className="bg-card border-border">
        <DialogHeader>
          <DialogTitle>Add User</DialogTitle>
        </DialogHeader>
        <form onSubmit={handleSubmit(onSubmit)} className="flex flex-col gap-4 pt-2">
          <div className="flex flex-col gap-1.5">
            <Label>Email *</Label>
            <Input placeholder="staff@example.com" {...register("email")} />
            {errors.email && <p className="text-xs text-destructive">{errors.email.message}</p>}
          </div>

          <div className="flex flex-col gap-1.5">
            <Label>Full Name</Label>
            <Input placeholder="Jane Doe" {...register("full_name")} />
          </div>

          <div className="flex flex-col gap-1.5">
            <Label>Phone Number</Label>
            <Input placeholder="+1 555 0100" {...register("phone_number")} />
          </div>

          <div className="flex flex-col gap-1.5">
            <Label>Unit Number</Label>
            <Input placeholder="4B" {...register("unit_number")} />
          </div>

          <div className="flex flex-col gap-1.5">
            <Label>Role *</Label>
            <Select onValueChange={(v) => setValue("role", v as "TENANT_USER" | "PROPERTY_ADMIN")} defaultValue="TENANT_USER">
              <SelectTrigger>
                <SelectValue placeholder="Select role" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="TENANT_USER">Tenant User</SelectItem>
                <SelectItem value="PROPERTY_ADMIN">Property Admin</SelectItem>
              </SelectContent>
            </Select>
            {errors.role && <p className="text-xs text-destructive">{errors.role.message}</p>}
          </div>

          <DialogFooter>
            <Button type="button" variant="outline" onClick={handleClose}>Cancel</Button>
            <Button type="submit" disabled={isSubmitting}>
              {isSubmitting ? "Creating…" : "Add User"}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}
```

- [ ] **Step 2: Install shadcn Select component (if not already added)**

```bash
cd frontend && npx shadcn@latest add select --yes
```

- [ ] **Step 3: Replace `frontend/app/(dashboard)/users/page.tsx`**

```tsx
"use client"

import { useEffect, useState } from "react"
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query"
import { useRouter } from "next/navigation"
import { toast } from "sonner"
import { Button } from "@/components/ui/button"
import { UserPlus } from "lucide-react"
import { DataTable } from "@/components/data-table/DataTable"
import { makeUserColumns, type TenantUser } from "@/components/data-table/columns/users"
import { CreateUserForm } from "@/components/forms/CreateUserForm"
import { apiFetch, ApiError } from "@/lib/api"
import { useAuth } from "@/lib/auth"

export default function UsersPage() {
  const { user } = useAuth()
  const router = useRouter()
  const queryClient = useQueryClient()
  const [createOpen, setCreateOpen] = useState(false)

  // Role guard: UX redirect (backend enforces independently)
  useEffect(() => {
    if (user && user.role === "TENANT_USER") {
      router.push("/visits")
    }
  }, [user, router])

  const { data, isLoading } = useQuery<TenantUser[]>({
    queryKey: ["users"],
    queryFn: async () => {
      try {
        return await apiFetch<TenantUser[]>("/users/")
      } catch (err) {
        toast.error(err instanceof ApiError ? err.message : "Failed to load users")
        return []
      }
    },
    enabled: user?.role !== "TENANT_USER",
  })

  const toggleActive = useMutation({
    mutationFn: (u: TenantUser) =>
      apiFetch(`/users/${u.id}`, {
        method: "PUT",
        body: JSON.stringify({ is_active: !u.is_active }),
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["users"] })
      toast.success("User updated")
    },
    onError: (err) => {
      toast.error(err instanceof ApiError ? err.message : "Failed to update user")
    },
  })

  const columns = makeUserColumns((u) => toggleActive.mutate(u))

  return (
    <div className="flex flex-col gap-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold text-foreground">Users</h1>
        <Button onClick={() => setCreateOpen(true)}>
          <UserPlus className="mr-2 h-4 w-4" />
          Add user
        </Button>
      </div>

      <DataTable
        columns={columns}
        data={data ?? []}
        isLoading={isLoading}
        searchColumn="email"
        searchPlaceholder="Search by email…"
      />

      <CreateUserForm open={createOpen} onClose={() => setCreateOpen(false)} />
    </div>
  )
}
```

- [ ] **Step 4: Commit**

```bash
cd ..
git add frontend/
git commit -m "feat(ui): users page with role guard, CreateUserForm, deactivate action"
```

---

## Chunk 4: Settings + Final

### Task 14: Settings page + SettingsForm

**Files:**
- Create: `frontend/components/forms/SettingsForm.tsx`
- Modify: `frontend/app/(dashboard)/settings/page.tsx`

- [ ] **Step 1: Create `frontend/components/forms/SettingsForm.tsx`**

```tsx
"use client"

import { useForm } from "react-hook-form"
import { zodResolver } from "@hookform/resolvers/zod"
import { z } from "zod"
import { useEffect } from "react"
import { toast } from "sonner"
import { useQuery, useQueryClient } from "@tanstack/react-query"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { apiFetch, ApiError } from "@/lib/api"
import { useAuth } from "@/lib/auth"

interface UserProfile {
  id: string
  email: string
  full_name: string | null
  phone_number: string | null
  unit_number: string | null
  role: string
}

const schema = z.object({
  full_name: z.string().optional(),
  phone_number: z.string().optional(),
  unit_number: z.string().optional(),
})

type FormData = z.infer<typeof schema>

export function SettingsForm() {
  const { updateUser } = useAuth()

  const { data: profile, isLoading } = useQuery<UserProfile>({
    queryKey: ["profile"],
    queryFn: () => apiFetch<UserProfile>("/users/me"),
  })

  const {
    register,
    handleSubmit,
    reset,
    formState: { isSubmitting, isDirty },
  } = useForm<FormData>({ resolver: zodResolver(schema) })

  // Populate form once profile loads
  useEffect(() => {
    if (profile) {
      reset({
        full_name: profile.full_name ?? "",
        phone_number: profile.phone_number ?? "",
        unit_number: profile.unit_number ?? "",
      })
    }
  }, [profile, reset])

  async function onSubmit(data: FormData) {
    try {
      const updated = await apiFetch<UserProfile>("/users/me", {
        method: "PUT",
        body: JSON.stringify({
          full_name: data.full_name || null,
          phone_number: data.phone_number || null,
          unit_number: data.unit_number || null,
        }),
      })
      // User interface uses camelCase; API response uses snake_case — map explicitly
      updateUser({
        email: updated.email,
        fullName: updated.full_name ?? undefined,
        phoneNumber: updated.phone_number ?? undefined,
        unitNumber: updated.unit_number ?? undefined,
      })
      toast.success("Profile updated")
      reset({ full_name: updated.full_name ?? "", phone_number: updated.phone_number ?? "", unit_number: updated.unit_number ?? "" })
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : "Failed to update profile")
    }
  }

  if (isLoading) {
    return <div className="text-muted-foreground">Loading…</div>
  }

  return (
    <Card className="max-w-lg">
      <CardHeader>
        <CardTitle>Profile</CardTitle>
      </CardHeader>
      <CardContent>
        <div className="mb-4 flex flex-col gap-1">
          <span className="text-xs text-muted-foreground uppercase tracking-wide">Email</span>
          <span className="text-sm text-foreground">{profile?.email}</span>
        </div>
        <div className="mb-6 flex flex-col gap-1">
          <span className="text-xs text-muted-foreground uppercase tracking-wide">Role</span>
          <span className="text-sm text-foreground capitalize">
            {profile?.role?.toLowerCase().replace("_", " ")}
          </span>
        </div>

        <form onSubmit={handleSubmit(onSubmit)} className="flex flex-col gap-4">
          <div className="flex flex-col gap-1.5">
            <Label>Full Name</Label>
            <Input placeholder="Your name" {...register("full_name")} />
          </div>

          <div className="flex flex-col gap-1.5">
            <Label>Phone Number</Label>
            <Input placeholder="+1 555 0100" {...register("phone_number")} />
          </div>

          <div className="flex flex-col gap-1.5">
            <Label>Unit Number</Label>
            <Input placeholder="4B" {...register("unit_number")} />
          </div>

          <Button type="submit" className="self-start" disabled={isSubmitting || !isDirty}>
            {isSubmitting ? "Saving…" : "Save changes"}
          </Button>
        </form>
      </CardContent>
    </Card>
  )
}
```

- [ ] **Step 2: Replace `frontend/app/(dashboard)/settings/page.tsx`**

```tsx
"use client"

import { SettingsForm } from "@/components/forms/SettingsForm"

export default function SettingsPage() {
  return (
    <div className="flex flex-col gap-6">
      <h1 className="text-2xl font-bold text-foreground">Settings</h1>
      <SettingsForm />
    </div>
  )
}
```

- [ ] **Step 3: Run all tests**

```bash
cd frontend && npm test
```

Expected: 13 tests PASS (utils × 7, ApiError × 3, auth × 3).

- [ ] **Step 4: Commit**

```bash
cd ..
git add frontend/
git commit -m "feat(ui): settings page with profile form and success toast"
```

---

### Task 15: End-to-end smoke test + push

**Goal:** Verify the full user journey works against the running FastAPI backend.

**Prerequisites:**
- FastAPI backend running: `uv run uvicorn app.main:app --reload --port 8001`
- PostgreSQL + Redis running: `docker-compose up -d`
- A user account exists in the database (use the seeded demo user or create one via `POST /auth/register` if available, or via DB seed)

- [ ] **Step 1: Start the frontend**

```bash
cd frontend && npm run dev
```

Expected: `http://localhost:3000` running.

- [ ] **Step 2: Login flow**

1. Navigate to `http://localhost:3000` — should redirect to `/login`
2. Enter invalid credentials — expected: red toast error "Invalid credentials" (or whatever the backend returns)
3. Enter valid credentials — expected: redirected to `/visits`, sidebar visible with amber "H" logo

- [ ] **Step 3: Verify sidebar**

1. Sidebar shows: Visits, Visitors, Invitations, Settings (for TENANT_USER) OR all 5 items (for PROPERTY_ADMIN)
2. Click sidebar collapse trigger — expected: sidebar collapses to icon-only
3. Click trigger again — expected: sidebar expands

- [ ] **Step 4: Verify Visits page**

1. `/visits` loads — DataTable shows today's visits or "No results"
2. Change date via date picker — table re-fetches for that date

- [ ] **Step 5: Verify Visitors page**

1. `/visitors` loads — DataTable shows visitors
2. Click a row — VisitorHistorySheet slides in from right, shows visit history

- [ ] **Step 6: Verify Invitations page**

1. `/invitations` loads — DataTable shows invitations
2. Click "Create invitation" — dialog opens, fill form, submit — table refreshes

- [ ] **Step 7: Verify Settings page**

1. `/settings` loads — form pre-filled with current user's profile
2. Edit Full Name, click Save — success toast appears, button goes back to disabled (no dirty state)

- [ ] **Step 8: Verify auth protection**

1. Open a new browser tab, navigate to `http://localhost:3000/visits` — should briefly show spinner then redirect to `/login` (no token in new tab's localStorage)

- [ ] **Step 9: Run final test suite**

```bash
npm test
```

Expected: 13 tests PASS.

- [ ] **Step 10: Commit and push**

```bash
cd ..
git add frontend/
git commit -m "feat(ui): complete Phase 6 admin dashboard smoke test verified"
git push -u origin feat/phase-6-admin-ui
```
