import { describe, expect, it } from "vitest";
import { canSeeCompliance } from "./staffing-roles";

describe("canSeeCompliance", () => {
  it("Admin und Teamleiter sehen Compliance", () => {
    expect(canSeeCompliance({ is_admin: true, role: "admin" })).toBe(true);
    expect(canSeeCompliance({ is_admin: true })).toBe(true);
    expect(canSeeCompliance({ is_admin: false, role: "team_lead" })).toBe(true);
  });

  it("Vermittler und unbekannte Nutzer nicht", () => {
    expect(canSeeCompliance({ is_admin: false, role: "member" })).toBe(false);
    expect(canSeeCompliance({ is_admin: false })).toBe(false);
    expect(canSeeCompliance(null)).toBe(false);
    expect(canSeeCompliance(undefined)).toBe(false);
  });
});
