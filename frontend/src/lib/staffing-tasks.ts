// NOMICON: Darstellung der Aufgaben der Ansicht Überlassung (reine Funktionen, testbar).
import type { StaffingTask } from "./api/staffing";

/** Ziel der Aufgabe: Einsatz, Leiharbeitnehmer oder Compliance (Erlaubnis). */
export function taskHref(task: Pick<StaffingTask, "kind" | "assignment_id" | "worker_id">): string {
  if (task.assignment_id) return `/ueberlassung/einsaetze/${task.assignment_id}`;
  if (task.worker_id) return `/ueberlassung/leiharbeitnehmer/${task.worker_id}`;
  if (task.kind === "license") return "/ueberlassung/compliance";
  return "/ueberlassung";
}

export const TASK_KIND_LABELS: Record<StaffingTask["kind"], string> = {
  deadline_max: "Frist",
  equal_pay: "Equal Pay",
  timesheet_missing: "Stundenzettel",
  timesheet_overdue: "Stundenzettel",
  timesheet_rejected: "Stundenzettel",
  checklist_open: "Checkliste",
  bench: "Bench",
  license: "Erlaubnis",
};

export const SEVERITY_ORDER: Record<StaffingTask["severity"], number> = { red: 0, yellow: 1, info: 2 };

/** Zählt die Aufgaben je Dringlichkeit für die Kopfzeile. */
export function countBySeverity(tasks: Pick<StaffingTask, "severity">[]): Record<StaffingTask["severity"], number> {
  const counts = { red: 0, yellow: 0, info: 0 };
  for (const task of tasks) counts[task.severity] += 1;
  return counts;
}
