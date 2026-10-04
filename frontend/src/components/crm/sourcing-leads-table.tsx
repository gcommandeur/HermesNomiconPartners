"use client";

import { useState } from "react";
import Link from "next/link";
import useSWR from "swr";
import { ExternalLink, UserRoundSearch } from "lucide-react";
import { DataTable } from "@/components/crm/data-table";
import { ErrorState } from "@/components/crm/error-state";
import { ErrorBanner } from "@/components/crm/error-banner";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { formatDate } from "@/lib/utils";
import { apiPost } from "@/lib/api/client";
import { invalidateCandidatesCache } from "@/lib/api/hooks";
import { getOpenSourcingLeads } from "@/lib/api/queries";
import type { DataResult, SourcingLead, SourcingSourceType } from "@/lib/api/types";

const SOURCE_LABELS: Record<SourcingSourceType, string> = {
  steuerberaterverzeichnis: "StB-Verzeichnis",
  wpk_berufsregister: "WPK-Register",
  brak_anwaltsverzeichnis: "BRAK-Verzeichnis",
  kanzlei_team_page: "Kanzlei-Team-Seite",
};

export function SourcingLeadsTable() {
  const { data, isLoading, error, mutate } = useSWR<DataResult<SourcingLead[]>>(
    "/sourcing/leads-open",
    getOpenSourcingLeads,
    { revalidateOnFocus: false, dedupingInterval: 30_000 },
  );
  const [actionError, setActionError] = useState<string | null>(null);
  // Verhindert Doppel-Klicks waehrend approve/reject laeuft (pro Zeile).
  const [busyLeadId, setBusyLeadId] = useState<string | null>(null);

  const leads = data?.data ?? [];
  const duplicateLeads = leads.filter((lead) => lead.status === "possible_duplicate");
  const pendingLeads = leads.filter((lead) => lead.status === "pending");

  async function handleAction(lead: SourcingLead, action: "approve" | "reject") {
    setBusyLeadId(lead.id);
    setActionError(null);
    try {
      await apiPost(`/sourcing/leads/${lead.id}/${action}`, {});
      if (action === "approve") await invalidateCandidatesCache();
      await mutate();
    } catch (exception) {
      setActionError(exception instanceof Error ? exception.message : "Aktion fehlgeschlagen.");
    } finally {
      setBusyLeadId(null);
    }
  }

  if (error) return <ErrorState onRetry={() => void mutate()} />;

  if (isLoading) {
    return (
      <div className="space-y-2">
        {Array.from({ length: 6 }).map((_, index) => (
          <div key={index} className="h-14 animate-pulse rounded-lg bg-brand-surface" />
        ))}
      </div>
    );
  }

  const renderRow = (lead: SourcingLead) => (
    <tr key={lead.id} className="hover:bg-brand-hover/35">
      <td className="px-4 py-3.5">
        <span className="font-semibold text-brand-platinum">{lead.first_name} {lead.last_name}</span>
        {lead.status === "possible_duplicate" && lead.duplicate_of_candidate_id && (
          <p className="mt-1 text-[10.45px]">
            <Link
              href={`/kandidaten/${lead.duplicate_of_candidate_id}`}
              className="text-brand-warning hover:underline"
            >
              Möglicherweise bereits als Kandidat vorhanden – Profil öffnen
            </Link>
          </p>
        )}
      </td>
      <td className="px-4 py-3.5 text-brand-soft">
        {lead.source_url ? (
          <a
            href={lead.source_url}
            target="_blank"
            rel="noopener noreferrer"
            className="inline-flex items-center gap-1 hover:text-white hover:underline"
          >
            {SOURCE_LABELS[lead.source_type]}
            <ExternalLink size={12} />
          </a>
        ) : (
          SOURCE_LABELS[lead.source_type]
        )}
        {lead.notes_text && (
          <p
            title={lead.notes_text}
            className="mt-1 line-clamp-3 max-w-xs whitespace-pre-line text-[10.45px] text-brand-muted"
          >
            {lead.notes_text}
          </p>
        )}
      </td>
      <td className="px-4 py-3.5 text-brand-soft">{lead.current_employer ?? "—"}</td>
      <td className="px-4 py-3.5 text-brand-soft">
        {[lead.postal_code, lead.city].filter(Boolean).join(" ") || "—"}
      </td>
      <td className="px-4 py-3.5 text-xs text-brand-muted">{formatDate(lead.found_at)}</td>
      <td className="px-4 py-3.5">
        <div className="flex gap-2">
          <Button
            size="sm"
            variant="dark"
            disabled={busyLeadId === lead.id}
            onClick={() => void handleAction(lead, "approve")}
          >
            Übernehmen
          </Button>
          <Button
            size="sm"
            variant="outline"
            disabled={busyLeadId === lead.id}
            onClick={() => void handleAction(lead, "reject")}
          >
            Verwerfen
          </Button>
        </div>
      </td>
    </tr>
  );

  const headers = ["Name", "Quelle", "Arbeitgeber laut Quelle", "PLZ / Ort", "Gefunden", "Aktion"];

  // Mobile (<lg): Karten statt der 6-spaltigen Tabelle, siehe
  // candidates-table.tsx fuer denselben Fix + Begruendung (Nutzer-Feedback
  // "mobile Version nicht passend").
  const renderCard = (lead: SourcingLead) => (
    <div key={lead.id} className="rounded-lg border border-white/10 bg-brand-panel p-3">
      <p className="font-semibold text-brand-platinum">{lead.first_name} {lead.last_name}</p>
      {lead.status === "possible_duplicate" && lead.duplicate_of_candidate_id && (
        <p className="mt-1 text-[10.45px]">
          <Link href={`/kandidaten/${lead.duplicate_of_candidate_id}`} className="text-brand-warning hover:underline">
            Möglicherweise bereits als Kandidat vorhanden – Profil öffnen
          </Link>
        </p>
      )}
      <p className="mt-1 text-xs text-brand-soft">
        {lead.source_url ? (
          <a href={lead.source_url} target="_blank" rel="noopener noreferrer" className="inline-flex items-center gap-1 hover:text-white hover:underline">
            {SOURCE_LABELS[lead.source_type]}<ExternalLink size={12} />
          </a>
        ) : (
          SOURCE_LABELS[lead.source_type]
        )}
        {" · "}{lead.current_employer ?? "Arbeitgeber offen"}
      </p>
      <p className="mt-0.5 text-[10.45px] text-brand-muted">
        {[lead.postal_code, lead.city].filter(Boolean).join(" ") || "PLZ/Ort offen"} · Gefunden {formatDate(lead.found_at)}
      </p>
      {lead.notes_text && (
        <p className="mt-1.5 line-clamp-3 whitespace-pre-line text-[10.45px] text-brand-muted">{lead.notes_text}</p>
      )}
      <div className="mt-2.5 flex gap-2">
        <Button size="sm" variant="dark" disabled={busyLeadId === lead.id} onClick={() => void handleAction(lead, "approve")}>
          Übernehmen
        </Button>
        <Button size="sm" variant="outline" disabled={busyLeadId === lead.id} onClick={() => void handleAction(lead, "reject")}>
          Verwerfen
        </Button>
      </div>
    </div>
  );

  const renderLeadList = (items: SourcingLead[]) => (
    <>
      <div className="space-y-2 lg:hidden">{items.map(renderCard)}</div>
      <div className="hidden lg:block"><DataTable headers={headers}>{items.map(renderRow)}</DataTable></div>
    </>
  );

  return (
    <>
      <ErrorBanner message={actionError} className="mb-3" />
      {duplicateLeads.length > 0 && (
        <div className="mb-6">
          <div className="mb-2 flex items-center gap-2">
            <Badge tone="amber">Mögliche Duplikate</Badge>
            <span className="text-xs text-brand-muted">
              Fuzzy-Namensabgleich hat einen bestehenden Kandidaten gefunden – bitte vor Übernahme prüfen
              (z.B. Arbeitgeberwechsel eines Bestandskandidaten).
            </span>
          </div>
          {renderLeadList(duplicateLeads)}
        </div>
      )}
      {renderLeadList(pendingLeads)}
      {pendingLeads.length === 0 && duplicateLeads.length === 0 && (
        <div className="mt-6 flex flex-col items-center gap-2 rounded-lg border border-white/10 bg-brand-surface p-8 text-center">
          <UserRoundSearch size={24} className="text-brand-muted" />
          <p className="text-sm text-brand-soft">Keine offenen Leads.</p>
          <p className="text-xs text-brand-muted">
            Starte einen Sourcing-Lauf, um neue Kandidaten-Vorschläge aus öffentlichen
            Berufsregistern zu sammeln.
          </p>
        </div>
      )}
      <p className="mt-3 text-xs text-brand-gray">
        {pendingLeads.length + duplicateLeads.length} offene Leads
      </p>
    </>
  );
}
