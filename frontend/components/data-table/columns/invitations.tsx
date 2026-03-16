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
