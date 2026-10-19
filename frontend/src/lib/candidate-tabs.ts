// NOMICON: Reiter der Kandidatenseite (reine Funktionen, testbar). Der Reiter "Überlassung" erscheint nur
// mit der Ansicht Überlassung; ohne sie bleibt die Seite (Direct) unverändert.

export const BASE_CANDIDATE_TABS = ["Übersicht", "Anonymes Profil", "Notizen", "Matching", "CV-Outs", "Timeline", "Aufgaben", "Dokumente"] as const;
export const STAFFING_TAB = "Überlassung";

export function candidateTabs(canStaffing: boolean): string[] {
  return canStaffing ? [...BASE_CANDIDATE_TABS, STAFFING_TAB] : [...BASE_CANDIDATE_TABS];
}

function normalize(value: string): string {
  return value.trim().toLowerCase().replace(/ä/g, "ae").replace(/ö/g, "oe").replace(/ü/g, "ue").replace(/ß/g, "ss");
}

/** Reiter aus dem Link (`?tab=…`): genau, sonst ohne Groß-/Kleinschreibung und Umlaute ("ueberlassung" ->
 * "Überlassung"); unbekannt oder nicht freigeschaltet fällt auf "Übersicht" zurück. */
export function resolveCandidateTab(requested: string | null | undefined, tabs: string[]): string {
  if (!requested) return "Übersicht";
  if (tabs.includes(requested)) return requested;
  const wanted = normalize(requested);
  return tabs.find((tab) => normalize(tab) === wanted) ?? "Übersicht";
}
