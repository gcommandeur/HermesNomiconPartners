import { describe, expect, it } from "vitest";
import { formatPriorDays, isOverlapConflict, overdueSummary } from "./staffing-deadline-text";

describe("isOverlapConflict", () => {
  it("erkennt die Überschneidungs-Meldung des Servers", () => {
    expect(isOverlapConflict("Überschneidung: Dieser Leiharbeitnehmer hat im selben Zeitraum bereits ...")).toBe(true);
    expect(isOverlapConflict("Dieser Kandidat ist bereits im Austausch: ...")).toBe(false);
  });
});

describe("overdueSummary", () => {
  it("steht im Singular und Plural", () => {
    expect(overdueSummary(1)).toBe("1 Einsatz überfällig");
    expect(overdueSummary(3)).toBe("3 Einsätze überfällig");
  });
});

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
