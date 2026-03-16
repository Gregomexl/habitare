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
