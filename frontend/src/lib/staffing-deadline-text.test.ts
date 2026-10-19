import { describe, expect, it } from "vitest";
import { formatPriorDays, isOverlapConflict, overdueSummary, provisionalReasonText } from "./staffing-deadline-text";

describe("provisionalReasonText", () => {
  it("nennt, was an der Frist fehlt", () => {
    expect(provisionalReasonText(["planned_assignment"])).toBe("Vorläufig: Einsatz noch nicht aktiviert");
    expect(provisionalReasonText(["prior_unconfirmed"])).toBe("Vorläufig: Vorzeiten nicht bestätigt");
    expect(provisionalReasonText(["planned_assignment", "open_end"])).toBe(
      "Vorläufig: Einsatz noch nicht aktiviert; kein Enddatum erfasst",
    );
    expect(provisionalReasonText([])).toBe("Vorläufig");
    expect(provisionalReasonText(undefined)).toBe("Vorläufig");
  });
});

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
