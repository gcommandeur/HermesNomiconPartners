"use client";

import { useEffect, useState } from "react";
import useSWR from "swr";
import { useDebouncedValue } from "@/lib/use-debounced-value";
import type { DataResult, PageQuery, Paginated } from "./types";

const DEBOUNCE_MS = 300;

/** Serverseitige Suche + Pagination fuer grosse Listen (Kandidaten, Kanzleien,
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
 * die ganze Tabelle). */
export function useServerSearchList<T>(
  cacheKeyPrefix: string,
  fetcher: (query: PageQuery) => Promise<DataResult<Paginated<T>>>,
  options: { status?: string; ownerUserId?: string; pageSize?: number } = {},
) {
  const pageSize = options.pageSize ?? 100;
  const [search, setSearch] = useState("");
  const [page, setPage] = useState(0);
  const debouncedSearch = useDebouncedValue(search.trim(), DEBOUNCE_MS);

  // Zurueck auf Seite 1, wenn sich Suche oder Filter aendern - sonst bliebe
  // man auf einer Seite haengen, die es im neuen (kuerzeren) Ergebnis
  // vielleicht gar nicht mehr gibt.
  useEffect(() => {
    setPage(0);
  }, [debouncedSearch, options.status, options.ownerUserId]);

  const offset = page * pageSize;
  const swrKey = `${cacheKeyPrefix}?search=${debouncedSearch}&status=${options.status ?? ""}&owner_user_id=${options.ownerUserId ?? ""}&limit=${pageSize}&offset=${offset}`;

  const { data, error, isLoading, mutate } = useSWR<DataResult<Paginated<T>>>(
    swrKey,
    () =>
      fetcher({
        search: debouncedSearch || undefined,
        status: options.status,
        ownerUserId: options.ownerUserId,
        limit: pageSize,
        offset,
      }),
    { revalidateOnFocus: false, keepPreviousData: true },
  );

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
    error,
    source: data?.source,
    demoError: data?.error,
    retry: () => void mutate(),
  };
}
