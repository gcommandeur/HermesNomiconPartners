// NOMICON: reine Helfer für Provisionsmodell-Oberfläche (Fortschrittsbalken, Stufen im Editor).
// Plain-Modul ohne "use client", aus Server- und Client-Komponenten nutzbar.

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
