"use client";

import { useMemo, useState } from "react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { Ghost, History, X } from "lucide-react";
import { FilterBar } from "@/components/crm/filter-bar";
import { DataTable } from "@/components/crm/data-table";
import { StatusPill } from "@/components/crm/status-pill";
import { ExportActions } from "@/components/crm/export-actions";
import { DemoNotice } from "@/components/crm/demo-notice";
import { ErrorState } from "@/components/crm/error-state";
import { ErrorBanner } from "@/components/crm/error-banner";
import { ListSkeleton } from "@/components/crm/list-skeleton";
import { PaginationControls } from "@/components/crm/pagination-controls";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { compareValues, type SortDir } from "@/lib/sort";
import { formatDate } from "@/lib/utils";
import { usePagination } from "@/lib/use-pagination";
import { apiPost } from "@/lib/api/client";
import { useCurrentUser, useReactivationCandidatesCache } from "@/lib/api/hooks";
import { useServerSearchList } from "@/lib/api/use-server-search";
import { getCandidatesPage } from "@/lib/api/queries";
import type { Candidate } from "@/lib/api/types";

interface NlSearchResponse {
  items: Candidate[];
  total_count: number;
  filters_used: Record<string, unknown>;
  hint: string | null;
}

const STATUS_OPTIONS = [
  { value: "active", label: "Aktiv" },
  { value: "passive", label: "Passiv" },
  { value: "placed", label: "Platziert" },
  { value: "blocked", label: "Gesperrt" },
  { value: "archived", label: "Archiviert" },
];

const SORT_ACCESSORS: Record<string, (candidate: Candidate) => unknown> = {
  candidate_number: (c) => (c.candidate_number ? Number(c.candidate_number) || c.candidate_number : null),
  name: (c) => `${c.last_name} ${c.first_name}`,
  job_title: (c) => c.job_title,
  city: (c) => c.city ?? c.postal_code,
  salary_expectation: (c) => c.salary_expectation,
  status: (c) => c.status,
};

