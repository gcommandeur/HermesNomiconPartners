"use client";

import { useEffect, useMemo, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { ChevronDown, Ghost, History, ShieldAlert, X } from "lucide-react";
import { FilterBar } from "@/components/crm/filter-bar";
import { DataTable } from "@/components/crm/data-table";
import { StatusPill } from "@/components/crm/status-pill";
import { CandidateQuickViewDrawer } from "@/components/crm/candidate-quickview-drawer";
import { ExportActions } from "@/components/crm/export-actions";
import { DemoNotice } from "@/components/crm/demo-notice";
import { ErrorState } from "@/components/crm/error-state";
import { ErrorBanner } from "@/components/crm/error-banner";
import { ListSkeleton } from "@/components/crm/list-skeleton";
import { PaginationControls } from "@/components/crm/pagination-controls";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { compareValues, type SortDir } from "@/lib/sort";
import { ABSCHLUSSART_OPTIONS, abschlussartLabel, formatDate, ROLLE_OPTIONS, rolleLabel, searchFieldLabel } from "@/lib/utils";
import { usePagination } from "@/lib/use-pagination";
import { useDebouncedValue } from "@/lib/use-debounced-value";
import { apiPost } from "@/lib/api/client";
import { useCurrentUser, useReactivationCandidatesCache } from "@/lib/api/hooks";
import { useServerSearchList } from "@/lib/api/use-server-search";
import { getCandidatesPage } from "@/lib/api/queries";
import type { Abschlussart, Candidate, Rolle } from "@/lib/api/types";
import { EngagementBadge } from "@/components/crm/engagement-badge"; // NOMICON
import { ENGAGEMENT_FILTER_LABELS, type EngagementFilter } from "@/lib/api/engagement"; // NOMICON
import { useEngagementSummaries } from "@/lib/api/engagement-hooks"; // NOMICON
import { useStaffingCandidateSummaries } from "@/lib/api/staffing-hooks"; // NOMICON
import { STAFFING_FILTER_LABELS, type StaffingListFilter } from "@/lib/api/staffing"; // NOMICON
import { useMyViews } from "@/lib/api/views-hooks"; // NOMICON
import { StaffingCandidateCell, staffingCandidateText } from "@/components/crm/staffing-candidate-cell"; // NOMICON
import { canSeeStaffing } from "@/lib/staffing-candidate"; // NOMICON

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

/** Mehrfachauswahl aus den 10 Rollen-Kategorien + Sonstige - eigenstaendig
 * statt Teil von FilterBar (dessen statusOptions/-Value sind Einzelauswahl
 * und werden auch von clients-table.tsx/contacts genutzt, hier nicht
 * anfassen). ODER-verknuepft mit sich selbst, UND-verknuepft mit search
 * (siehe repositories/candidates.py::filtered). */
function RollenFilter({ selected, onChange }: { selected: Rolle[]; onChange: (value: Rolle[]) => void }) {
  const [open, setOpen] = useState(false);

  function toggle(rolle: Rolle) {
    onChange(selected.includes(rolle) ? selected.filter((r) => r !== rolle) : [...selected, rolle]);
  }

  return (
    <div className="relative">
      <Button variant="outline" onClick={() => setOpen((current) => !current)}>
        Rollen{selected.length > 0 ? `: ${selected.length}` : ""}
        <ChevronDown size={14} />
      </Button>
      {open && (
        <>
          <div className="fixed inset-0 z-30" onClick={() => setOpen(false)} />
          <div className="absolute right-0 top-11 z-40 w-64 rounded-lg border border-white/10 bg-brand-surface p-1.5 shadow-2xl">
            {selected.length > 0 && (
              <button
                type="button"
                className="flex w-full items-center justify-between rounded-md px-3 py-2 text-left text-xs text-brand-muted hover:bg-white/8"
                onClick={() => onChange([])}
              >
                Auswahl zurücksetzen <X size={12} />
              </button>
            )}
            {ROLLE_OPTIONS.map((rolle) => (
              <label
                key={rolle}
                className="flex w-full cursor-pointer items-center gap-2 rounded-md px-3 py-2 text-left text-xs text-brand-platinum hover:bg-white/8"
              >
                <input
                  type="checkbox"
                  checked={selected.includes(rolle)}
                  onChange={() => toggle(rolle)}
                  className="accent-brand-accent"
                />
                {rolleLabel(rolle)}
              </label>
            ))}
          </div>
        </>
      )}
    </div>
  );
}

/** Mehrfachauswahl aus den 9 Abschlussarten - exakt gleiche Mechanik wie
 * RollenFilter oben (Punkt 7a des Konsolidierten Auftrags "Fehlerbehebung
 * Import + Erweiterung Extraktionsschema": "analog zum bestehenden
 * rollen-Filter, gleiche Mechanik"). ODER-verknuepft mit sich selbst,
 * UND-verknuepft mit rollen/search (siehe repositories/candidates.py::
 * filtered). */
function AbschluesseFilter({
  selected,
  onChange,
}: {
  selected: Abschlussart[];
  onChange: (value: Abschlussart[]) => void;
}) {
  const [open, setOpen] = useState(false);

  function toggle(abschlussart: Abschlussart) {
    onChange(
      selected.includes(abschlussart)
        ? selected.filter((a) => a !== abschlussart)
        : [...selected, abschlussart],
    );
  }

  return (
    <div className="relative">
      <Button variant="outline" onClick={() => setOpen((current) => !current)}>
        Abschlüsse{selected.length > 0 ? `: ${selected.length}` : ""}
        <ChevronDown size={14} />
      </Button>
      {open && (
        <>
          <div className="fixed inset-0 z-30" onClick={() => setOpen(false)} />
          <div className="absolute right-0 top-11 z-40 w-64 rounded-lg border border-white/10 bg-brand-surface p-1.5 shadow-2xl">
            {selected.length > 0 && (
              <button
                type="button"
                className="flex w-full items-center justify-between rounded-md px-3 py-2 text-left text-xs text-brand-muted hover:bg-white/8"
                onClick={() => onChange([])}
              >
                Auswahl zurücksetzen <X size={12} />
              </button>
            )}
            {ABSCHLUSSART_OPTIONS.map((abschlussart) => (
              <label
                key={abschlussart}
                className="flex w-full cursor-pointer items-center gap-2 rounded-md px-3 py-2 text-left text-xs text-brand-platinum hover:bg-white/8"
              >
                <input
                  type="checkbox"
                  checked={selected.includes(abschlussart)}
                  onChange={() => toggle(abschlussart)}
                  className="accent-brand-accent"
                />
                {abschlussartLabel(abschlussart)}
              </label>
            ))}
          </div>
        </>
      )}
    </div>
  );
}

const ROLLE_VALUES = new Set<string>(ROLLE_OPTIONS);
const ABSCHLUSSART_VALUES = new Set<string>(ABSCHLUSSART_OPTIONS);

export function CandidatesTable() {
  const router = useRouter();
  const searchParams = useSearchParams();
  // Erlaubt einen direkten Link auf den Reaktivierungs-Filter (z.B. vom
  // Redirect der entfernten /reaktivierung-Route, siehe Phase L.2).
  const [reactivationOnly, setReactivationOnly] = useState(
    () => searchParams.get("reaktivierung") === "1",
  );
  const [status, setStatus] = useState(() => searchParams.get("status") ?? "");
  const [selectedRollen, setSelectedRollen] = useState<Rolle[]>(
    () => (searchParams.get("rollen") ?? "").split(",").filter((r): r is Rolle => ROLLE_VALUES.has(r)),
  );
  const [selectedAbschluesse, setSelectedAbschluesse] = useState<Abschlussart[]>(
    () =>
      (searchParams.get("abschluesse") ?? "")
        .split(",")
        .filter((a): a is Abschlussart => ABSCHLUSSART_VALUES.has(a)),
  );
  // Echter PLZ+Umkreis-Filter (nicht der bestehende `region`-Substring-
  // Match) - radiusKm bleibt "" (kein Filter aktiv), bis der Nutzer sowohl
  // einen Ort ALS AUCH einen Radius gewaehlt hat, siehe use-server-search.ts.
  const [plzOrt, setPlzOrt] = useState(() => searchParams.get("plz") ?? "");
  const [radiusKm, setRadiusKm] = useState(() => searchParams.get("radius") ?? "");
  // "Meine Kandidaten" - reiner Komfort-Filter nach owner_user_id, KEINE
  // Sichtbarkeitsgrenze (Default "Alle" bleibt unveraendert). Siehe
  // Backend models/candidate.py::owner_user_id fuer die Begruendung.
  const [mineOnly, setMineOnly] = useState(() => searchParams.get("mine") === "1");
  // Titelschutz-Korrektur Schritt 2: eigener Filter, um Kandidaten mit
  // unbestaetigter geschuetzter Rolle wiederzufinden (Nutzer-Vorgabe -
  // "sonst findet man sie nicht wieder"). Wirkt wie plzOrt/radiusKm NICHT
  // auf die separate Reaktivierungsliste (eigene, kleine Sonder-
  // Datenquelle ohne diesen Filter, gleiches Muster wie dort).
  const [rollenUnbestaetigtOnly, setRollenUnbestaetigtOnly] = useState(
    () => searchParams.get("rollen_unbestaetigt") === "1",
  );
  // NOMICON: Kandidatenstatus-Filter (frei für Direct/AÜ, im Austausch)
  const [engagement, setEngagement] = useState<EngagementFilter | "">(() => {
    const raw = searchParams.get("engagement");
    return raw === "free_direct" || raw === "free_staffing" || raw === "engaged" ? raw : "";
  });
  // NOMICON: Überlassungs-Filter und -Spalte nur mit Ansicht Überlassung
  const { data: myViews } = useMyViews();
  const canStaffing = canSeeStaffing(myViews?.data.views);
  const [staffingFilter, setStaffingFilter] = useState<StaffingListFilter | "">(() => {
    const raw = searchParams.get("ueberlassung");
    return raw === "workers" || raw === "bench" || raw === "critical" || raw === "applicants" ? raw : "";
  });
  const activeStaffingFilter = canStaffing && staffingFilter ? staffingFilter : undefined;
  const { data: currentUserData } = useCurrentUser();
  const currentUserId = currentUserData?.data.id;
  const [sortKey, setSortKey] = useState<string | null>(
    () => searchParams.get("sort") ?? "candidate_number",
  );
  const [sortDir, setSortDir] = useState<SortDir>(
    () => (searchParams.get("dir") === "asc" ? "asc" : "desc"),
  );
  // Kandidat oeffnet im seitlichen Quickview-Panel statt per echter
  // Navigation zur Detailseite (Nutzer-Vorgabe: "im anderen Subfenster",
  // Liste bleibt gemountet) - vorher unmountete ein <Link>-Klick diese
  // Komponente komplett, alle Filter/Suche/Sortierung gingen beim
  // Zurueknavigieren verloren. Gleiches Muster wie submission-views.tsx.
  const [quickViewCandidateId, setQuickViewCandidateId] = useState<string | null>(null);

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
    rollen: selectedRollen,
    abschluesse: selectedAbschluesse,
    plzOrt,
    radiusKm: radiusKm ? Number(radiusKm) : undefined,
    rollenUnbestaetigt: rollenUnbestaetigtOnly ? true : undefined,
    engagement: engagement || undefined, // NOMICON
    staffing: activeStaffingFilter, // NOMICON
    ownerUserId: mineOnly ? currentUserId : undefined,
    sortBy: sortKey ?? undefined,
    sortDir,
    initialSearch: searchParams.get("q") ?? undefined,
    initialPage: (() => {
      const raw = Number(searchParams.get("page"));
      return Number.isFinite(raw) && raw > 0 ? raw : undefined;
    })(),
  });

  // Spiegelt alle Filter/Sortier-/Such-/Seiten-Zustaende in die URL (kurze
  // Schluessel, damit die Query-String nicht ausufert) - Zweck: der zweite
  // Einstiegspunkt zur Kandidatendetailseite (globale Suche, siehe
  // topbar.tsx::goTo) navigiert ECHT weg von /kandidaten und unmountet damit
  // diese Komponente komplett; ohne URL-Spiegelung ging beim Zurueckkehren
  // ueber "Zur Kandidatenliste" (siehe app/kandidaten/[id]/page.tsx::backLink)
  // jeder Filter/Suchtext/Sortierung/Seite verloren. Klick auf eine Zeile
  // bleibt bewusst unveraendert (siehe quickViewCandidateId oben) - dort
  // bleibt die Komponente gemountet, es gibt also gar keinen Verlust.
  // router.replace() statt push(): sonst wuerde jede Tastatureingabe/jeder
  // Filterwechsel einen eigenen Browser-History-Eintrag erzeugen.
  const debouncedUrlSearch = useDebouncedValue(search.trim(), 300);
  useEffect(() => {
    const params = new URLSearchParams();
    if (debouncedUrlSearch) params.set("q", debouncedUrlSearch);
    if (status) params.set("status", status);
    if (selectedRollen.length > 0) params.set("rollen", selectedRollen.join(","));
    if (selectedAbschluesse.length > 0) params.set("abschluesse", selectedAbschluesse.join(","));
    if (plzOrt) params.set("plz", plzOrt);
    if (radiusKm) params.set("radius", radiusKm);
    if (mineOnly) params.set("mine", "1");
    if (reactivationOnly) params.set("reaktivierung", "1");
    if (rollenUnbestaetigtOnly) params.set("rollen_unbestaetigt", "1");
    if (engagement) params.set("engagement", engagement); // NOMICON
    if (staffingFilter) params.set("ueberlassung", staffingFilter); // NOMICON
    if (sortKey) params.set("sort", sortKey);
    if (sortDir) params.set("dir", sortDir);
    if (page > 0) params.set("page", String(page));
    const query = params.toString();
    router.replace(query ? `/kandidaten?${query}` : "/kandidaten", { scroll: false });
  }, [
    debouncedUrlSearch,
    status,
    selectedRollen,
    selectedAbschluesse,
    plzOrt,
    radiusKm,
    mineOnly,
    reactivationOnly,
    rollenUnbestaetigtOnly,
    engagement, // NOMICON
    staffingFilter, // NOMICON
    sortKey,
    sortDir,
    page,
    router,
  ]);

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
  // (kleinen) Bestand, wie vor dieser Umstellung. Der PLZ+Umkreis-Filter
  // (plzOrt/radiusKm) wirkt hier BEWUSST NICHT: die Distanzberechnung lebt
  // serverseitig in services/geo.py (candidate_coordinates/haversine_km),
  // eine Kandidat-Koordinate steht im Frontend gar nicht zur Verfuegung -
  // ihn hier zu duplizieren waere ein eigenstaendiges (teureres) Stueck
  // Scope. Gleiches Muster wie bei aiResults unten: eine Sonder-Datenquelle
  // bekommt nicht zwangslaeufig jeden Filter.
  const reactivationFiltered = useMemo(() => {
    const base = reactivationCandidates.filter((candidate) => {
      if (status && candidate.status !== status) return false;
      if (mineOnly && candidate.owner_user_id !== currentUserId) return false;
      if (selectedRollen.length > 0 && !selectedRollen.some((r) => candidate.rollen?.includes(r))) {
        return false;
      }
      if (
        selectedAbschluesse.length > 0 &&
        !selectedAbschluesse.some((a) => candidate.abschluesse?.includes(a))
      ) {
        return false;
      }
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
  }, [
    reactivationCandidates,
    search,
    status,
    selectedRollen,
    selectedAbschluesse,
    mineOnly,
    currentUserId,
    sortKey,
    sortDir,
  ]);

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
  // NOMICON: Austausch-Status der angezeigten Seite per Sammelabfrage
  const { data: engagementByCandidate } = useEngagementSummaries(displayedCandidates.map((candidate) => candidate.id));
  const { data: staffingByCandidate } = useStaffingCandidateSummaries(displayedCandidates.map((candidate) => candidate.id), canStaffing);
  const displayedTotal = reactivationOnly ? reactivationFiltered.length : (aiResults?.length ?? totalCount);
  const displayedPage = reactivationOnly ? reactivationPage : page;
  const displayedPageCount = reactivationOnly ? reactivationPageCount : (aiResults ? 1 : pageCount);
  const displayedSetPage = reactivationOnly ? setReactivationPage : setPage;
  const quickViewCandidate = quickViewCandidateId
    ? displayedCandidates.find((candidate) => candidate.id === quickViewCandidateId) ?? null
    : null;

  const exportRows = useMemo(() => displayedCandidates.map((candidate) => ({
    Name: `${candidate.first_name} ${candidate.last_name}`,
    Rolle: candidate.job_title,
    Rollen: (candidate.rollen ?? []).map(rolleLabel).join(", "),
    Abschluesse: (candidate.abschluesse ?? []).map(abschlussartLabel).join(", "),
    Region: candidate.city ?? candidate.postal_code,
    Gehalt: candidate.salary_expectation,
    Status: candidate.status,
    Kurzprofil: candidate.short_profile ? "Ja" : "Nein",
    // NOMICON: Spalte nur mit Ansicht Überlassung (kein Lohn, keine Marge)
    ...(canStaffing ? { Ueberlassung: staffingCandidateText(staffingByCandidate?.[candidate.id]) } : {}),
  })), [displayedCandidates, canStaffing, staffingByCandidate]);

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
        <div className="flex flex-wrap gap-2">
          <Button
            size="sm"
            variant={reactivationOnly ? "dark" : "outline"}
            onClick={() => setReactivationOnly((current) => !current)}
          >
            <History size={14} />Erneut kontaktieren
          </Button>
          <Button
            size="sm"
            variant={rollenUnbestaetigtOnly ? "dark" : "outline"}
            onClick={() => setRollenUnbestaetigtOnly((current) => !current)}
            title="Kandidaten mit geschützter Rolle (Steuerberater/Wirtschaftsprüfer/Rechtsanwalt) ohne erkennbaren Beleg im CV"
          >
            <ShieldAlert size={14} />Titel unbestätigt
          </Button>
        </div>
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
      {rollenUnbestaetigtOnly && (
        <div className="mb-3">
          <Badge tone="amber" className="gap-1.5">
            Titel-unbestätigt-Filter aktiv
            <button type="button" onClick={() => setRollenUnbestaetigtOnly(false)} title="Filter entfernen" className="hover:text-white">
              <X size={12} />
            </button>
          </Badge>
        </div>
      )}
      <DemoNotice source={reactivationOnly ? "api" : (source ?? "api")} error={reactivationOnly ? undefined : demoError} />
      <div className="flex flex-col gap-2 sm:flex-row sm:items-start">
        <div className="flex-1">
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
        </div>
        <div className="mb-4">
          <RollenFilter selected={selectedRollen} onChange={setSelectedRollen} />
        </div>
        <div className="mb-4">
          <AbschluesseFilter selected={selectedAbschluesse} onChange={setSelectedAbschluesse} />
        </div>
        <div className="mb-4 flex gap-2">
          <input
            value={plzOrt}
            onChange={(e) => setPlzOrt(e.target.value)}
            placeholder="PLZ/Ort"
            className="h-10 w-32 rounded-md border border-white/10 bg-brand-surface px-3 text-xs text-brand-text outline-none focus:border-brand-accent"
          />
          <select
            value={radiusKm}
            onChange={(e) => setRadiusKm(e.target.value)}
            className="h-10 rounded-md border border-white/10 bg-brand-surface px-2 text-xs text-brand-platinum outline-none focus:border-brand-accent"
          >
            <option value="">Umkreis</option>
            <option value="25">25 km</option>
            <option value="50">50 km</option>
            <option value="100">100 km</option>
            <option value="200">200 km</option>
          </select>
          {/* NOMICON: Kandidatenstatus-Filter */}
          <select
            value={engagement}
            onChange={(e) => setEngagement(e.target.value as EngagementFilter | "")}
            aria-label="Austausch-Status"
            className="h-10 rounded-md border border-white/10 bg-brand-surface px-2 text-xs text-brand-platinum outline-none focus:border-brand-accent"
          >
            <option value="">Austausch</option>
            {(Object.keys(ENGAGEMENT_FILTER_LABELS) as EngagementFilter[]).map((value) => (
              <option key={value} value={value}>{ENGAGEMENT_FILTER_LABELS[value]}</option>
            ))}
          </select>
          {/* NOMICON: Überlassungs-Filter (nur mit Ansicht Überlassung) */}
          {canStaffing && (
            <select
              value={staffingFilter}
              onChange={(e) => setStaffingFilter(e.target.value as StaffingListFilter | "")}
              aria-label="Überlassung"
              className="h-10 rounded-md border border-white/10 bg-brand-surface px-2 text-xs text-brand-platinum outline-none focus:border-brand-accent"
            >
              <option value="">Überlassung</option>
              {(Object.keys(STAFFING_FILTER_LABELS) as StaffingListFilter[]).map((value) => (
                <option key={value} value={value}>{STAFFING_FILTER_LABELS[value]}</option>
              ))}
            </select>
          )}
        </div>
      </div>
      {(selectedRollen.length > 0 || selectedAbschluesse.length > 0 || (plzOrt.trim() && radiusKm)) && (
        <div className="mb-3 flex flex-wrap gap-1.5">
          {selectedRollen.map((rolle) => (
            <Badge key={rolle} tone="blue" className="gap-1.5">
              {rolleLabel(rolle)}
              <button type="button" onClick={() => setSelectedRollen((current) => current.filter((r) => r !== rolle))} className="hover:text-white">
                <X size={12} />
              </button>
            </Badge>
          ))}
          {selectedAbschluesse.map((abschlussart) => (
            <Badge key={abschlussart} tone="blue" className="gap-1.5">
              {abschlussartLabel(abschlussart)}
              <button
                type="button"
                onClick={() =>
                  setSelectedAbschluesse((current) => current.filter((a) => a !== abschlussart))
                }
                className="hover:text-white"
              >
                <X size={12} />
              </button>
            </Badge>
          ))}
          {plzOrt.trim() && radiusKm && (
            <Badge tone="blue" className="gap-1.5">
              {radiusKm} km um {plzOrt.trim()}
              <button type="button" onClick={() => { setPlzOrt(""); setRadiusKm(""); }} className="hover:text-white">
                <X size={12} />
              </button>
            </Badge>
          )}
        </div>
      )}
      <ErrorBanner message={aiError} className="mb-3" />
      {aiResults && (
        <div className="mb-3 flex items-center justify-between rounded-lg border border-brand-accent/30 bg-brand-accent/10 p-3 text-xs text-brand-soft">
          <span>KI-Suche aktiv: {aiResults.length} Treffer für &quot;{search}&quot;</span>
          <button
            className="text-brand-muted underline hover:text-white"
            onClick={() => { setAiResults(null); setAiHint(null); }}
          >
            Zurück zur normalen Filterung
          </button>
        </div>
      )}
      {aiHint && (
        <div className="mb-3 rounded-lg border border-brand-warning/25 bg-brand-warning/5 p-3 text-xs text-brand-warning">{aiHint}</div>
      )}
      {/* Mobile (<lg): Karten statt der 10-spaltigen Desktop-Tabelle - die
       * Tabelle bleibt unten fuer den Desktop unveraendert bestehen (siehe
       * "hidden lg:block"), aber auf einem Telefon war sie faktisch nur die
       * ersten ~2 Spalten (Nr./Name), der Rest nur per Horizontal-Scroll
       * erreichbar (Nutzer-Feedback "mobile Version nicht passend"). Zeigt
       * dieselben Kerninformationen wie die Tabelle, nur gestapelt statt
       * spaltenweise. */}
      <div className="space-y-2 lg:hidden">
        {displayedCandidates.map((candidate) => (
          <button
            key={candidate.id}
            type="button"
            onClick={() => setQuickViewCandidateId(candidate.id)}
            className="block w-full rounded-lg border border-white/10 bg-brand-panel p-3 text-left active:bg-brand-hover/35"
          >
            <div className="flex items-start justify-between gap-2">
              <div className="min-w-0">
                <p className="flex items-center gap-1.5 truncate text-sm font-semibold text-brand-platinum">
                  {candidate.candidate_number && (
                    <span className="text-brand-muted">{candidate.candidate_number}</span>
                  )}
                  {candidate.first_name} {candidate.last_name}
                  {candidate.has_ghosting_history && (
                    <Ghost size={12} className="shrink-0 text-brand-danger-soft" aria-label="Ghosting-Historie" />
                  )}
                </p>
                <p className="mt-0.5 truncate text-xs text-brand-muted">
                  {candidate.job_title ?? "—"} · {candidate.city ?? candidate.postal_code ?? "Region offen"}
                </p>
              </div>
              <StatusPill status={candidate.status} />
            </div>
            <EngagementBadge summary={engagementByCandidate?.[candidate.id]} className="mt-2" /> {/* NOMICON */}
            {canStaffing && <StaffingCandidateCell summary={staffingByCandidate?.[candidate.id]} compact />} {/* NOMICON */}
            {candidate.rollen && candidate.rollen.length > 0 && (
              <div className="mt-2 flex flex-wrap items-center gap-1">
                {candidate.rollen.map((rolle) => <Badge key={rolle} tone="blue">{rolleLabel(rolle)}</Badge>)}
                {candidate.rollen_unbestaetigt && (
                  <span title="Titel unbestätigt - kein erkennbarer Beleg im CV">
                    <ShieldAlert size={13} className="text-brand-warning" />
                  </span>
                )}
              </div>
            )}
            <div className="mt-2 flex items-center justify-between text-[10.45px] text-brand-gray">
              <span>Kontakt {formatDate(candidate.last_contact_at ?? candidate.updated_at)}</span>
              {candidate.salary_expectation && <span>{candidate.salary_expectation}</span>}
            </div>
            {candidate.search_match_fields && candidate.search_match_fields.length > 0 && (
              <p className="mt-1.5 text-[10.45px] text-brand-warning">
                Treffer in: {candidate.search_match_fields.map(searchFieldLabel).join(", ")}
                {candidate.search_matched_values && candidate.search_matched_values.length > 0 && (
                  <> ({candidate.search_matched_values.join(", ")})</>
                )}
              </p>
            )}
          </button>
        ))}
        {displayedCandidates.length === 0 && (
          <p className="py-8 text-center text-xs text-brand-muted">Keine Kandidaten gefunden.</p>
        )}
      </div>
      <div className="hidden lg:block">
      <DataTable
        headers={[
          { label: "Nr.", key: "candidate_number" },
          { label: "Name", key: "name" },
          { label: "Rolle / Qualifikation", key: "job_title" },
          "Rollen",
          { label: "Region", key: "city" },
          { label: "Gehalt", key: "salary_expectation" },
          "Verfügbarkeit",
          "Unterlagen",
          { label: "Status", key: "status" },
          "Austausch", // NOMICON
          ...(canStaffing ? ["Überlassung"] : []), // NOMICON
          "Nächster Schritt",
        ]}
        sortKey={sortKey}
        sortDir={sortDir}
        onSort={handleSort}
      >
        {displayedCandidates.map((candidate) => (
          <tr key={candidate.id} className="hover:bg-brand-hover/35">
            <td className="px-4 py-3.5 text-xs text-brand-muted">{candidate.candidate_number ?? "—"}</td>
            <td className="px-4 py-3.5"><button type="button" onClick={() => setQuickViewCandidateId(candidate.id)} className="font-semibold text-brand-platinum hover:text-white hover:underline">{candidate.first_name} {candidate.last_name}</button>{candidate.has_ghosting_history && <Ghost size={12} className="ml-1.5 inline text-brand-danger-soft" aria-label="Ghosting-Historie" />}<p className="mt-1 text-[10.45px] text-brand-muted">Kontakt {formatDate(candidate.last_contact_at ?? candidate.updated_at)}</p>
              {/* Nachvollziehbarkeit der Freitextsuche (Punkt 5) - nur
               * gesetzt, wenn `search` aktiv ist (siehe Backend
               * repositories/candidates.py::compute_search_match_fields). */}
              {candidate.search_match_fields && candidate.search_match_fields.length > 0 && (
                <p className="mt-1 text-[10.45px] text-brand-warning">
                  Treffer in: {candidate.search_match_fields.map(searchFieldLabel).join(", ")}
                  {candidate.search_matched_values && candidate.search_matched_values.length > 0 && (
                    <> ({candidate.search_matched_values.join(", ")})</>
                  )}
                </p>
              )}
            </td>
            <td className="px-4 py-3.5"><p>{candidate.job_title ?? "—"}</p><p className="mt-1 text-[10.45px] text-brand-muted">{candidate.qualification ?? "Qualifikation offen"}</p></td>
            <td className="px-4 py-3.5">
              {candidate.rollen && candidate.rollen.length > 0 ? (
                <div className="flex flex-wrap items-center gap-1">
                  {candidate.rollen.map((rolle) => <Badge key={rolle} tone="blue">{rolleLabel(rolle)}</Badge>)}
                  {/* Titelschutz-Korrektur Schritt 2: dezenter Hinweis am
                   * Rollen-Badge, wenn die geschuetzte Rolle unbelegt ist -
                   * rollen selbst bleibt unangetastet, siehe Kandidatendetail
                   * fuer die Bestaetigen-/Korrigieren-Aktionen. */}
                  {candidate.rollen_unbestaetigt && (
                    <span title="Titel unbestätigt - kein erkennbarer Beleg im CV">
                      <ShieldAlert size={13} className="text-brand-warning" />
                    </span>
                  )}
                </div>
              ) : (
                <span className="text-brand-muted">—</span>
              )}
            </td>
            <td className="px-4 py-3.5 text-brand-soft">{candidate.city ?? candidate.postal_code ?? "—"}</td>
            <td className="px-4 py-3.5">{candidate.salary_expectation ?? "—"}</td>
            <td className="px-4 py-3.5"><p>{candidate.notice_period ?? "—"}</p><p className="mt-1 text-[10.45px] text-brand-muted">{candidate.available_from ? formatDate(candidate.available_from) : "nach Absprache"}</p></td>
            <td className="px-4 py-3.5"><div className="flex gap-1.5"><span className={`size-2 rounded-full ${candidate.cv_available ? "bg-brand-silver" : "bg-[#334155]"}`} title="CV" /><span className={`size-2 rounded-full ${candidate.short_profile ? "bg-brand-accent" : "bg-[#334155]"}`} title="Kurzprofil" /></div></td>
            <td className="px-4 py-3.5"><StatusPill status={candidate.status} /></td>
            <td className="px-4 py-3.5"><EngagementBadge summary={engagementByCandidate?.[candidate.id]} /></td>{/* NOMICON */}
            {canStaffing && <td className="px-4 py-3.5"><StaffingCandidateCell summary={staffingByCandidate?.[candidate.id]} /></td>}{/* NOMICON */}
            <td className="px-4 py-3.5 text-brand-soft">{candidate.next_step ?? "Kontakt aufnehmen"}</td>
          </tr>
        ))}
      </DataTable>
      </div>
      <PaginationControls page={displayedPage} pageCount={displayedPageCount} onChange={displayedSetPage} />
      <p className="mt-3 text-xs text-brand-gray">{displayedCandidates.length} von {displayedTotal} Kandidaten</p>

      <CandidateQuickViewDrawer
        candidate={quickViewCandidate}
        onClose={() => setQuickViewCandidateId(null)}
        backTo="kandidaten"
        backHref={searchParams.toString() ? `/kandidaten?${searchParams.toString()}` : "/kandidaten"}
      />
    </>
  );
}
