import { describe, it, expect } from "vitest"
import { ApiError } from "@/lib/api"

describe("ApiError", () => {
  it("is an instance of Error", () => {
    const err = new ApiError("HTTP_403", "Forbidden", null, 403)
    expect(err).toBeInstanceOf(Error)
    expect(err).toBeInstanceOf(ApiError)
  })

  it("has correct name", () => {
    const err = new ApiError("HTTP_403", "Forbidden", null, 403)
    expect(err.name).toBe("ApiError")
  })

  it("exposes code, message, detail, status", () => {
    const err = new ApiError("VALIDATION_ERROR", "Invalid body", [{ loc: ["body", "email"] }], 422)
    expect(err.code).toBe("VALIDATION_ERROR")
    expect(err.message).toBe("Invalid body")
    expect(err.detail).toEqual([{ loc: ["body", "email"] }])
    expect(err.status).toBe(422)
  })
})
