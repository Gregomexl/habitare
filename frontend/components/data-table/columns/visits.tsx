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
    cell: ({ getValue }) => (getValue() as string | null) ?? "—",
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
    cell: ({ getValue }) => (getValue() as string | null) ?? "—",
  },
]
