// NOMICON: Spaltenlogik des Einsatz-Boards (reine Funktionen, testbar). Statusregel für
// Leiharbeitnehmer: docs/UEBERLASSUNG.md, Abschnitt "Status eines Leiharbeitnehmers".
import type { StaffingAssignment, StaffingWorker, Traffic } from "./api/staffing";

export type ColumnKey = "onboarding" | "planned" | "active" | "ending" | "ended";

export const ENDING_SOON_DAYS = 30;
export const ENDED_VISIBLE_DAYS = 30;

function daysBetween(from: Date, to: Date): number {
  return Math.round((to.getTime() - from.getTime()) / 86_400_000);
}

export function classifyAssignment(a: StaffingAssignment, traffic: Traffic | undefined, today: Date): ColumnKey | null {
  if (a.status === "aborted") return null;
  if (a.status === "ended") {
    const end = a.actual_end_date ?? a.planned_end_date;
    return end && daysBetween(new Date(end), today) <= ENDED_VISIBLE_DAYS ? "ended" : null;
  }
  if (a.status === "planned") return a.checklist_done < a.checklist_total ? "onboarding" : "planned";
  const endsSoon = a.planned_end_date !== null && daysBetween(today, new Date(a.planned_end_date)) <= ENDING_SOON_DAYS;
  return traffic === "yellow" || traffic === "red" || endsSoon ? "ending" : "active";
}

/** Anwärter ohne geplanten oder aktiven Einsatz: erscheinen als Personenkarte in "Anwärter / Onboarding",
 * damit niemand im Board fehlt, nur weil noch kein Einsatz angelegt ist. Anwärter MIT geplantem
 * Einsatz stehen bereits über den Einsatz im Board. */
export function applicantsWithoutAssignment(
  workers: Pick<StaffingWorker, "id" | "status">[],
  assignments: Pick<StaffingAssignment, "worker_id" | "status">[],
): string[] {
  const busy = new Set(assignments.filter((a) => a.status === "planned" || a.status === "active").map((a) => a.worker_id));
  return workers.filter((w) => w.status === "applicant" && !busy.has(w.id)).map((w) => w.id);
}
