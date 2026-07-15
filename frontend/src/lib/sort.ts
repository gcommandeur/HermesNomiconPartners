export type SortDir = "asc" | "desc";

/** Generic comparator for table sorting - handles strings (locale-aware,
 * numeric-aware for things like candidate numbers "192" vs "4052"), numbers,
 * and null/undefined (always sorts to the end regardless of direction, so
 * "keine Angabe" rows don't jump around confusingly when toggling asc/desc). */
export function compareValues(a: unknown, b: unknown, dir: SortDir): number {
  const aEmpty = a === null || a === undefined || a === "";
  const bEmpty = b === null || b === undefined || b === "";
  if (aEmpty && bEmpty) return 0;
  if (aEmpty) return 1;
  if (bEmpty) return -1;

  let result: number;
  if (typeof a === "number" && typeof b === "number") {
    result = a - b;
  } else {
    result = String(a).localeCompare(String(b), "de", { numeric: true, sensitivity: "base" });
  }
  return dir === "asc" ? result : -result;
}
