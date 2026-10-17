// NOMICON: Arbeitnehmerüberlassung - Texte zur Fristanzeige als reine Funktionen (gut testbar,
// ohne Netzwerk-Imports). Siehe components/crm/staffing-ui.tsx.

const DAYS_PER_MONTH = 30.4375;

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
