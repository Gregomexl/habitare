"use client"

import { useQuery } from "@tanstack/react-query"
import {
  Sheet,
  SheetContent,
  SheetHeader,
  SheetTitle,
  SheetDescription,
} from "@/components/ui/sheet"
import { Badge } from "@/components/ui/badge"
import { ScrollArea } from "@/components/ui/scroll-area"
import { Skeleton } from "@/components/ui/skeleton"
import { apiFetch } from "@/lib/api"
import { formatDate, statusBadgeVariant } from "@/lib/utils"
import type { Visitor } from "@/components/data-table/columns/visitors"

interface VisitHistory {
  id: string
  checked_in_at: string
  status: string
  host_email: string | null
  unit_number: string | null
}

interface VisitorHistorySheetProps {
  visitor: Visitor | null
  onClose: () => void
}

export function VisitorHistorySheet({ visitor, onClose }: VisitorHistorySheetProps) {
  const { data, isLoading } = useQuery<VisitHistory[]>({
    queryKey: ["visitor-visits", visitor?.id],
    queryFn: () => apiFetch<VisitHistory[]>(`/visitors/${visitor!.id}/visits`),
    enabled: !!visitor,
  })

  return (
    <Sheet open={!!visitor} onOpenChange={(open) => { if (!open) onClose() }}>
      <SheetContent className="w-96 bg-card border-border">
        <SheetHeader>
          <SheetTitle className="text-foreground">{visitor?.full_name}</SheetTitle>
          <SheetDescription className="text-muted-foreground">{visitor?.email}</SheetDescription>
        </SheetHeader>

        <ScrollArea className="mt-6 h-[calc(100vh-120px)]">
          <p className="mb-3 text-sm font-semibold text-muted-foreground uppercase tracking-wide">Visit History</p>
          {isLoading ? (
            <div className="flex flex-col gap-3">
              {Array.from({ length: 4 }).map((_, i) => (
                <Skeleton key={i} className="h-16 w-full rounded-md" />
              ))}
            </div>
          ) : data?.length ? (
            <div className="flex flex-col gap-3">
              {data.map((visit) => {
                const { className } = statusBadgeVariant(visit.status)
                return (
                  <div key={visit.id} className="rounded-md border border-border bg-background p-3">
                    <div className="flex items-center justify-between">
                      <span className="text-sm text-foreground">{formatDate(visit.checked_in_at)}</span>
                      <Badge className={className}>{visit.status}</Badge>
                    </div>
                    {visit.host_email && (
                      <p className="mt-1 text-xs text-muted-foreground">Host: {visit.host_email}</p>
                    )}
                  </div>
                )
              })}
            </div>
          ) : (
            <p className="text-sm text-muted-foreground">No visits recorded.</p>
          )}
        </ScrollArea>
      </SheetContent>
    </Sheet>
  )
}
