"use client";

import { Fragment, useMemo, useState } from "react";
import Link from "next/link";
import { ChevronDown, ChevronRight } from "lucide-react";
import { FilterBar } from "@/components/crm/filter-bar";
import { DataTable } from "@/components/crm/data-table";
import { StatusPill } from "@/components/crm/status-pill";
import { Badge } from "@/components/ui/badge";
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
  // GESAMTEN Bestand, nicht mehr nur die aktuell geladene Seite.
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
      {/* Mobile (<lg): Karten statt der 9-spaltigen Desktop-Tabelle, siehe
       * candidates-table.tsx fuer denselben Fix + Begruendung (Nutzer-
       * Feedback "mobile Version nicht passend"). */}
      <div className="space-y-2 lg:hidden">
        {rows.map((row) => {
          if (row.kind === "single") {
            const client = row.client;
            return (
              <Link
                key={client.id}
                href={`/kanzleien/${client.id}`}
                className="block rounded-lg border border-white/10 bg-brand-panel p-3 active:bg-brand-hover/35"
              >
                <div className="flex items-start justify-between gap-2">
                  <p className="min-w-0 truncate text-sm font-semibold text-brand-platinum">{client.name}</p>
                  <StatusPill status={client.status} />
                </div>
                <p className="mt-0.5 truncate text-xs text-brand-muted">
                  {client.region ?? client.city ?? client.postal_code ?? "Region offen"}
                  {client.focus ? ` · ${client.focus}` : ""}
                </p>
                <div className="mt-2 flex items-center justify-between text-[10.45px] text-brand-gray">
                  <span>Kontakt {formatDate(client.last_contact_at ?? client.updated_at)}</span>
                  <span>{client.fee_percentage ?? 27} % Honorar</span>
                </div>
              </Link>
            );
          }

          const { groupKey, locations } = row;
          const isExpanded = expandedGroup === groupKey;
          const postalCodes = [...new Set(locations.map((loc) => loc.postal_code).filter(Boolean))];
          return (
            <div key={groupKey} className="rounded-lg border border-white/10 bg-brand-panel">
              <button
                type="button"
                onClick={() => setExpandedGroup(isExpanded ? null : groupKey)}
                className="flex w-full items-center justify-between gap-2 p-3 text-left"
              >
                <span className="flex min-w-0 items-center gap-1.5 truncate text-sm font-semibold text-brand-platinum">
                  {isExpanded ? <ChevronDown size={14} className="shrink-0" /> : <ChevronRight size={14} className="shrink-0" />}
                  <span className="truncate">{groupKey}</span>
                </span>
                <span className="shrink-0 text-[10.45px] text-brand-muted">{locations.length} Standorte</span>
              </button>
              {isExpanded && (
                <div className="space-y-2 border-t border-white/10 p-2">
                  {locations.map((client) => (
                    <Link
                      key={client.id}
                      href={`/kanzleien/${client.id}`}
                      className="block rounded-lg border border-white/10 bg-brand-surface/60 p-3 active:bg-brand-hover/35"
                    >
                      <div className="flex items-start justify-between gap-2">
                        <p className="min-w-0 truncate text-sm font-semibold text-brand-platinum">{client.name}</p>
                        <StatusPill status={client.status} />
                      </div>
                      <p className="mt-0.5 truncate text-xs text-brand-muted">
                        {client.postal_code ?? "PLZ offen"}
                      </p>
                    </Link>
                  ))}
                </div>
              )}
              {!isExpanded && postalCodes.length > 0 && (
                <p className="px-3 pb-3 text-[10.45px] text-brand-muted">PLZ: {postalCodes.join(", ")}</p>
              )}
            </div>
          );
        })}
        {rows.length === 0 && (
          <p className="py-8 text-center text-xs text-brand-muted">Keine Kanzleien gefunden.</p>
        )}
      </div>
      <div className="hidden lg:block">
      <DataTable
        headers={[
          { label: "Kanzlei", key: "name" },
          { label: "Region", key: "region" },
          { label: "Größe", key: "company_size" },
          { label: "Fokus", key: "focus" },
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
              <tr key={client.id} className="hover:bg-brand-hover/35">
                <td className="px-4 py-3.5"><Link href={`/kanzleien/${client.id}`} className="font-semibold text-brand-platinum hover:text-white hover:underline">{client.name}</Link><div className="mt-1 flex flex-wrap items-center gap-1.5"><StatusPill status={client.status} />{client.approval_pending && <Badge tone="amber">Freigabe ausstehend</Badge>}</div></td>
                <td className="px-4 py-3.5">{client.region ?? client.city ?? client.postal_code ?? "—"}</td>
                <td className="px-4 py-3.5 text-brand-soft">{client.company_size ?? "—"}</td>
                <td className="px-4 py-3.5">{client.focus ?? "—"}</td>
                <td className="px-4 py-3.5 text-brand-soft">{formatDate(client.last_contact_at ?? client.updated_at)}</td>
                <td className="px-4 py-3.5"><StatusPill status={client.terms_status === "accepted" || client.terms_status === "Unterzeichnet" ? "active" : "draft"} /></td>
                <td className="px-4 py-3.5 font-medium">{client.fee_percentage ?? 27} %</td>
              </tr>
            );
          }

          const { groupKey, locations } = row;
          const isExpanded = expandedGroup === groupKey;
          const postalCodes = [...new Set(locations.map((loc) => loc.postal_code).filter(Boolean))];
          const mostRecentContact = locations
            .map((loc) => loc.last_contact_at ?? loc.updated_at)
            .filter(Boolean)
            .sort()
            .at(-1);

          return (
            <Fragment key={groupKey}>
              <tr
                className="cursor-pointer hover:bg-brand-hover/35"
                onClick={() => setExpandedGroup(isExpanded ? null : groupKey)}
              >
                <td className="px-4 py-3.5">
                  <span className="inline-flex items-center gap-1.5 font-semibold text-brand-platinum">
                    {isExpanded ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
                    {groupKey}
                  </span>
                  <p className="mt-1 text-[10.45px] text-brand-muted">{locations.length} Standorte</p>
                </td>
                <td className="px-4 py-3.5">
                  <div className="flex flex-wrap gap-1">
                    {postalCodes.length > 0
                      ? postalCodes.map((plz) => (
                          <span key={plz} className="rounded-full border border-white/10 bg-brand-surface px-2 py-0.5 text-[10.45px] text-brand-soft">{plz}</span>
                        ))
                      : "—"}
                  </div>
                </td>
                <td className="px-4 py-3.5 text-brand-soft">—</td>
                <td className="px-4 py-3.5">{locations[0]?.focus ?? "—"}</td>
                <td className="px-4 py-3.5 text-brand-soft">{mostRecentContact ? formatDate(mostRecentContact) : "—"}</td>
                <td className="px-4 py-3.5">—</td>
                <td className="px-4 py-3.5 font-medium">—</td>
              </tr>
              {isExpanded &&
                locations.map((client) => (
                  <tr key={client.id} className="bg-brand-surface/40 hover:bg-brand-hover/35">
                    <td className="px-4 py-3.5 pl-9"><Link href={`/kanzleien/${client.id}`} className="font-semibold text-brand-platinum hover:text-white hover:underline">{client.name}</Link><div className="mt-1 flex flex-wrap items-center gap-1.5"><StatusPill status={client.status} />{client.approval_pending && <Badge tone="amber">Freigabe ausstehend</Badge>}</div></td>
                    <td className="px-4 py-3.5">{client.region ?? client.city ?? client.postal_code ?? "—"}</td>
                    <td className="px-4 py-3.5 text-brand-soft">{client.company_size ?? "—"}</td>
                    <td className="px-4 py-3.5">{client.focus ?? "—"}</td>
                    <td className="px-4 py-3.5 text-brand-soft">{formatDate(client.last_contact_at ?? client.updated_at)}</td>
                    <td className="px-4 py-3.5"><StatusPill status={client.terms_status === "accepted" || client.terms_status === "Unterzeichnet" ? "active" : "draft"} /></td>
                    <td className="px-4 py-3.5 font-medium">{client.fee_percentage ?? 27} %</td>
                  </tr>
                ))}
            </Fragment>
          );
        })}
      </DataTable>
      </div>
      <PaginationControls page={page} pageCount={pageCount} onChange={setPage} />
      <p className="mt-3 text-xs text-brand-gray">{sorted.length} von {totalCount} Kanzleien</p>
    </>
  );
}
