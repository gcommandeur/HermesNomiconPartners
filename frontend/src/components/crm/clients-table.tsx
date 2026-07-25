"use client";

import { useMemo, useState } from "react";
import Link from "next/link";
import { ChevronDown, ChevronRight } from "lucide-react";
import { FilterBar } from "@/components/crm/filter-bar";
import { DataTable } from "@/components/crm/data-table";
import { StatusPill } from "@/components/crm/status-pill";
import { ExportActions } from "@/components/crm/export-actions";
import { DemoNotice } from "@/components/crm/demo-notice";
import { ErrorState } from "@/components/crm/error-state";
import { ListSkeleton } from "@/components/crm/list-skeleton";
import { PaginationControls } from "@/components/crm/pagination-controls";
import { formatDate, termsStatusLabel } from "@/lib/utils";
import { useCurrentUser } from "@/lib/api/hooks";
import { useServerSearchList } from "@/lib/api/use-server-search";
import { getClientsPage } from "@/lib/api/queries";
import type { ClientCompany } from "@/lib/api/types";

const STATUS_OPTIONS = [
  { value: "active", label: "Aktiv (grün)" },
  { value: "acquisition", label: "In Verhandlung (gelb)" },
  { value: "prospect", label: "Noch kein Kontakt (grau)" },
  { value: "blocked", label: "Do not touch (rot)" },
  { value: "archived", label: "Archiviert" },
];

type ClientRow =
  | { kind: "single"; client: ClientCompany }
  | { kind: "group"; groupKey: string; locations: ClientCompany[] };

/** Fasst Kanzleien mit identischem, nicht-leerem kanzleigruppe-Wert (z.B.
 * "ECOVIS") zu einer Zeile zusammen - reine Darstellungsaenderung, die
 * einzelnen ClientCompany-Datensaetze (eigene Adresse/Kontakte je Standort)
 * bleiben unveraendert eigenstaendig (siehe models/client_company.py).
 * Gruppierung wirkt bewusst nur innerhalb der aktuell serverseitig
 * geladenen Seite - eine gruppenweite Zusammenfassung ueber die gesamte
 * Paginierung hinweg wuerde eine eigene Backend-Aggregation brauchen. */
function groupByKanzleigruppe(clients: ClientCompany[]): ClientRow[] {
  const seenGroups = new Set<string>();
  const rows: ClientRow[] = [];
  for (const client of clients) {
    const group = client.kanzleigruppe?.trim();
    if (!group) {
      rows.push({ kind: "single", client });
      continue;
    }
    if (seenGroups.has(group)) continue;
    seenGroups.add(group);
    const locations = clients.filter((candidate) => candidate.kanzleigruppe?.trim() === group);
    rows.push({ kind: "group", groupKey: group, locations });
  }
  return rows;
}

