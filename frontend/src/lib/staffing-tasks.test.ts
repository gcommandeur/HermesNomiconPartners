import { describe, expect, it } from "vitest";

import { countBySeverity, taskHref } from "./staffing-tasks";

describe("taskHref", () => {
  it("führt zum Einsatz, sonst zum Leiharbeitnehmer, sonst zur Compliance-Seite", () => {
    expect(taskHref({ kind: "checklist_open", assignment_id: "a1", worker_id: "w1" })).toBe("/ueberlassung/einsaetze/a1");
    expect(taskHref({ kind: "bench", assignment_id: null, worker_id: "w1" })).toBe("/ueberlassung/leiharbeitnehmer/w1");
    expect(taskHref({ kind: "license", assignment_id: null, worker_id: null })).toBe("/ueberlassung/compliance");
    expect(taskHref({ kind: "equal_pay", assignment_id: null, worker_id: null })).toBe("/ueberlassung");
  });
});

describe("countBySeverity", () => {
  it("zählt je Dringlichkeit", () => {
    expect(countBySeverity([{ severity: "red" }, { severity: "red" }, { severity: "info" }])).toEqual({ red: 2, yellow: 0, info: 1 });
    expect(countBySeverity([])).toEqual({ red: 0, yellow: 0, info: 0 });
  });
});
