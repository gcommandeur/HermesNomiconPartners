import { describe, expect, it } from "vitest";

import type { StaffingCandidateSummary } from "./api/staffing";
import { candidateStaffingActions, canSeeStaffing, staffingCandidateText, staffingWarning } from "./staffing-candidate";

function summary(partial: Partial<StaffingCandidateSummary>): StaffingCandidateSummary {
  return { candidate_id: "c1", status: "active", worker_id: "w1", client_name: null, assignment_status: null, traffic: null, days_remaining: null, bench: false, ...partial } as StaffingCandidateSummary;
}

describe("staffingCandidateText", () => {
  it("bleibt leer ohne Leiharbeitnehmer-Profil", () => {
    expect(staffingCandidateText(undefined)).toBe("");
    expect(staffingCandidateText(summary({ status: "none" }))).toBe("");
  });

  it("zeigt Status, bei Aktiv den Kunden und bei gelber/roter Frist die Resttage", () => {
    expect(staffingCandidateText(summary({ status: "applicant" }))).toBe("Anwärter");
    expect(staffingCandidateText(summary({ client_name: "Muster GmbH" }))).toBe("Aktiv · Muster GmbH");
    expect(staffingCandidateText(summary({ client_name: "Muster GmbH", traffic: "yellow", days_remaining: 26 }))).toBe("Aktiv · Muster GmbH · Frist noch 26 Tage");
    expect(staffingCandidateText(summary({ bench: true }))).toBe("Aktiv · Bench");
  });

  it("enthält nie Lohn- oder Margenangaben (Felder gibt es im Typ nicht)", () => {
    const text = staffingCandidateText(summary({ client_name: "X" }));
    expect(text).not.toMatch(/€|Lohn|Marge/);
  });
});

describe("staffingWarning", () => {
  it("warnt nur bei gelb oder rot", () => {
    expect(staffingWarning({ traffic: "green", days_remaining: 100 })).toBeNull();
    expect(staffingWarning({ traffic: null, days_remaining: null })).toBeNull();
    expect(staffingWarning({ traffic: "red", days_remaining: 1 })).toBe("Frist noch 1 Tag");
    expect(staffingWarning({ traffic: "red", days_remaining: -3 })).toBe("Frist seit 3 Tagen überschritten");
    expect(staffingWarning({ traffic: "yellow", days_remaining: null })).toBe("Frist prüfen");
  });
});

describe("Sichtbarkeit und Aktionen", () => {
  it("Spalte, Filter und Abschnitt nur mit Ansicht Überlassung", () => {
    expect(canSeeStaffing(["direct", "staffing"])).toBe(true);
    expect(canSeeStaffing(["direct"])).toBe(false);
    expect(canSeeStaffing(["management"])).toBe(false);
    expect(canSeeStaffing(undefined)).toBe(false);
    expect(canSeeStaffing([])).toBe(false);
  });

  it("'Als Leiharbeitnehmer anlegen' nur ohne Profil, neuer Einsatz nur für Anwärter und Aktive", () => {
    expect(candidateStaffingActions(null)).toEqual({ create: true, edit: false, newAssignment: false });
    expect(candidateStaffingActions({ status: "applicant" })).toEqual({ create: false, edit: true, newAssignment: true });
    expect(candidateStaffingActions({ status: "active" })).toEqual({ create: false, edit: true, newAssignment: true });
    expect(candidateStaffingActions({ status: "left" })).toEqual({ create: false, edit: true, newAssignment: false });
  });
});
