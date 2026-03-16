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
