// NOMICON: zentrale Zahlen-Formatierung in deutscher Schreibweise (Komma als Dezimaltrenner, Punkt als
// Tausendertrenner). Eingaben dürfen Zahlen oder Texte sein ("40.00" vom Server). Leere oder ungültige
// Werte werden zu "–". Plain-Modul, aus Server- und Client-Komponenten nutzbar.

export type NumberLike = number | string | null | undefined;

export function toNumber(value: NumberLike): number | null {
  if (value === null || value === undefined || value === "") return null;
  const number = typeof value === "number" ? value : Number(value);
  return Number.isFinite(number) ? number : null;
}

/** 1234.5 -> "1.234,5"; Standard: bis zu 2 Nachkommastellen, ohne überflüssige Nullen. */
export function formatNumber(value: NumberLike, options: { min?: number; max?: number } = {}): string {
  const number = toNumber(value);
  if (number === null) return "–";
  const min = options.min ?? 0;
  const max = Math.max(options.max ?? 2, min);
  return number.toLocaleString("de-DE", { minimumFractionDigits: min, maximumFractionDigits: max });
}

/** "40.00" -> "40 Std."; mit `fixed` immer zwei Nachkommastellen (Stundenzettel: "7,50"). */
export function formatHours(value: NumberLike, options: { fixed?: boolean; unit?: string } = {}): string {
  const number = toNumber(value);
  if (number === null) return "–";
  const text = formatNumber(number, options.fixed ? { min: 2, max: 2 } : {});
  return options.unit === "" ? text : `${text} ${options.unit ?? "Std."}`;
}

/** "30.00" -> "30 %", 27.5 -> "27,5 %". */
export function formatPercent(value: NumberLike, options: { max?: number } = {}): string {
  const number = toNumber(value);
  if (number === null) return "–";
  return `${formatNumber(number, { max: options.max ?? 2 })} %`;
}

/** Betrag in Euro mit zwei Nachkommastellen: "14.5" -> "14,50 €". */
export function formatEuroAmount(value: NumberLike, options: { digits?: number } = {}): string {
  const number = toNumber(value);
  if (number === null) return "–";
  const digits = options.digits ?? 2;
  return new Intl.NumberFormat("de-DE", {
    style: "currency",
    currency: "EUR",
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  }).format(number);
}
