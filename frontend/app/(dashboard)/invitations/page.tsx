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
        searchPlaceholder="Search by visitor name\u2026"
      />

      <CreateInvitationForm open={createOpen} onClose={() => setCreateOpen(false)} />
    </div>
  )
}
