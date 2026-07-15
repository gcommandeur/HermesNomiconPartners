import { useEffect, useMemo, useState } from "react";

/** Begrenzt, wie viele Zeilen einer bereits geladenen/gefilterten Liste
 * tatsächlich ins DOM gerendert werden - bei Listen mit hunderten bis
 * tausenden Einträgen (Kandidaten, Kanzleien, Geo-Mapping) fror der Tab beim
 * ersten Laden 10-20s ein, weil jede einzelne Zeile als eigenes <tr> mit
 * mehreren Kind-Elementen gerendert wurde (siehe Nutzer-Feedback zum
 * Generaltest vor Go-Live). Rein clientseitig (kein neuer Netzwerk-Request
 * pro Seite) - die Daten sind ja schon vollständig geladen/gefiltert/
 * sortiert, es wird nur die DOM-Knotenzahl pro Render begrenzt. Bewusst KEINE
 * Aenderung an der gemeinsamen DataTable-Komponente oder den anderen
 * Verbraucher-Seiten (Kontakte/Prozesse/Vakanzen) - dort ist die Zeilenzahl
 * unproblematisch klein, ein groesserer Umbau der Tabellen-Architektur war
 * nicht Teil dieses Auftrags. */
const DEFAULT_PAGE_SIZE = 100;

export function usePagination<T>(items: T[], pageSize: number = DEFAULT_PAGE_SIZE) {
  const [page, setPage] = useState(0);
  const pageCount = Math.max(1, Math.ceil(items.length / pageSize));

  // Zurueck auf Seite 1, wenn sich die (gefilterte) Liste aendert - sonst
  // bliebe man nach einer Suche/einem Sortierwechsel auf einer Seite haengen,
  // die es in der neuen, kuerzeren Liste gar nicht mehr gibt.
  useEffect(() => {
    setPage(0);
  }, [items]);

  const safePage = Math.min(page, pageCount - 1);
  const pageItems = useMemo(
    () => items.slice(safePage * pageSize, safePage * pageSize + pageSize),
    [items, safePage, pageSize],
  );

  return { pageItems, page: safePage, pageCount, pageSize, setPage };
}
