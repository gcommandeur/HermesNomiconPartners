"use client";

import { useEffect, useRef, useState } from "react";
import useSWR from "swr";
import { useDebouncedValue } from "@/lib/use-debounced-value";
import type { Abschlussart, DataResult, PageQuery, Paginated, Rolle } from "./types";

const DEBOUNCE_MS = 300;

/** Serverseitige Suche + Pagination fuer grosse Listen (Kandidaten, Kunden,
 * Kontakte) - loest fetchAllPages() ab, das bislang IMMER den kompletten
 * Bestand lud und danach clientseitig filterte/paginierte. Das brach
 * stillschweigend ab 25.000 Datensaetzen (PAGE_SIZE * MAX_PAGES) und waere
 * bei der Zielgroesse von ~30.000 Kandidaten bereits als Einzelantwort
 * mehrere MB gross gewesen.
 *
 * Ein Tastendruck im Suchfeld loest NICHT sofort einen Request aus (das
 * waere ein Request pro Zeichen) - der Suchbegriff wird um 300ms entprellt,
 * bevor er in den SWR-Cache-Key (und damit den tatsaechlichen API-Call)
 * einfliesst. `keepPreviousData` haelt die zuletzt geladene Seite sichtbar,
 * waehrend im Hintergrund neu geladen wird, statt zwischendurch ein Skeleton
 * zu zeigen (wichtig beim Tippen: sonst flackert bei jeder Debounce-Runde
 * die ganze Tabelle).
 *
 * Wichtig fuer Aufrufer: SWRs `isLoading` wird bei JEDEM Cache-Key-Wechsel
 * kurz wahr (auch mit `keepPreviousData`, das nur `data` ueberbrueckt, nicht
 * `isLoading` - offizielles SWR-Verhalten) - ein Aufrufer, der bei jedem
 * `isLoading` die komplette Liste durch ein Skeleton ersetzt, flackert daher
 * bei JEDER Sucheingabe, obwohl `keepPreviousData` genau das verhindern
 * sollte. Fuer den initialen Ladezustand `hasLoadedOnce` verwenden (wird erst
 * nach der allerersten erfolgreichen Antwort wahr und bleibt danach stabil),
 * fuer eine dezente Lade-Anzeige waehrend Folgesuchen `isValidating`. */
