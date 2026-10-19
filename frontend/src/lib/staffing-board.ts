// NOMICON: Spaltenlogik des Überlassungs-Kanbans (reine Funktionen, testbar). Statusregel für
// Leiharbeitnehmer: docs/UEBERLASSUNG.md, Abschnitt "Status eines Leiharbeitnehmers".
import type { StaffingAssignment, StaffingWorker } from "./api/staffing";

/** In Auswahl und In Überlassung bewegt man von Hand, "Überlassung endet bald" füllt sich von selbst. */
export type KanbanColumn = "selection" | "running" | "ending";

/** So viele Wochen vor dem geplanten Ende rutscht ein laufender Einsatz nach "Überlassung endet bald". */
export const ENDING_SOON_WEEKS = 6;

export function daysBetween(from: Date, to: Date): number {
  return Math.round((to.getTime() - from.getTime()) / 86_400_000);
}

/** Tage bis zum geplanten Ende (negativ: überfällig); `null` ohne geplantes Ende. */
export function daysUntilEnd(a: Pick<StaffingAssignment, "planned_end_date">, today: Date): number | null {
  return a.planned_end_date ? daysBetween(today, new Date(a.planned_end_date)) : null;
}

/** Spalte eines Einsatzes: geplant = In Auswahl (von Hand nach "In Überlassung" setzen); aktiv = In Überlassung,
 * und ab ENDING_SOON_WEEKS Wochen vor dem geplanten Ende (auch überfällig) "Überlassung endet bald".
 * Beendete und abgebrochene Einsätze stehen nicht im Kanban. */
export function classifyKanban(a: Pick<StaffingAssignment, "status" | "planned_end_date">, today: Date): KanbanColumn | null {
  if (a.status === "planned") return "selection";
  if (a.status !== "active") return null;
  const left = daysUntilEnd(a, today);
  return left !== null && left <= ENDING_SOON_WEEKS * 7 ? "ending" : "running";
}

/** Personen "In Auswahl" (interner Status "applicant") ohne geplanten oder aktiven Einsatz: erscheinen als
 * Personenkarte in der Spalte "In Auswahl", damit niemand im Kanban fehlt, nur weil noch kein Einsatz angelegt
 * ist. Personen In Auswahl MIT geplantem Einsatz stehen bereits über den Einsatz im Kanban. */
export function applicantsWithoutAssignment(
  workers: Pick<StaffingWorker, "id" | "status">[],
  assignments: Pick<StaffingAssignment, "worker_id" | "status">[],
): string[] {
  const busy = new Set(assignments.filter((a) => a.status === "planned" || a.status === "active").map((a) => a.worker_id));
  return workers.filter((w) => w.status === "applicant" && !busy.has(w.id)).map((w) => w.id);
}
