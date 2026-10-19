// NOMICON: Arbeitnehmerüberlassung - Texte zur Fristanzeige als reine Funktionen (gut testbar,
// ohne Netzwerk-Imports). Siehe components/crm/staffing-ui.tsx.

const DAYS_PER_MONTH = 30.4375;

/** Meldung des Servers (HTTP 409), wenn ein anderer Einsatz derselben Person im selben Zeitraum liegt. */
export function isOverlapConflict(message: string): boolean {
  return message.startsWith("Überschneidung:");
}

const PROVISIONAL_TEXT: Record<string, string> = {
  planned_assignment: "Einsatz noch nicht aktiviert",
  open_end: "kein Enddatum erfasst",
  prior_unconfirmed: "Vorzeiten nicht bestätigt",
};

/** Tooltip für „vorläufig“: was an der Frist noch fehlt (Gründe vom Server als Codes). */
export function provisionalReasonText(reasons: readonly string[] | null | undefined): string {
  const text = (reasons ?? []).map((reason) => PROVISIONAL_TEXT[reason] ?? reason).join("; ");
  return text ? `Vorläufig: ${text}` : "Vorläufig";
}

/** Warnzeile der Übersicht: "1 Einsatz überfällig" / "3 Einsätze überfällig". */
export function overdueSummary(count: number): string {
  return `${count} ${count === 1 ? "Einsatz" : "Einsätze"} überfällig`;
}

/** "inkl. 10 Monate Vorzeit": Anteil der Zählung, der aus früher beim Kunden geleisteten Zeiten
 * stammt (Vorzeiten). Unter einem Monat in Tagen. Leer, wenn es keine Vorzeit gibt. */
export function formatPriorDays(days: number | null | undefined): string {
  if (!days || days <= 0) return "";
  if (days < 31) return `inkl. ${days} ${days === 1 ? "Tag" : "Tage"} Vorzeit`;
  const months = Math.round(days / DAYS_PER_MONTH);
  return `inkl. ${months} ${months === 1 ? "Monat" : "Monate"} Vorzeit`;
}
