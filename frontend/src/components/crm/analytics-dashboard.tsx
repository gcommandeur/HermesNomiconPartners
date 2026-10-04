"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { ChevronDown } from "lucide-react";
import { Card, CardContent } from "@/components/ui/card";
import { DemoNotice } from "@/components/crm/demo-notice";
import { ErrorState } from "@/components/crm/error-state";
import { useCockpitCache, useScopeUsersCache } from "@/lib/api/hooks";
import { PITCH_LABEL, STAGE_LABELS } from "@/lib/stage-labels";
import { formatCurrency } from "@/lib/utils";

const NO_DATA = "Keine Daten erfasst";

/** Kleines eigenes Mehrfach-Auswahl-Dropdown (kein Popover/Checkbox-
 * Primitive im Projekt vorhanden) - Nutzer-Vorgabe: "oben koennen mehrere
 * user angewaehlt werden... standardauswahl sind alle user". `null` bedeutet
 * "alle ausgewaehlt" (Default-/Normalzustand, kein Filter aktiv). */
function UserFilter({
  users,
  selected,
  onChange,
}: {
  users: { id: string; label: string }[];
  selected: Set<string> | null;
  onChange: (next: Set<string> | null) => void;
}) {
  const [open, setOpen] = useState(false);
  const containerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    function handleClickOutside(event: MouseEvent) {
      if (containerRef.current && !containerRef.current.contains(event.target as Node)) {
        setOpen(false);
      }
    }
    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, []);

  const allSelected = selected === null;
  const selectedCount = allSelected ? users.length : selected.size;
  const summary =
    users.length === 0
      ? "Nutzer…"
      : allSelected
        ? "Alle Nutzer"
        : selectedCount === 0
          ? "Keine Nutzer"
          : `${selectedCount} von ${users.length} Nutzern`;

  function toggle(id: string) {
    const current = selected ?? new Set(users.map((u) => u.id));
    const next = new Set(current);
    if (next.has(id)) next.delete(id);
    else next.add(id);
    // Sind wieder alle ausgewaehlt, zurueck auf "kein Filter" (null) statt
    // einer expliziten Liste mit allen IDs - vermeidet einen unnoetig langen
    // Query-String und haelt den "Alle Nutzer"-Normalzustand kanonisch.
    onChange(next.size === users.length ? null : next);
  }

  return (
    <div className="relative" ref={containerRef}>
      <button
        type="button"
        className="flex h-9 items-center gap-2 rounded-md border border-white/10 bg-brand-surface px-3 text-xs text-brand-soft hover:border-white/20"
        onClick={() => setOpen((o) => !o)}
      >
        {summary}
        <ChevronDown size={13} />
      </button>
      {open && (
        <div className="absolute right-0 z-10 mt-1 w-56 rounded-md border border-white/10 bg-brand-surface p-2 shadow-lg">
          <button
            type="button"
            className="mb-1 w-full rounded px-2 py-1.5 text-left text-xs text-brand-muted hover:bg-white/5"
            onClick={() => onChange(null)}
          >
            Alle auswählen
          </button>
          <div className="max-h-64 space-y-0.5 overflow-y-auto">
            {users.map((user) => (
              <label
                key={user.id}
                className="flex cursor-pointer items-center gap-2 rounded px-2 py-1.5 text-xs text-brand-soft hover:bg-white/5"
              >
                <input
                  type="checkbox"
                  checked={allSelected || selected.has(user.id)}
                  onChange={() => toggle(user.id)}
                />
                {user.label}
              </label>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

/** Client-seitige Analytics-Seite (vorher Server Component) - noetig fuer
 * den neuen Mehrfach-Nutzerfilter, der die Cockpit-Daten je Auswahl neu
 * abfragt (siehe useCockpitCache). */
export function AnalyticsDashboard() {
  const [selectedOwnerIds, setSelectedOwnerIds] = useState<Set<string> | null>(null);
  const { data: usersResult } = useScopeUsersCache();
  const users = useMemo(
    () => (usersResult?.data ?? []).map((u) => ({ id: u.id, label: u.display_name || u.email })),
    [usersResult],
  );
  const ownerUserIds = selectedOwnerIds ? Array.from(selectedOwnerIds) : undefined;
  const { data, error, mutate } = useCockpitCache("week", ownerUserIds);

  if (error) {
    return <ErrorState onRetry={() => void mutate()} />;
  }
  if (!data) {
    return <div className="h-40 animate-pulse rounded-lg border border-white/10 bg-brand-surface/50" />;
  }

  const { kpis, rates, recruiting_kpis: recruitingKpis } = data.data;
  const recruitingKpiCards: [string, string][] = [
    ["Time-to-Fill ab Prozessanlage (Median)", recruitingKpis.time_to_fill_days !== null ? `${recruitingKpis.time_to_fill_days} Tage` : NO_DATA],
    ["Time-to-Interview (Median)", recruitingKpis.time_to_interview_days !== null ? `${recruitingKpis.time_to_interview_days} Tage` : NO_DATA],
    ["Ø Fee pro Placement", recruitingKpis.average_fee_per_placement !== null ? formatCurrency(recruitingKpis.average_fee_per_placement) : NO_DATA],
  ];
  // Konsolidierte 7-Stufen-Pipeline (Nutzer-Vorgabe: "die 7 Stufen sind
  // 1. Pitch/InMail, 2. Quali Call, 3. CV IN, 4. CV OUT, 5. Interview,
  // 6. Offer und 7. Placement") - einfache Volumen-Balken statt der
  // vorherigen, staerker gemischten Kennzahlenliste (Nutzer-Vorgabe: "einfach
  // das volumen in balken anzeigen"). Alle sechs Stufen NACH Pitch nutzen die
  // "erreicht"-Pipeline-Zahl (Statuswechsel-Transition), dieselbe Semantik
  // wie die Prozess-Timeline auf der Kandidatendetailseite.
  const funnel: [string, number][] = [
    [PITCH_LABEL, kpis.pitches],
    [STAGE_LABELS.qualification_call, kpis.qualification_calls],
    [STAGE_LABELS.cv_in, kpis.cv_available],
    [STAGE_LABELS.cv_out, kpis.cv_outs_reached_count],
    [STAGE_LABELS.interview, kpis.interviews],
    [STAGE_LABELS.offer, kpis.offer_stage_reached_count],
    [STAGE_LABELS.placement, kpis.placement_stage_reached_count],
  ];
  const maxFunnelValue = Math.max(1, ...funnel.map(([, value]) => value));
  // 6 Uebergaenge zwischen den 7 Stufen - Prozente bleiben in dieser Ansicht
  // erhalten (Nutzer-Vorgabe: "prozente koennen bleiben in der ansicht").
  const conversions: [string, number | string][] = [
    [`${PITCH_LABEL} → ${STAGE_LABELS.qualification_call}`, rates.pitch_to_qualification_call_rate],
    [`${STAGE_LABELS.qualification_call} → ${STAGE_LABELS.cv_in}`, kpis.qualification_calls ? Math.round(kpis.cv_available / kpis.qualification_calls * 1000) / 10 : NO_DATA],
    [`${STAGE_LABELS.cv_in} → ${STAGE_LABELS.cv_out}`, kpis.cv_available ? Math.round(kpis.cv_outs_reached_count / kpis.cv_available * 1000) / 10 : NO_DATA],
    [`${STAGE_LABELS.cv_out} → ${STAGE_LABELS.interview}`, rates.submission_to_interview],
    [`${STAGE_LABELS.interview} → ${STAGE_LABELS.offer}`, rates.interview_to_offer],
    [`${STAGE_LABELS.offer} → ${STAGE_LABELS.placement}`, rates.offer_to_placement],
  ];

  return (
    <>
      {/* Mitarbeiter sehen nur sich selbst - dort waere ein Filter sinnlos. */}
      {users.length > 1 && (
        <div className="mb-5 flex justify-end">
          <UserFilter users={users} selected={selectedOwnerIds} onChange={setSelectedOwnerIds} />
        </div>
      )}
      <DemoNotice source={data.source} error={data.error} />
      {/* Ueber den gesamten historischen Bestand berechnet (nicht auf den
       * Cockpit-Zeitraum begrenzt), siehe Backend CockpitService::
       * _recruiting_kpis - ein Median ueber nur eine Woche/einen Monat haette
       * zu wenige Datenpunkte, um aussagekraeftig zu sein. */}
      <div className="mb-5 grid grid-cols-1 gap-3 sm:grid-cols-3">
        {recruitingKpiCards.map(([label, value]) => (
          <Card key={label}><CardContent className="p-4"><p className="text-[11px] text-brand-muted">{label}</p><p className="mt-2 text-xl font-semibold">{value}</p></CardContent></Card>
        ))}
      </div>
      <div className="grid grid-cols-1 gap-5 xl:grid-cols-[1.2fr_.8fr]">
        <Card>
          <CardContent>
            <h2 className="font-semibold">Recruiting Funnel</h2>
            <div className="mt-5 space-y-2">
              {funnel.map(([label, value]) => (
                <div key={label} className="flex items-center gap-3">
                  <span className="w-28 shrink-0 text-xs text-brand-soft">{label}</span>
                  <div className="h-8 flex-1 overflow-hidden rounded-md bg-brand-sidebar">
                    <div
                      className="flex h-full items-center justify-end rounded-md bg-gradient-to-r from-brand-accent-strong to-brand-accent-light px-2 text-xs font-semibold text-white"
                      style={{ width: `${Math.max(6, (value / maxFunnelValue) * 100)}%` }}
                    >
                      {value}
                    </div>
                  </div>
                </div>
              ))}
            </div>
          </CardContent>
        </Card>
        <Card><CardContent><h2 className="font-semibold">Conversion Rates</h2><div className="mt-5 divide-y divide-white/10">{conversions.map(([label,value]) => <div key={String(label)} className="py-3"><div className="flex justify-between text-xs"><span className="text-brand-soft">{label}</span><strong>{typeof value === "string" ? value : `${value} %`}</strong></div><div className="mt-2 h-1.5 rounded-full bg-brand-sidebar"><div className="h-full rounded-full bg-gradient-to-r from-brand-accent-strong to-brand-accent-light" style={{width:`${typeof value === "string" ? 0 : Math.min(value,100)}%`}} /></div></div>)}</div><div className="mt-5 grid grid-cols-2 gap-3"><div className="rounded-lg border p-3"><p className="text-[10px] text-brand-muted">Erwartet</p><p className="mt-2 font-semibold">{formatCurrency(kpis.expected_fees)}</p></div><div className="rounded-lg border p-3"><p className="text-[10px] text-brand-muted">Realisiert</p><p className="mt-2 font-semibold">{formatCurrency(kpis.realized_fees)}</p></div></div></CardContent></Card>
      </div>
    </>
  );
}
