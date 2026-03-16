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
    cell: ({ getValue }) => (getValue() as string | null) ?? "—",
  },
  {
    accessorKey: "phone_number",
    header: "Phone",
    cell: ({ getValue }) => (getValue() as string | null) ?? "—",
  },
  {
    accessorKey: "unit_number",
    header: "Unit",
    cell: ({ getValue }) => (getValue() as string | null) ?? "—",
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
