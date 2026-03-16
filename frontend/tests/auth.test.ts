import { describe, it, expect } from "vitest"

// We test only the pure decodeToken function by importing the decode logic
// AuthContext is a React component and is verified via the browser
import { jwtDecode } from "jwt-decode"

// A manually constructed JWT with the correct URL-safe base64 payload segment.
// jwtDecode requires URL-safe base64 (replace + with -, / with _, strip =).
function toBase64Url(obj: object): string {
  return btoa(JSON.stringify(obj))
    .replace(/\+/g, "-")
    .replace(/\//g, "_")
    .replace(/=/g, "")
}

const SAMPLE_TOKEN =
  "eyJhbGciOiJIUzI1NiJ9." +
  toBase64Url({
    user_id: "abc-123",
    tenant_id: "ten-456",
    role: "PROPERTY_ADMIN",
    email: "admin@example.com",
    exp: 9999999999,
  }) +
  ".fakesig"

describe("jwtDecode (token decode used by AuthContext)", () => {
  it("decodes user_id from payload", () => {
    const payload = jwtDecode<{ user_id: string }>(SAMPLE_TOKEN)
    expect(payload.user_id).toBe("abc-123")
  })

  it("decodes role from payload", () => {
    const payload = jwtDecode<{ role: string }>(SAMPLE_TOKEN)
    expect(payload.role).toBe("PROPERTY_ADMIN")
  })

  it("decodes email from payload", () => {
    const payload = jwtDecode<{ email: string }>(SAMPLE_TOKEN)
    expect(payload.email).toBe("admin@example.com")
  })
})
