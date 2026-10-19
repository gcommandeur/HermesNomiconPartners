import { describe, expect, it } from "vitest";
import { candidateTabs, resolveCandidateTab } from "./candidate-tabs";

describe("candidateTabs", () => {
  it("zeigt den Reiter Überlassung nur mit der Ansicht Überlassung", () => {
    expect(candidateTabs(true).at(-1)).toBe("Überlassung");
    expect(candidateTabs(false)).not.toContain("Überlassung");
  });

  it("lässt die Direct-Seite unverändert", () => {
    expect(candidateTabs(false)).toEqual(["Übersicht", "Anonymes Profil", "Notizen", "Matching", "CV-Outs", "Timeline", "Aufgaben", "Dokumente"]);
  });
});

describe("resolveCandidateTab", () => {
  const withStaffing = candidateTabs(true);

  it("nimmt den genauen Namen oder die Schreibweise ohne Umlaut aus den Weiterleitungen", () => {
    expect(resolveCandidateTab("Dokumente", withStaffing)).toBe("Dokumente");
    expect(resolveCandidateTab("Überlassung", withStaffing)).toBe("Überlassung");
    expect(resolveCandidateTab("ueberlassung", withStaffing)).toBe("Überlassung");
    expect(resolveCandidateTab("UEBERLASSUNG", withStaffing)).toBe("Überlassung");
  });

  it("fällt auf Übersicht zurück, wenn der Reiter fehlt, unbekannt oder nicht freigeschaltet ist", () => {
    expect(resolveCandidateTab(undefined, withStaffing)).toBe("Übersicht");
    expect(resolveCandidateTab("gibt-es-nicht", withStaffing)).toBe("Übersicht");
    expect(resolveCandidateTab("ueberlassung", candidateTabs(false))).toBe("Übersicht"); // Direct: kein Reiter
  });
});