export function useServerSearchList<T>(
  cacheKeyPrefix: string,
  fetcher: (query: PageQuery) => Promise<DataResult<Paginated<T>>>,
  options: {
    status?: string;
    rollen?: Rolle[];
    abschluesse?: Abschlussart[];
    plzOrt?: string;
    radiusKm?: number;
    rollenUnbestaetigt?: boolean;
    engagement?: "free_direct" | "free_staffing" | "engaged"; // NOMICON
    staffing?: "workers" | "bench" | "critical" | "applicants"; // NOMICON
    ownerUserId?: string;
    pageSize?: number;
    sortBy?: string;
    sortDir?: "asc" | "desc";
    // Erlaubt Aufrufern, Suche/Seite beim ersten Rendern aus der URL statt
    // von "" bzw. 0 zu starten (siehe candidates-table.tsx) - nur fuer den
    // initialen useState-Wert relevant, spaetere Aenderungen dieser Props
    // haben keine Wirkung.
    initialSearch?: string;
    initialPage?: number;
  } = {},
) {
  const pageSize = options.pageSize ?? 100;
  const [search, setSearch] = useState(options.initialSearch ?? "");
  const [page, setPage] = useState(options.initialPage ?? 0);
  // Verhindert, dass der Seite-1-Reset-Effekt unten den obigen initialPage-
  // Wert gleich beim ersten Render wieder auf 0 zuruecksetzt - Effects laufen
  // auch nach dem allerersten Render, unabhaengig davon, ob sich Dependencies
  // "geaendert" haben (es gibt ja noch keinen Vorwert zum Vergleichen).
  const isFirstRender = useRef(true);
  const debouncedSearch = useDebouncedValue(search.trim(), DEBOUNCE_MS);
  // plzOrt ist wie search ein Freitextfeld - ohne eigenes Debounce wuerde
  // jeder Tastendruck (sobald ein Radius gewaehlt ist) einen eigenen Request
  // ausloesen.
  const debouncedPlzOrt = useDebouncedValue((options.plzOrt ?? "").trim(), DEBOUNCE_MS);
  // Stabiler String fuer Dependency-Array/Cache-Key statt der rollen-Array-
  // Referenz selbst, die sich bei jedem Render neu bildet, wenn der Aufrufer
  // sie inline erzeugt (z.B. `rollen: [...selected]`).
  const rollenKey = (options.rollen ?? []).join(",");
  const abschluesseKey = (options.abschluesse ?? []).join(",");
  // Nur ein aktiver Umkreis-Filter, wenn BEIDE Werte gesetzt sind (siehe
  // services/candidates.py::list_filtered) - ein Radius allein ohne Zentrum
  // (oder umgekehrt) darf keinen Request/Cache-Key-Wechsel ausloesen.
  const radiusActive = Boolean(debouncedPlzOrt && options.radiusKm);

  // Zurueck auf Seite 1, wenn sich Suche, Filter oder Sortierung aendern -
  // sonst bliebe man auf einer Seite haengen, die es im neuen (kuerzeren/
  // anders sortierten) Ergebnis vielleicht gar nicht mehr an dieser Stelle gibt.
  useEffect(() => {
    if (isFirstRender.current) {
      isFirstRender.current = false;
      return;
    }
    setPage(0);
  }, [
    debouncedSearch,
    options.status,
    rollenKey,
    abschluesseKey,
    debouncedPlzOrt,
    options.radiusKm,
    options.rollenUnbestaetigt,
    options.engagement, // NOMICON
    options.staffing, // NOMICON
    options.ownerUserId,
    options.sortBy,
    options.sortDir,
  ]);

  const offset = page * pageSize;
  const swrKey = `${cacheKeyPrefix}?search=${debouncedSearch}&status=${options.status ?? ""}&rollen=${rollenKey}&abschluesse=${abschluesseKey}&plz_ort=${radiusActive ? debouncedPlzOrt : ""}&radius_km=${radiusActive ? options.radiusKm : ""}&rollen_unbestaetigt=${options.rollenUnbestaetigt ?? ""}&engagement=${options.engagement ?? ""}&staffing=${options.staffing ?? ""}&owner_user_id=${options.ownerUserId ?? ""}&sort_by=${options.sortBy ?? ""}&sort_dir=${options.sortDir ?? ""}&limit=${pageSize}&offset=${offset}`;

  const { data, error, isLoading, isValidating, mutate } = useSWR<DataResult<Paginated<T>>>(
    swrKey,
    () =>
      fetcher({
        search: debouncedSearch || undefined,
        status: options.status,
        rollen: options.rollen,
        abschluesse: options.abschluesse,
        plzOrt: radiusActive ? debouncedPlzOrt : undefined,
        radiusKm: radiusActive ? options.radiusKm : undefined,
        rollenUnbestaetigt: options.rollenUnbestaetigt,
        engagement: options.engagement, // NOMICON
        staffing: options.staffing, // NOMICON
        ownerUserId: options.ownerUserId,
        sortBy: options.sortBy,
        sortDir: options.sortDir,
        limit: pageSize,
        offset,
      }),
    { revalidateOnFocus: false, keepPreviousData: true },
  );

  // Wird einmalig wahr, sobald die allererste Antwort da ist, und bleibt
  // danach stabil wahr - siehe Doc-Kommentar oben, warum das (statt SWRs
  // eigenem `isLoading`) der richtige Wert fuer "initialer Skeleton ja/nein"
  // ist.
  const [hasLoadedOnce, setHasLoadedOnce] = useState(false);
  useEffect(() => {
    if (data !== undefined) setHasLoadedOnce(true);
  }, [data]);

  const totalCount = data?.data.total_count ?? 0;
  const pageCount = Math.max(1, Math.ceil(totalCount / pageSize));
  const safePage = Math.min(page, pageCount - 1);

  return {
    search,
    setSearch,
    page: safePage,
    setPage,
    pageCount,
    pageSize,
    items: data?.data.items ?? [],
    totalCount,
    isLoading,
    hasLoadedOnce,
    isValidating,
    error,
    source: data?.source,
    demoError: data?.error,
    retry: () => void mutate(),
  };
}
