"use client";

import { useMemo, useState } from "react";
import Link from "next/link";
import { FilterBar } from "@/components/crm/filter-bar";
import { DataTable } from "@/components/crm/data-table";
import { StatusPill } from "@/components/crm/status-pill";
import { ExportActions } from "@/components/crm/export-actions";
import { DemoNotice } from "@/components/crm/demo-notice";
import { ErrorState } from "@/components/crm/error-state";
import { PaginationControls } from "@/components/crm/pagination-controls";
import { formatDate, termsStatusLabel } from "@/lib/utils";
import { compareValues } from "@/lib/sort";
import { useClientsCache } from "@/lib/api/hooks";
import { usePagination } from "@/lib/use-pagination";
import type { ClientCompany } from "@/lib/api/types";

const STATUS_OPTIONS = [
  { value: "active", label: "Aktiv (grün)" },
  { value: "acquisition", label: "In Verhandlung (gelb)" },
  { value: "prospect", label: "Noch kein Kontakt (grau)" },
  { value: "blocked", label: "Do not touch (rot)" },
  { value: "archived", label: "Archiviert" },
];

const SORT_ACCESSORS: Record<string, (client: ClientCompany) => unknown> = {
  name: (c) => c.name,
  region: (c) => c.region ?? c.city ?? c.postal_code,
  company_size: (c) => c.company_size ?? c.size,
  focus: (c) => c.focus,
  active_mandates: (c) => c.active_mandates ?? 0,
  last_contact_at: (c) => c.last_contact_at ?? c.last_contact ?? c.updated_at,
  fee_percentage: (c) => Number(c.fee_percentage ?? 27),
};

export function ClientsTable() {
  const { data, isLoading, error, mutate: retry } = useClientsCache();
  const clients = useMemo(() => data?.data ?? [], [data]);
  const [search, setSearch] = useState("");
  const [status, setStatus] = useState("");
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

  const filtered = useMemo(() => {
    const base = clients.filter((client) => {
      if (status && client.status !== status) return false;
      const term = search.trim().toLowerCase();
      if (!term) return true;
      const haystack = [
        client.name, client.kanzleigruppe, client.region, client.city, client.postal_code, client.focus,
      ].filter(Boolean).join(" ").toLowerCase();
      return haystack.includes(term);
    });
    if (!sortKey || !SORT_ACCESSORS[sortKey]) return base;
    const accessor = SORT_ACCESSORS[sortKey];
    return [...base].sort((a, b) => compareValues(accessor(a), accessor(b), sortDir));
  }, [clients, search, status, sortKey, sortDir]);

  const { pageItems, page, pageCount, setPage } = usePagination(filtered);

  const exportRows = useMemo(() => filtered.map((client) => ({
    Kanzlei: client.name,
    Status: client.status,
    Region: client.region ?? client.city ?? client.postal_code,
    Fokus: client.focus,
    Ansprechpartner: client.contact_name,
    AGB: termsStatusLabel(client.terms_status),
    Honorar: client.fee_percentage ?? 27,
  })), [filtered]);

  if (error) {
    return <ErrorState onRetry={() => void retry()} />;
  }

  if (isLoading) {
    return (
      <div className="space-y-2">
        {Array.from({ length: 8 }).map((_, index) => (
          <div key={index} className="h-14 animate-pulse rounded-lg bg-[#0D1B2E]" />
        ))}
      </div>
    );
  }

  return (
    <>
      <div className="mb-4 flex justify-end"><ExportActions filename="kanzleien" rows={exportRows} /></div>
      <DemoNotice source={data?.source ?? "api"} error={data?.error} />
      <FilterBar
        placeholder="Nach Kanzlei, Region oder Fokus suchen"
        value={search}
        onChange={setSearch}
        statusOptions={STATUS_OPTIONS}
        statusValue={status}
        onStatusChange={setStatus}
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
        {pageItems.map((client) => (
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
        ))}
      </DataTable>
      <PaginationControls page={page} pageCount={pageCount} onChange={setPage} />
      <p className="mt-3 text-xs text-[#8a9095]">{filtered.length} von {clients.length} Kanzleien</p>
    </>
  );
}
