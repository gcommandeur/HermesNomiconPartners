import { describe, expect, it } from "vitest";

import { isFollowUpDue } from "./follow-up";

const NOW = new Date(2026, 9, 16, 10, 0, 0); // 16.10.2026, 10:00 lokal

describe("isFollowUpDue", () => {
  it("markiert nichts ohne Termin", () => {
    expect(isFollowUpDue(null, NOW)).toBe(false);
    expect(isFollowUpDue(undefined, NOW)).toBe(false);
    expect(isFollowUpDue("", NOW)).toBe(false);
  });

  it("markiert überfällige Termine", () => {
    expect(isFollowUpDue(new Date(2026, 9, 5, 9, 0).toISOString(), NOW)).toBe(true);
    expect(isFollowUpDue(new Date(2026, 9, 15, 23, 59).toISOString(), NOW)).toBe(true);
  });

  it("markiert den heutigen Termin bis Tagesende", () => {
    expect(isFollowUpDue(new Date(2026, 9, 16, 8, 0).toISOString(), NOW)).toBe(true);
    expect(isFollowUpDue(new Date(2026, 9, 16, 23, 30).toISOString(), NOW)).toBe(true);
  });

  it("markiert zukünftige Termine nicht", () => {
    expect(isFollowUpDue(new Date(2026, 9, 17, 0, 1).toISOString(), NOW)).toBe(false);
    expect(isFollowUpDue(new Date(2026, 10, 3, 9, 0).toISOString(), NOW)).toBe(false);
  });
});
