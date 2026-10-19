import { describe, expect, it } from "vitest";
import { applicantsWithoutAssignment, classifyKanban, daysUntilEnd, ENDING_SOON_WEEKS } from "./staffing-board";

const TODAY = new Date("2026-10-19");

function day(offset: number): string {
  return new Date(TODAY.getTime() + offset * 86_400_000).toISOString().slice(0, 10);
}

describe("classifyKanban", () => {
  it("geplante Einsätze stehen In Auswahl, egal wie weit die Checkliste ist", () => {
    expect(classifyKanban({ status: "planned", planned_end_date: null }, TODAY)).toBe("selection");
    expect(classifyKanban({ status: "planned", planned_end_date: day(5) }, TODAY)).toBe("selection");
  });

  it("aktive Einsätze laufen, bis sechs Wochen vor dem Ende erreicht sind", () => {
    expect(classifyKanban({ status: "active", planned_end_date: null }, TODAY)).toBe("running");
    expect(classifyKanban({ status: "active", planned_end_date: day(ENDING_SOON_WEEKS * 7 + 1) }, TODAY)).toBe("running");
    expect(classifyKanban({ status: "active", planned_end_date: day(ENDING_SOON_WEEKS * 7) }, TODAY)).toBe("ending");
  });

  it("ein überfälliger aktiver Einsatz endet bald (und bleibt sichtbar)", () => {
    expect(classifyKanban({ status: "active", planned_end_date: day(-10) }, TODAY)).toBe("ending");
  });

  it("beendete und abgebrochene Einsätze fehlen im Kanban", () => {
    expect(classifyKanban({ status: "ended", planned_end_date: day(-10) }, TODAY)).toBeNull();
    expect(classifyKanban({ status: "aborted", planned_end_date: null }, TODAY)).toBeNull();
  });
});

describe("daysUntilEnd", () => {
  it("zählt Tage bis zum geplanten Ende, negativ wenn überfällig", () => {
    expect(daysUntilEnd({ planned_end_date: day(12) }, TODAY)).toBe(12);
    expect(daysUntilEnd({ planned_end_date: day(-3) }, TODAY)).toBe(-3);
    expect(daysUntilEnd({ planned_end_date: null }, TODAY)).toBeNull();
  });
});

describe("applicantsWithoutAssignment", () => {
  it("nimmt In-Auswahl-Personen ohne geplanten oder aktiven Einsatz", () => {
    const workers = [
      { id: "a", status: "applicant" as const },
      { id: "b", status: "applicant" as const },
      { id: "c", status: "active" as const },
    ];
    const assignments = [{ worker_id: "b", status: "planned" as const }];
    expect(applicantsWithoutAssignment(workers, assignments)).toEqual(["a"]);
  });
});
