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
