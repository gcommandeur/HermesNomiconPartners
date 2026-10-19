import { describe, expect, it } from "vitest";

import type { StaffingAssignment } from "./api/staffing";
import { applicantsWithoutAssignment, classifyAssignment } from "./staffing-board";

const TODAY = new Date(2026, 9, 16);

function assignment(partial: Partial<StaffingAssignment>): StaffingAssignment {
  return {
    status: "active",
    checklist_done: 6,
    checklist_total: 6,
    planned_end_date: null,
    actual_end_date: null,
    ...partial,
  } as StaffingAssignment;
}

describe("classifyAssignment", () => {
  it("geplant mit offener Checkliste ist Onboarding, mit vollständiger Checkliste Geplant", () => {
    expect(classifyAssignment(assignment({ status: "planned", checklist_done: 3 }), undefined, TODAY)).toBe("onboarding");
    expect(classifyAssignment(assignment({ status: "planned" }), undefined, TODAY)).toBe("planned");
  });

  it("aktiv ist Aktiv, mit Fristenampel gelb/rot oder nahem Ende Läuft aus", () => {
    expect(classifyAssignment(assignment({}), "green", TODAY)).toBe("active");
    expect(classifyAssignment(assignment({}), "yellow", TODAY)).toBe("ending");
    expect(classifyAssignment(assignment({ planned_end_date: "2026-10-30" }), undefined, TODAY)).toBe("ending");
  });

  it("beendet zeigt nur die letzten 30 Tage, abgebrochen nie", () => {
    expect(classifyAssignment(assignment({ status: "ended", actual_end_date: "2026-10-01" }), undefined, TODAY)).toBe("ended");
    expect(classifyAssignment(assignment({ status: "ended", actual_end_date: "2026-08-01" }), undefined, TODAY)).toBeNull();
    expect(classifyAssignment(assignment({ status: "aborted" }), undefined, TODAY)).toBeNull();
  });
});

describe("applicantsWithoutAssignment", () => {
  const workers = [
    { id: "w1", status: "applicant" as const },
    { id: "w2", status: "applicant" as const },
    { id: "w3", status: "active" as const },
  ];

  it("nennt Personen In Auswahl ohne geplanten oder aktiven Einsatz", () => {
    const result = applicantsWithoutAssignment(workers, [{ worker_id: "w2", status: "planned" }]);
    expect(result).toEqual(["w1"]);
  });

  it("ein beendeter Einsatz macht die Person In Auswahl nicht beschäftigt", () => {
    expect(applicantsWithoutAssignment(workers, [{ worker_id: "w1", status: "ended" }])).toEqual(["w1", "w2"]);
  });

  it("ignoriert Aktive, Ruhende und Ausgeschiedene", () => {
    expect(applicantsWithoutAssignment([{ id: "x", status: "dormant" }, { id: "y", status: "left" }], [])).toEqual([]);
  });
});
