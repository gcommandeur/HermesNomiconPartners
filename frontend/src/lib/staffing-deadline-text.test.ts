import { describe, expect, it } from "vitest";
import { formatPriorDays } from "./staffing-deadline-text";

describe("formatPriorDays", () => {
  it("bleibt leer ohne Vorzeit", () => {
    expect(formatPriorDays(0)).toBe("");
    expect(formatPriorDays(undefined)).toBe("");
    expect(formatPriorDays(null)).toBe("");
  });

  it("nennt kurze Vorzeiten in Tagen", () => {
    expect(formatPriorDays(1)).toBe("inkl. 1 Tag Vorzeit");
    expect(formatPriorDays(20)).toBe("inkl. 20 Tage Vorzeit");
  });

  it("rundet längere Vorzeiten auf Monate", () => {
    expect(formatPriorDays(31)).toBe("inkl. 1 Monat Vorzeit");
    expect(formatPriorDays(304)).toBe("inkl. 10 Monate Vorzeit");
  });
});
