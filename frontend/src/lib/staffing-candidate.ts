// NOMICON: Darstellung der Spalte "Überlassung" in der Kandidatenliste (reine Funktionen, testbar).
import { CANDIDATE_STAFFING_STATUS_LABELS, type StaffingCandidateSummary } from "./api/staffing";

/** Text der Zelle und des CSV-Exports: Status, bei Aktiv der Kunde, bei gelber/roter Frist die Resttage. */
export function staffingCandidateText(summary: StaffingCandidateSummary | undefined): string {
  if (!summary || summary.status === "none") return "";
  const parts: string[] = [CANDIDATE_STAFFING_STATUS_LABELS[summary.status]];
  if (summary.status === "active" && summary.client_name) parts.push(summary.client_name);
  if (summary.bench) parts.push("Bench");
  const warn = staffingWarning(summary);
  if (warn) parts.push(warn);
  return parts.join(" · ");
}

/** Warnung nur bei gelber oder roter Frist: "Frist noch 26 Tage" bzw. "Frist überschritten". */
export function staffingWarning(summary: Pick<StaffingCandidateSummary, "traffic" | "days_remaining">): string | null {
  if (summary.traffic !== "yellow" && summary.traffic !== "red") return null;
  const days = summary.days_remaining;
  if (days === null || days === undefined) return "Frist prüfen";
  if (days < 0) return `Frist seit ${-days} ${-days === 1 ? "Tag" : "Tagen"} überschritten`;
  return `Frist noch ${days} ${days === 1 ? "Tag" : "Tage"}`;
}

/** Sichtbarkeit von Spalte, Filter und Abschnitt "Überlassung" am Kandidaten: nur mit der Ansicht
 * Überlassung (der Server erzwingt dasselbe mit 403). */
export function canSeeStaffing(views: readonly string[] | null | undefined): boolean {
  return Boolean(views?.includes("staffing"));
}

/** Welche Hauptaktion der Abschnitt "Überlassung" am Kandidaten anbietet: ohne Profil "Als Leiharbeitnehmer
 * anlegen" (verknüpft den bestehenden Kandidaten, kein zweiter Datensatz), sonst Bearbeiten; neue Einsätze
 * nur für Personen "In Auswahl" und aktive Personen. */
export function candidateStaffingActions(worker: { status: string } | null | undefined): { create: boolean; edit: boolean; newAssignment: boolean } {
  if (!worker) return { create: true, edit: false, newAssignment: false };
  return { create: false, edit: true, newAssignment: worker.status === "active" || worker.status === "applicant" };
}
