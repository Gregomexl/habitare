import { clsx, type ClassValue } from "clsx"
import { twMerge } from "tailwind-merge"

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs))
}

export function formatDate(dateStr: string): string {
  // Use timeZone: "UTC" to prevent date-only strings ("2026-03-15") from rolling
  // back one day in UTC-west timezones. new Date("2026-03-15") parses as UTC midnight.
  return new Date(dateStr).toLocaleDateString("en-US", {
    timeZone: "UTC",
    month: "short",
    day: "numeric",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  })
}

type BadgeStyle = { variant: "default" | "secondary" | "destructive" | "outline"; className: string }

export function statusBadgeVariant(status: string): BadgeStyle {
  switch (status.toUpperCase()) {
    case "CHECKED_IN":
    case "SENT":
    case "ACTIVE":
      return { variant: "default", className: "bg-green-500/20 text-green-400 border border-green-500/30" }
    case "PENDING":
      return { variant: "default", className: "bg-orange-500/20 text-orange-400 border border-orange-500/30" }
    case "CHECKED_OUT":
    case "EXPIRED":
    case "USED":
      return { variant: "secondary", className: "bg-zinc-700/50 text-zinc-400 border border-zinc-600/30" }
    case "FAILED":
    case "CANCELLED":
      return { variant: "destructive", className: "bg-red-500/20 text-red-400 border border-red-500/30" }
    default:
      return { variant: "secondary", className: "bg-zinc-700/50 text-zinc-400 border border-zinc-600/30" }
  }
}
