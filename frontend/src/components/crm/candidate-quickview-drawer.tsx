"use client";

import Link from "next/link";
import { ArrowUpRight, Ghost, Mail, MapPin, Phone, X } from "lucide-react";
import type { Candidate } from "@/lib/api/types";
import { StatusPill } from "./status-pill";
import { Badge } from "@/components/ui/badge";
import { formatDate, rolleLabel } from "@/lib/utils";

/** Seitliches Kurzprofil-Panel (Bullhorn-artiger "Split View"): öffnet den
 * Kandidaten neben der Prozesse-Liste, ohne die Seite zu verlassen. Nutzt die
 * bereits geladenen Kandidatendaten - keine zusätzliche API-Anfrage. */
export function CandidateQuickViewDrawer({
  candidate,
  onClose,
  backTo = "prozesse",
}: {
  candidate: Candidate | null;
  onClose: () => void;
  /** Wert fuer den `from`-Query-Param der Detailseite (steuert dort den
   * kontextabhaengigen Zurueck-Link, siehe app/kandidaten/[id]/page.tsx) -
   * Default "prozesse" haelt den bestehenden Aufrufer (submission-views.tsx)
   * unveraendert, candidates-table.tsx uebergibt "kandidaten". */
  backTo?: string;
}) {
  if (!candidate) return null;

  return (
    <div className="fixed inset-0 z-50 flex justify-end">
      <div className="absolute inset-0 bg-black/50" onClick={onClose} />
      <aside className="relative flex h-full w-full max-w-md flex-col overflow-y-auto border-l border-white/10 bg-[#0D1B2E] p-5 shadow-[-12px_0_30px_rgba(0,0,0,.35)]">
        <div className="mb-4 flex items-start justify-between gap-2">
          <div>
            <div className="mb-2 flex items-center gap-2">
              <StatusPill status={candidate.status} />
              {candidate.has_ghosting_history && <Badge tone="red" className="gap-1"><Ghost size={11} />Ghosting</Badge>}
              <span className="text-[11px] text-[#8b9196]">Aktualisiert {formatDate(candidate.updated_at)}</span>
            </div>
            <h2 className="text-xl font-semibold tracking-[-.03em]">{candidate.first_name} {candidate.last_name}</h2>
            <p className="mt-1 text-sm text-[#CBD5E1]">{candidate.job_title ?? "Rolle offen"} · {candidate.city ?? candidate.postal_code ?? "Region offen"}</p>
            {candidate.rollen && candidate.rollen.length > 0 && (
              <div className="mt-2 flex flex-wrap gap-1.5">
                {candidate.rollen.map((rolle) => <Badge key={rolle} tone="blue">{rolleLabel(rolle)}</Badge>)}
              </div>
            )}
          </div>
          <button
            type="button"
            onClick={onClose}
            className="shrink-0 rounded p-1.5 text-[#94A3B8] hover:bg-white/5 hover:text-white"
            title="Schließen"
          >
            <X size={16} />
          </button>
        </div>

        <div className="space-y-1.5 border-t border-white/10 pt-4 text-xs text-[#CBD5E1]">
          {candidate.email && <p className="flex items-center gap-1.5"><Mail size={13} />{candidate.email}</p>}
          {candidate.phone && <p className="flex items-center gap-1.5"><Phone size={13} />{candidate.phone}</p>}
          {(candidate.city || candidate.postal_code) && (
            <p className="flex items-center gap-1.5"><MapPin size={13} />{[candidate.postal_code, candidate.city].filter(Boolean).join(" ")}</p>
          )}
        </div>

        <div className="mt-4 grid grid-cols-1 gap-3 border-t border-white/10 pt-4 text-xs sm:grid-cols-2">
          <div>
            <p className="text-[10px] uppercase tracking-wider text-[#94A3B8]">Gehaltsrahmen</p>
            <p className="mt-1 text-[#F8FAFC]">{candidate.salary_expectation ?? "offen"}</p>
          </div>
          <div>
            <p className="text-[10px] uppercase tracking-wider text-[#94A3B8]">Verfügbarkeit</p>
            <p className="mt-1 text-[#F8FAFC]">{candidate.notice_period ?? "offen"}</p>
          </div>
        </div>

        {(candidate.short_profile || candidate.summary) && (
          <div className="mt-4 border-t border-white/10 pt-4">
            <p className="mb-1 text-[10px] uppercase tracking-wider text-[#94A3B8]">Kurzprofil</p>
            <p className="whitespace-pre-line text-xs text-[#CBD5E1]">{candidate.short_profile ?? candidate.summary}</p>
          </div>
        )}

        <div className="mt-auto flex justify-end border-t border-white/10 pt-4">
          <Link
            href={`/kandidaten/${candidate.id}?from=${backTo}`}
            className="inline-flex items-center gap-1.5 rounded-md border border-[#1F5FA8]/40 bg-[#153A66]/45 px-3 py-1.5 text-xs text-[#c5dcfa] hover:bg-[#153A66]/70"
          >
            Vollständiges Profil öffnen <ArrowUpRight size={13} />
          </Link>
        </div>
      </aside>
    </div>
  );
}
