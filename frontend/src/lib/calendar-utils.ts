/** Reine Datums-Hilfsfunktionen fuer die selbstgebaute Monats-/Wochenraster-
 * Ansicht (/kalender) - bewusst ohne Kalender-Bibliothek (z.B. FullCalendar),
 * da ein einfaches Raster ausreicht und eine schwere Abhaengigkeit fuer
 * dieses Feature nicht gerechtfertigt waere (siehe Bericht). Woche startet
 * Montag (deutsche Konvention). */

export function addDays(date: Date, days: number): Date {
  const result = new Date(date);
  result.setDate(result.getDate() + days);
  return result;
}

export function isSameDay(a: Date, b: Date): boolean {
  return (
    a.getFullYear() === b.getFullYear() &&
    a.getMonth() === b.getMonth() &&
    a.getDate() === b.getDate()
  );
}

export function startOfDay(date: Date): Date {
  const result = new Date(date);
  result.setHours(0, 0, 0, 0);
  return result;
}

/** Montag dieser Woche. */
export function startOfWeek(date: Date): Date {
  const result = startOfDay(date);
  const day = result.getDay(); // 0=Sonntag, 1=Montag, ...
  const diff = day === 0 ? -6 : 1 - day;
  return addDays(result, diff);
}

export function startOfMonth(date: Date): Date {
  return new Date(date.getFullYear(), date.getMonth(), 1);
}

export function endOfMonth(date: Date): Date {
  return new Date(date.getFullYear(), date.getMonth() + 1, 0);
}

/** Erster Tag des 6-Wochen-Rasters, das den Monat vollstaendig abdeckt
 * (fuellt mit Tagen des Vor-/Folgemonats auf, damit jede Woche 7 Tage hat). */
export function startOfMonthGrid(date: Date): Date {
  return startOfWeek(startOfMonth(date));
}

export function endOfMonthGrid(date: Date): Date {
  const lastDay = endOfMonth(date);
  const day = lastDay.getDay();
  const diff = day === 0 ? 0 : 7 - day;
  return addDays(startOfDay(lastDay), diff);
}

/** Lokale (Berlin-Wanduhrzeit) "YYYY-MM-DDTHH:mm:ss"-Darstellung ohne
 * Zeitzonen-Suffix - konsistent mit der Server-Annahme aus
 * services/ics_feed.py (Zeiten sind feste Europe/Berlin-Wanduhrzeit, kein
 * UTC-Umrechnen). `toISOString()` waere hier falsch, da es UTC verwendet. */
export function toLocalIsoString(date: Date): string {
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}T${pad(date.getHours())}:${pad(date.getMinutes())}:${pad(date.getSeconds())}`;
}

const MONTH_FORMATTER = new Intl.DateTimeFormat("de-DE", { month: "long", year: "numeric" });
const WEEKDAY_FORMATTER = new Intl.DateTimeFormat("de-DE", { weekday: "short" });
const DAY_FORMATTER = new Intl.DateTimeFormat("de-DE", { day: "2-digit", month: "2-digit" });
const TIME_FORMATTER = new Intl.DateTimeFormat("de-DE", { hour: "2-digit", minute: "2-digit" });

export function formatMonthLabel(date: Date): string {
  return MONTH_FORMATTER.format(date);
}

export function formatWeekdayLabel(date: Date): string {
  return WEEKDAY_FORMATTER.format(date);
}

export function formatDayLabel(date: Date): string {
  return DAY_FORMATTER.format(date);
}

/** Zeit-Anteil eines vom Backend gelieferten ISO-Strings, direkt ohne
 * Date-Parsing (vermeidet Zeitzonen-Reinterpretation, siehe
 * calendar-event-modal.tsx fuer denselben Ansatz bei Formularen). */
export function formatTimeFromIso(iso: string): string {
  const match = iso.match(/T(\d{2}):(\d{2})/);
  return match ? `${match[1]}:${match[2]}` : TIME_FORMATTER.format(new Date(iso));
}

/** Datum-Anteil (YYYY-MM-DD) eines vom Backend gelieferten ISO-Strings,
 * direkt ohne Date-Parsing - fuer den Tag-Vergleich beim Einsortieren von
 * Terminen ins Raster (siehe calendar-view.tsx). */
export function dateKeyFromIso(iso: string): string {
  return iso.slice(0, 10);
}

export function dateKey(date: Date): string {
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}`;
}
