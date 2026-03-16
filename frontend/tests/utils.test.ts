import { describe, it, expect } from "vitest"
import { formatDate, statusBadgeVariant } from "@/lib/utils"

describe("formatDate", () => {
  it("formats ISO datetime to readable string", () => {
    const result = formatDate("2026-03-15T14:30:00Z")
    expect(result).toMatch(/Mar 15, 2026/)
  })

  it("handles date-only string without timezone rollback", () => {
    // "2026-03-15" parsed as UTC midnight — implementation must use timeZone:"UTC"
    // to avoid rolling back to Mar 14 in UTC-west timezones.
    const result = formatDate("2026-03-15")
    expect(result).toMatch(/Mar 15, 2026/)
  })
})

describe("statusBadgeVariant", () => {
  it("returns success style for CHECKED_IN", () => {
    const result = statusBadgeVariant("CHECKED_IN")
    expect(result.className).toContain("green")
  })

  it("returns success style for ACTIVE", () => {
    const result = statusBadgeVariant("ACTIVE")
    expect(result.className).toContain("green")
  })

  it("returns warning style for PENDING", () => {
    const result = statusBadgeVariant("PENDING")
    expect(result.className).toContain("orange")
  })

  it("returns muted style for EXPIRED", () => {
    const result = statusBadgeVariant("EXPIRED")
    expect(result.className).toContain("zinc")
  })

  it("returns danger style for FAILED", () => {
    const result = statusBadgeVariant("FAILED")
    expect(result.className).toContain("red")
  })

  it("returns danger style for CANCELLED", () => {
    const result = statusBadgeVariant("CANCELLED")
    expect(result.className).toContain("red")
  })

  it("is case-insensitive", () => {
    expect(statusBadgeVariant("checked_in").className).toContain("green")
  })
})
