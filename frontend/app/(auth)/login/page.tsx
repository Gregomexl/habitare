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