export function ClientsTable() {
  const [status, setStatus] = useState("");
  // "Meine Kanzleien" - reiner Komfort-Filter nach owner_user_id, KEINE
  // Sichtbarkeitsgrenze (Default "Alle" bleibt unveraendert).
  const [mineOnly, setMineOnly] = useState(false);
  const { data: currentUserData } = useCurrentUser();
  const currentUserId = currentUserData?.data.id;
  const [sortKey, setSortKey] = useState<string | null>("name");
  const [sortDir, setSortDir] = useState<"asc" | "desc">("asc");

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
  // Kanzlei-Bestand. Sortierung laeuft ueber ORDER BY im Backend (siehe
  // repositories/clients.py::_order_by_clauses) und damit ueber den
  // GESAMTEN Bestand, nicht mehr nur die aktuell geladene Seite. Fuer
  // "active_mandates" gibt es kein Backend-Feld (siehe Kommentar in
  // SORT_ACCESSORS unten) - der Server ignoriert diesen sortBy-Wert und
  // faellt auf die Default-Sortierung nach Name zurueck.
  const {
    search,
    setSearch,
    page,
    setPage,
    pageCount,
    items: clients,
    totalCount,
    hasLoadedOnce,
    isValidating,
    error,
    source,
    demoError,
    retry,
  } = useServerSearchList<ClientCompany>("/clients", getClientsPage, {
    status,
    ownerUserId: mineOnly ? currentUserId : undefined,
    sortBy: sortKey ?? undefined,
    sortDir,
  });
  const sorted = clients;
  const [expandedGroup, setExpandedGroup] = useState<string | null>(null);
  const rows = useMemo(() => groupByKanzleigruppe(sorted), [sorted]);

  const exportRows = useMemo(() => sorted.map((client) => ({
    Kanzlei: client.name,
    Status: client.status,
    Region: client.region ?? client.city ?? client.postal_code,
    Fokus: client.focus,
    Ansprechpartner: client.contact_name,
    AGB: termsStatusLabel(client.terms_status),
    Honorar: client.fee_percentage ?? 27,
  })), [sorted]);

  if (error) {
    return <ErrorState onRetry={() => void retry()} />;
  }

  // Skeleton NUR beim allerersten Laden - siehe list-skeleton.tsx, warum
  // hier NICHT SWRs `isLoading` verwendet werden darf (Fokusverlust im
  // Suchfeld bei jedem Tastendruck).
  if (!hasLoadedOnce) {
    return <ListSkeleton />;
  }

  return (
    <>
      <div className="mb-4 flex justify-end"><ExportActions filename="kanzleien" rows={exportRows} /></div>
      <DemoNotice source={source ?? "api"} error={demoError} />
      <FilterBar
        placeholder="Nach Kanzlei, Region oder Fokus suchen"
        value={search}
        onChange={setSearch}
        statusOptions={STATUS_OPTIONS}
        statusValue={status}
        onStatusChange={setStatus}
        ownerFilter={{ mineOnly, onChange: setMineOnly }}
        loading={isValidating}
      />
      <DataTable
        headers={[
          { label: "Kanzlei", key: "name" },
          { label: "Region", key: "region" },
          { label: "Größe", key: "company_size" },
          { label: "Fokus", key: "focus" },
          "Hauptkontakt",
          { label: "Mandate", key: "active_mandates" },
          { label: "Letzter Kontakt", key: "last_contact_at" },
          "AGB",
          { label: "Honorar", key: "fee_percentage" },
        ]}
        sortKey={sortKey}
        sortDir={sortDir}
        onSort={handleSort}
      >
        {rows.map((row) => {
          if (row.kind === "single") {
            const client = row.client;
            return (
              <tr key={client.id} className="hover:bg-[#203A5A]/35">
                <td className="px-4 py-3.5"><Link href={`/kanzleien/${client.id}`} className="font-semibold text-[#D8DADF] hover:text-white hover:underline">{client.name}</Link><div className="mt-1"><StatusPill status={client.status} /></div></td>
                <td className="px-4 py-3.5">{client.region ?? client.city ?? client.postal_code ?? "—"}</td>
                <td className="px-4 py-3.5 text-[#CBD5E1]">{client.company_size ?? client.size ?? "—"}</td>
                <td className="px-4 py-3.5">{client.focus ?? "—"}</td>
                <td className="px-4 py-3.5">{client.contact_name ?? "—"}</td>
                <td className="px-4 py-3.5 text-center">{client.active_mandates ?? 0}</td>
                <td className="px-4 py-3.5 text-[#CBD5E1]">{formatDate(client.last_contact_at ?? client.last_contact ?? client.updated_at)}</td>
                <td className="px-4 py-3.5"><StatusPill status={client.terms_status === "accepted" || client.terms_status === "Unterzeichnet" ? "active" : "draft"} /></td>
                <td className="px-4 py-3.5 font-medium">{client.fee_percentage ?? 27} %</td>
              </tr>
            );
          }

          const { groupKey, locations } = row;
          const isExpanded = expandedGroup === groupKey;
          const postalCodes = [...new Set(locations.map((loc) => loc.postal_code).filter(Boolean))];
          const totalMandates = locations.reduce((sum, loc) => sum + (loc.active_mandates ?? 0), 0);
          const mostRecentContact = locations
            .map((loc) => loc.last_contact_at ?? loc.last_contact ?? loc.updated_at)
            .filter(Boolean)
            .sort()
            .at(-1);

          return (
            <>
              <tr
                key={groupKey}
                className="cursor-pointer hover:bg-[#203A5A]/35"
                onClick={() => setExpandedGroup(isExpanded ? null : groupKey)}
              >
                <td className="px-4 py-3.5">
                  <span className="inline-flex items-center gap-1.5 font-semibold text-[#D8DADF]">
                    {isExpanded ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
                    {groupKey}
                  </span>
                  <p className="mt-1 text-[11px] text-[#94A3B8]">{locations.length} Standorte</p>
                </td>
                <td className="px-4 py-3.5">
                  <div className="flex flex-wrap gap-1">
                    {postalCodes.length > 0
                      ? postalCodes.map((plz) => (
                          <span key={plz} className="rounded-full border border-white/10 bg-[#0D1B2E] px-2 py-0.5 text-[11px] text-[#CBD5E1]">{plz}</span>
                        ))
                      : "—"}
                  </div>
                </td>
                <td className="px-4 py-3.5 text-[#CBD5E1]">—</td>
                <td className="px-4 py-3.5">{locations[0]?.focus ?? "—"}</td>
                <td className="px-4 py-3.5">—</td>
                <td className="px-4 py-3.5 text-center">{totalMandates}</td>
                <td className="px-4 py-3.5 text-[#CBD5E1]">{mostRecentContact ? formatDate(mostRecentContact) : "—"}</td>
                <td className="px-4 py-3.5">—</td>
                <td className="px-4 py-3.5 font-medium">—</td>
              </tr>
              {isExpanded &&
                locations.map((client) => (
                  <tr key={client.id} className="bg-[#0D1B2E]/40 hover:bg-[#203A5A]/35">
                    <td className="px-4 py-3.5 pl-9"><Link href={`/kanzleien/${client.id}`} className="font-semibold text-[#D8DADF] hover:text-white hover:underline">{client.name}</Link><div className="mt-1"><StatusPill status={client.status} /></div></td>
                    <td className="px-4 py-3.5">{client.region ?? client.city ?? client.postal_code ?? "—"}</td>
                    <td className="px-4 py-3.5 text-[#CBD5E1]">{client.company_size ?? client.size ?? "—"}</td>
                    <td className="px-4 py-3.5">{client.focus ?? "—"}</td>
                    <td className="px-4 py-3.5">{client.contact_name ?? "—"}</td>
                    <td className="px-4 py-3.5 text-center">{client.active_mandates ?? 0}</td>
                    <td className="px-4 py-3.5 text-[#CBD5E1]">{formatDate(client.last_contact_at ?? client.last_contact ?? client.updated_at)}</td>
                    <td className="px-4 py-3.5"><StatusPill status={client.terms_status === "accepted" || client.terms_status === "Unterzeichnet" ? "active" : "draft"} /></td>
                    <td className="px-4 py-3.5 font-medium">{client.fee_percentage ?? 27} %</td>
                  </tr>
                ))}
            </>
          );
        })}
      </DataTable>
      <PaginationControls page={page} pageCount={pageCount} onChange={setPage} />
      <p className="mt-3 text-xs text-[#8a9095]">{sorted.length} von {totalCount} Kanzleien</p>
    </>
  );
}
