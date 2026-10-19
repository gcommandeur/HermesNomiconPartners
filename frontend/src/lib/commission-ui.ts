// NOMICON: reine Helfer für Provisionsmodell-Oberfläche (Fortschrittsbalken, Stufen im Editor).
// Plain-Modul ohne "use client", aus Server- und Client-Komponenten nutzbar.
import { formatEuroAmount, formatNumber, toNumber } from "./format";

/** Breite des Fortschrittsbalkens in Prozent (0–100); ungültige Werte werden zu 0. */
export function barWidth(percent: string | number | null | undefined): number {
  const value = typeof percent === "number" ? percent : Number(percent);
  if (!Number.isFinite(value)) return 0;
  return Math.min(100, Math.max(0, value));
}

const UMLAUTS: Record<string, string> = { ä: "ae", ö: "oe", ü: "ue", ß: "ss" };

/** Schlüssel für eine neue Stufe aus ihrem Namen ("Senior Berater" -> "senior_berater"), eindeutig
 * gegenüber `existing` (Muster des Servers: a-z, 0-9, Unterstrich, höchstens 40 Zeichen). */
export function rankKeyFromLabel(label: string, existing: string[]): string {
  const base =
    label
      .toLowerCase()
      .replace(/[äöüß]/g, (char) => UMLAUTS[char] ?? char)
      .replace(/[^a-z0-9]+/g, "_")
      .replace(/^_+|_+$/g, "")
      .slice(0, 34) || "stufe";
  if (!existing.includes(base)) return base;
  let counter = 2;
  while (existing.includes(`${base}_${counter}`)) counter += 1;
  return `${base}_${counter}`;
}

/** Verschiebt das Element an `index` um `delta` Plätze (-1 nach oben, +1 nach unten). */
export function moveItem<T>(items: T[], index: number, delta: number): T[] {
  const target = index + delta;
  if (index < 0 || index >= items.length || target < 0 || target >= items.length) return items;
  const copy = [...items];
  const [item] = copy.splice(index, 1);
  copy.splice(target, 0, item);
  return copy;
}

// --- Zeitstrahl "Meine Provision" ---------------------------------------------------------------


export interface TimelineMonthLike {
  year: number;
  month: number;
  quarter: number;
  month_in_quarter: number;
  revenue: string;
  commission: string;
  is_current: boolean;
  is_provisional: boolean;
}

export interface TimelineChartDatum {
  key: string;
  label: string;
  revenue: number;
  commission: number;
  isCurrent: boolean;
  /** Erster Monat eines Quartals (bis auf den ersten angezeigten): hier steht die Quartalsgrenze. */
  quarterStart: boolean;
}

const MONTH_SHORT = ["Jan", "Feb", "Mär", "Apr", "Mai", "Jun", "Jul", "Aug", "Sep", "Okt", "Nov", "Dez"];
const MONTH_LONG = ["Januar", "Februar", "März", "April", "Mai", "Juni", "Juli", "August", "September", "Oktober", "November", "Dezember"];

/** "Okt 26" für die Achse, "Oktober 2026" für die Tabelle. */
export function monthLabel(year: number, month: number, long = false): string {
  return long ? `${MONTH_LONG[month - 1]} ${year}` : `${MONTH_SHORT[month - 1]} ${String(year).slice(-2)}`;
}

/** Daten für das Diagramm: Umsatz und Provision je Monat als Zahlen, mit Quartalsgrenzen. */
export function timelineChartData(months: TimelineMonthLike[]): TimelineChartDatum[] {
  return months.map((m, index) => ({
    key: `${m.year}-${m.month}`,
    label: monthLabel(m.year, m.month),
    revenue: toNumber(m.revenue) ?? 0,
    commission: toNumber(m.commission) ?? 0,
    isCurrent: m.is_current,
    quarterStart: m.month_in_quarter === 1 && index > 0,
  }));
}

/** Beschriftungen der Monate, vor denen ein neues Quartal beginnt (für die Linien im Diagramm). */
export function quarterBoundaryLabels(data: TimelineChartDatum[]): string[] {
  return data.filter((d) => d.quarterStart).map((d) => d.label);
}

export interface ProgressLike {
  is_top_rank: boolean;
  current_rank_label: string;
  next_rank_label?: string | null;
  quarter_revenue: string;
  hurdle?: string | null;
  remaining?: string | null;
  days_to_quarter_end: number;
  next_band_remaining?: string | null;
  next_band_rate?: string | null;
}

/** "Senior Consultant → Manager: 68.000 € von 96.000 € Quartalsumsatz, noch 28.000 €". */
export function nextRoleText(progress: ProgressLike): string {
  if (progress.is_top_rank || !progress.next_rank_label || !progress.hurdle) {
    if (!progress.next_band_remaining) return `${progress.current_rank_label}: höchste Stufe und höchster Provisionssatz erreicht`;
    const rate = progress.next_band_rate ? ` (dann ${formatNumber(progress.next_band_rate)} %)` : "";
    return `${progress.current_rank_label} (höchste Stufe): noch ${formatEuroAmount(progress.next_band_remaining, { digits: 0 })} bis zur nächsten Provisionsstufe${rate}`;
  }
  const remaining = toNumber(progress.remaining) ?? 0;
  const tail = remaining > 0 ? `noch ${formatEuroAmount(progress.remaining, { digits: 0 })}` : "Schwelle erreicht";
  return `${progress.current_rank_label} → ${progress.next_rank_label}: ${formatEuroAmount(progress.quarter_revenue, { digits: 0 })} von ${formatEuroAmount(progress.hurdle, { digits: 0 })} Quartalsumsatz, ${tail}`;
}

/** "noch 41 Tage bis Quartalsende" / "letzter Tag des Quartals". */
export function daysToQuarterEndText(days: number): string {
  if (days <= 0) return "letzter Tag des Quartals";
  return `noch ${days} ${days === 1 ? "Tag" : "Tage"} bis Quartalsende`;
}

/** Hinweis unter dem Diagramm: Monatswert und vorläufiger laufender Monat. */
export function provisionalNote(hasRank: boolean): string {
  const base = "Der laufende Monat ist vorläufig: gerechnet bis heute, Abrechnung zum Quartalsende.";
  return hasRank
    ? `${base} Die Monatswerte verteilen die Quartalsprovision auf die Monate (Stufen laufen mit); der Bonus zählt in dem Monat, in dem der Deal bezahlt wird.`
    : `${base} Ohne Rang wird kein Provisionswert berechnet.`;
}