export function CandidatesTable() {
  const searchParams = useSearchParams();
  // Erlaubt einen direkten Link auf den Reaktivierungs-Filter (z.B. vom
  // Redirect der entfernten /reaktivierung-Route, siehe Phase L.2).
  const [reactivationOnly, setReactivationOnly] = useState(
    () => searchParams.get("reaktivierung") === "1",
  );
  const [status, setStatus] = useState("");
  // "Meine Kandidaten" - reiner Komfort-Filter nach owner_user_id, KEINE
  // Sichtbarkeitsgrenze (Default "Alle" bleibt unveraendert). Siehe
  // Backend models/candidate.py::owner_user_id fuer die Begruendung.
  const [mineOnly, setMineOnly] = useState(false);
  const { data: currentUserData } = useCurrentUser();
  const currentUserId = currentUserData?.data.id;
  const [sortKey, setSortKey] = useState<string | null>("candidate_number");
  const [sortDir, setSortDir] = useState<SortDir>("desc");

  function handleSort(key: string) {
    if (sortKey === key) {
      setSortDir((current) => (current === "asc" ? "desc" : "asc"));
    } else {
      setSortKey(key);
      setSortDir("asc");
    }
  }

  // Serverseitige Suche + Pagination + Sortierung (siehe
  // lib/api/use-server-search.ts) - laedt nur die aktuell sichtbare Seite +
  // Suchtreffer statt (wie vorher via fetchAllPages) immer den kompletten
  // Kandidatenbestand. Sortierung laeuft ueber ORDER BY im Backend (siehe
  // repositories/candidates.py::_order_by_clauses) und damit ueber den
  // GESAMTEN Bestand - vorher sortierte compareValues() nur die aktuell
  // geladene Seite, bei 30k+ Kandidaten also nur innerhalb von ~100
  // sichtbaren Zeilen statt ueber den gesamten Bestand. Die
  // Reaktivierungsliste bleibt bewusst ein separater, vollstaendig
  // geladener kleiner Datensatz (eigener, bereits bestehender Endpoint ohne
  // Skalierungsproblem) - beim Umschalten auf "Erneut kontaktieren" wird sie
  // clientseitig gefiltert/sortiert wie bisher.
  const {
    search,
    setSearch: setServerSearch,
    page,
    setPage,
    pageCount,
    items: serverCandidates,
    totalCount,
    hasLoadedOnce,
    isValidating,
    error,
    source,
    demoError,
    retry: retryCandidates,
  } = useServerSearchList<Candidate>("/candidates", getCandidatesPage, {
    status,
    ownerUserId: mineOnly ? currentUserId : undefined,
    sortBy: sortKey ?? undefined,
    sortDir,
  });

  const {
    data: reactivationData,
    isLoading: reactivationLoading,
    error: reactivationError,
    mutate: retryReactivation,
  } = useReactivationCandidatesCache(reactivationOnly);
  const reactivationCandidates = useMemo(
    () => reactivationData?.data ?? [],
    [reactivationData],
  );
  const [aiResults, setAiResults] = useState<Candidate[] | null>(null);
  const [aiHint, setAiHint] = useState<string | null>(null);
  const [aiSearching, setAiSearching] = useState(false);
  const [aiError, setAiError] = useState<string | null>(null);

  function handleSearchChange(value: string) {
    setServerSearch(value);
    // Any manual edit after an AI search leaves KI-Suche results stale -
    // fall back to the fast local filter until the user re-triggers KI-Suche.
    setAiResults(null);
    setAiHint(null);
  }

  async function handleAiSearch() {
    if (!search.trim()) return;
    setAiSearching(true);
    setAiError(null);
    try {
      const result = await apiPost<NlSearchResponse>("/candidates/nl-search", { query: search });
      setAiResults(result.items);
      setAiHint(result.hint);
    } catch (exception) {
      setAiError(exception instanceof Error ? exception.message : "KI-Suche fehlgeschlagen.");
    } finally {
      setAiSearching(false);
    }
  }

  // Reaktivierungsliste ist ein kleiner, vollstaendig geladener Datensatz -
  // Suche/Status/Sortierung bleiben dort clientseitig ueber den gesamten
  // (kleinen) Bestand, wie vor dieser Umstellung.
  const reactivationFiltered = useMemo(() => {
    const base = reactivationCandidates.filter((candidate) => {
      if (status && candidate.status !== status) return false;
      if (mineOnly && candidate.owner_user_id !== currentUserId) return false;
      const term = search.trim().toLowerCase();
      if (!term) return true;
      const haystack = [
        candidate.first_name, candidate.last_name, candidate.job_title,
        candidate.qualification, candidate.city, candidate.postal_code,
        candidate.candidate_number,
      ].filter(Boolean).join(" ").toLowerCase();
      return haystack.includes(term);
    });
    if (!sortKey || !SORT_ACCESSORS[sortKey]) return base;
    const accessor = SORT_ACCESSORS[sortKey];
    return [...base].sort((a, b) => compareValues(accessor(a), accessor(b), sortDir));
  }, [reactivationCandidates, search, status, mineOnly, currentUserId, sortKey, sortDir]);

  const { pageItems: reactivationPageItems, page: reactivationPage, pageCount: reactivationPageCount, setPage: setReactivationPage } = usePagination(reactivationFiltered);

  // serverCandidates kommt bereits serverseitig sortiert zurueck (sortBy/
  // sortDir werden an useServerSearchList durchgereicht). Nur die
  // KI-Suche-Treffer (aiResults) sind ein fixes, nicht paginiertes Array
  // eines separaten Endpoints und werden weiterhin clientseitig sortiert -
  // das ist unproblematisch, da KI-Suche-Ergebnismengen klein sind.
  const sortedServerCandidates = useMemo(() => {
    if (!aiResults) return serverCandidates;
    if (!sortKey || !SORT_ACCESSORS[sortKey]) return aiResults;
    const accessor = SORT_ACCESSORS[sortKey];
    return [...aiResults].sort((a, b) => compareValues(accessor(a), accessor(b), sortDir));
  }, [serverCandidates, aiResults, sortKey, sortDir]);

  const displayedCandidates = reactivationOnly ? reactivationPageItems : sortedServerCandidates;
  const displayedTotal = reactivationOnly ? reactivationFiltered.length : (aiResults?.length ?? totalCount);
  const displayedPage = reactivationOnly ? reactivationPage : page;
  const displayedPageCount = reactivationOnly ? reactivationPageCount : (aiResults ? 1 : pageCount);
  const displayedSetPage = reactivationOnly ? setReactivationPage : setPage;

  const exportRows = useMemo(() => displayedCandidates.map((candidate) => ({
    Name: `${candidate.first_name} ${candidate.last_name}`,
    Rolle: candidate.job_title,
    Region: candidate.city ?? candidate.postal_code,
    Gehalt: candidate.salary_expectation,
    Status: candidate.status,
    Kurzprofil: candidate.short_profile ? "Ja" : "Nein",
  })), [displayedCandidates]);

  if ((!reactivationOnly && error) || (reactivationOnly && reactivationError)) {
    return <ErrorState onRetry={() => { void retryCandidates(); void retryReactivation(); }} />;
  }

  // Skeleton NUR beim allerersten Laden (hasLoadedOnce), nicht bei jeder
  // Sucheingabe: SWRs `isLoading` wird bei jedem Cache-Key-Wechsel kurz wahr
  // (auch mit keepPreviousData, siehe use-server-search.ts) - wer darauf die
  // ganze Tabelle+Suchfeld durch ein Skeleton ersetzt, verliert bei jeder
  // Debounce-Runde den Fokus im Suchfeld und die Seite "flackert" sichtbar.
  // Waehrend einer Folgesuche bleiben Tabelle+Eingabe montiert (siehe
  // isValidating-Anzeige unten in der FilterBar-Zeile).
  if ((!reactivationOnly && !hasLoadedOnce) || (reactivationOnly && reactivationLoading)) {
    return <ListSkeleton />;
  }

  return (
    <>
      <div className="mb-4 flex flex-wrap items-center justify-between gap-2">
        <Button
          size="sm"
          variant={reactivationOnly ? "dark" : "outline"}
          onClick={() => setReactivationOnly((current) => !current)}
        >
          <History size={14} />Erneut kontaktieren
        </Button>
        <ExportActions filename="kandidaten" rows={exportRows} />
      </div>
      {reactivationOnly && (
        <div className="mb-3">
          <Badge tone="blue" className="gap-1.5">
            Wiedervorlage-Filter aktiv
            <button type="button" onClick={() => setReactivationOnly(false)} title="Filter entfernen" className="hover:text-white">
              <X size={12} />
            </button>
          </Badge>
        </div>
      )}
      <DemoNotice source={reactivationOnly ? "api" : (source ?? "api")} error={reactivationOnly ? undefined : demoError} />
      <FilterBar
        placeholder='Nach Name/Rolle/Region suchen, oder z.B. "aktive Steuerberater in Köln mit Umsatzsteuer-Erfahrung" für KI-Suche'
        value={search}
        onChange={handleSearchChange}
        statusOptions={STATUS_OPTIONS}
        statusValue={status}
        onStatusChange={setStatus}
        onSubmit={handleAiSearch}
        aiSearch={{ loading: aiSearching, onClick: handleAiSearch }}
        ownerFilter={{ mineOnly, onChange: setMineOnly }}
        loading={!reactivationOnly && isValidating}
      />
      <ErrorBanner message={aiError} className="mb-3" />
      {aiResults && (
        <div className="mb-3 flex items-center justify-between rounded-lg border border-[#1F5FA8]/30 bg-[#1F5FA8]/10 p-3 text-xs text-[#CBD5E1]">
          <span>KI-Suche aktiv: {aiResults.length} Treffer für &quot;{search}&quot;</span>
          <button
            className="text-[#94A3B8] underline hover:text-white"
            onClick={() => { setAiResults(null); setAiHint(null); }}
          >
            Zurück zur normalen Filterung
          </button>
        </div>
      )}
      {aiHint && (
        <div className="mb-3 rounded-lg border border-[#F0B429]/25 bg-[#F0B429]/5 p-3 text-xs text-[#F0B429]">{aiHint}</div>
      )}
      <DataTable
        headers={[
          { label: "Nr.", key: "candidate_number" },
          { label: "Name", key: "name" },
          { label: "Rolle / Qualifikation", key: "job_title" },
          { label: "Region", key: "city" },
          { label: "Gehalt", key: "salary_expectation" },
          "Verfügbarkeit",
          "Unterlagen",
          { label: "Status", key: "status" },
          "Nächster Schritt",
        ]}
        sortKey={sortKey}
        sortDir={sortDir}
        onSort={handleSort}
      >
        {displayedCandidates.map((candidate) => (
          <tr key={candidate.id} className="hover:bg-[#203A5A]/35">
            <td className="px-4 py-3.5 text-xs text-[#94A3B8]">{candidate.candidate_number ?? "—"}</td>
            <td className="px-4 py-3.5"><Link href={`/kandidaten/${candidate.id}`} className="font-semibold text-[#D8DADF] hover:text-white hover:underline">{candidate.first_name} {candidate.last_name}</Link>{candidate.has_ghosting_history && <Ghost size={12} className="ml-1.5 inline text-[#e4aeb4]" aria-label="Ghosting-Historie" />}<p className="mt-1 text-[11px] text-[#94A3B8]">Kontakt {formatDate(candidate.last_contact_at ?? candidate.last_contact ?? candidate.updated_at)}</p></td>
            <td className="px-4 py-3.5"><p>{candidate.job_title ?? "—"}</p><p className="mt-1 text-[11px] text-[#94A3B8]">{candidate.qualification ?? "Qualifikation offen"}</p></td>
            <td className="px-4 py-3.5 text-[#CBD5E1]">{candidate.city ?? candidate.postal_code ?? "—"}</td>
            <td className="px-4 py-3.5">{candidate.salary_expectation ?? "—"}</td>
            <td className="px-4 py-3.5"><p>{candidate.notice_period ?? "—"}</p><p className="mt-1 text-[11px] text-[#94A3B8]">{candidate.available_from ? formatDate(candidate.available_from) : "nach Absprache"}</p></td>
            <td className="px-4 py-3.5"><div className="flex gap-1.5"><span className={`size-2 rounded-full ${candidate.cv_available ? "bg-[#A7ADB7]" : "bg-[#334155]"}`} title="CV" /><span className={`size-2 rounded-full ${candidate.short_profile ? "bg-[#1F5FA8]" : "bg-[#334155]"}`} title="Kurzprofil" /></div></td>
            <td className="px-4 py-3.5"><StatusPill status={candidate.status} /></td>
            <td className="px-4 py-3.5 text-[#CBD5E1]">{candidate.next_step ?? "Kontakt aufnehmen"}</td>
          </tr>
        ))}
      </DataTable>
      <PaginationControls page={displayedPage} pageCount={displayedPageCount} onChange={displayedSetPage} />
      <p className="mt-3 text-xs text-[#8a9095]">{displayedCandidates.length} von {displayedTotal} Kandidaten</p>
    </>
  );
}
