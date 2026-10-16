// NOMICON: Entscheidung, ob ein Prozess als "Nachfassen fällig" markiert wird (Kanban, Tabelle).
// Reine Funktion, damit sie mit festem Datum testbar ist. Markiert wird erst, wenn der geplante
// Nachfass-Termin erreicht oder überschritten ist (bis Ende des heutigen Tages); Prozesse ohne
// Termin und Termine in der Zukunft sind normal. Schwelle: der Tag des Termins selbst.
export function isFollowUpDue(followUpAt: string | null | undefined, now: Date = new Date()): boolean {
  if (!followUpAt) return false;
  const endOfToday = new Date(now);
  endOfToday.setHours(23, 59, 59, 999);
  return new Date(followUpAt) <= endOfToday;
}

/** Klassen für Karten mit fälligem Nachfassen: Warnung über Kantenstreifen und Rahmen, der Text bleibt
 * auf hellem Grund lesbar (keine volle rote Fläche). */
export const FOLLOW_UP_DUE_CARD_CLASS =
  "border-brand-danger/50 border-l-4 border-l-brand-danger bg-brand-danger/10 hover:border-brand-danger/80";
