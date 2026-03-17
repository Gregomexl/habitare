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
    onError: (err: unknown) => {
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
        searchPlaceholder="Search by email\u2026"
      />

      <CreateUserForm open={createOpen} onClose={() => setCreateOpen(false)} />
    </div>
  )
}
