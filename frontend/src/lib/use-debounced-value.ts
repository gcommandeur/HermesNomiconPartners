import { useEffect, useState } from "react";

/** Verzoegert einen sich schnell aendernden Wert (z.B. Tastatureingabe) um
 * delayMs, bevor er z.B. in einen API-Call oder SWR-Cache-Key einfliesst -
 * verhindert einen Netzwerk-Request pro Tastendruck. Geteilt zwischen
 * use-server-search.ts (Listen-Suche) und SearchSelect (Auswahlfelder). */
export function useDebouncedValue<T>(value: T, delayMs: number): T {
  const [debounced, setDebounced] = useState(value);
  useEffect(() => {
    const timer = setTimeout(() => setDebounced(value), delayMs);
    return () => clearTimeout(timer);
  }, [value, delayMs]);
  return debounced;
}
