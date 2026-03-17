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
