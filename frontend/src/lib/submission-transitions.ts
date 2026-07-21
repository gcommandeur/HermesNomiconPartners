import type { SubmissionStatus } from "@/lib/api/types";

/** Einzige Quelle der erlaubten Status-Uebergaenge im Frontend - muss mit
 * dem Backend (services/submissions.py::ALLOWED_TRANSITIONS) uebereinstimmen.
 * Vorher als Duplikat in submission-views.tsx gepflegt; jetzt zentral, damit
 * Kanban-Drag&Drop und die Stufen-Bearbeitung auf der Kandidat-Detailseite
 * immer dieselben Regeln anzeigen. Jeder nicht erlaubte Uebergang wird vom
 * Backend ohnehin mit einem BusinessRuleError abgelehnt - diese Map dient
 * nur der Frontend-seitigen Vorab-Pruefung/UI (z.B. "Status setzen"-Button
 * nur bei gueltigem Ziel aktiv).
 *
 * Rueckwaerts-Wechsel sind bewusst nicht vorgesehen: jede Stufe darf nur in
 * die naechste (oder nach "cancelled") wechseln, nie zurueck.
 */
export const allowedTransitions: Partial<Record<SubmissionStatus, SubmissionStatus[]>> = {
  qualification_call: ["cv_in", "cancelled"],
  cv_in: ["cv_out", "cancelled"],
  cv_out: ["interview", "cancelled"],
  interview: ["offer", "cancelled"],
  offer: ["placement", "cancelled"],
  placement: [],
  cancelled: [],
};

export function isAllowedTransition(from: SubmissionStatus, to: SubmissionStatus): boolean {
  return (allowedTransitions[from] ?? []).includes(to);
}
