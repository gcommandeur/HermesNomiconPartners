"use client";

// NOMICON: Überlassung - Disposition: Kennzahlen, Erlaubnis, Fristen-Radar, Stundenzettel-Eingang,
// Bench ("frei seit") und Einsatz-Board.
import Link from "next/link";
import { AlertTriangle, ClipboardList, FileCheck2, HardHat, Hourglass, UserRoundX } from "lucide-react";
import { Card, CardContent } from "@/components/ui/card";
import { ErrorBanner } from "@/components/crm/error-banner";
import { useStaffingDisposition, useStaffingOverview } from "@/lib/api/staffing-hooks";
import { formatDate } from "@/lib/utils";
import { DeadlineRow } from "./staffing-overview-view";
import { StaffingAssignmentBoard } from "./staffing-assignment-board";
import { EmptyHint, LEGAL_NOTICE, LoadError, LoadingRows } from "./staffing-ui";

function Stat({ icon: Icon, label, value, hint, warn }: { icon: typeof HardHat; label: string; value: React.ReactNode; hint?: string; warn?: boolean }) {
  return (
    <Card>
      <CardContent className="flex items-start gap-3">
        <Icon size={18} className={warn ? "mt-0.5 text-brand-warning" : "mt-0.5 text-brand-silver"} aria-hidden />
        <div className="min-w-0">
          <p className="text-[9.5px] font-semibold uppercase tracking-wider text-brand-gray">{label}</p>
          <p className="mt-1 text-2xl font-semibold tracking-[-.02em]">{value}</p>
          {hint && <p className="mt-0.5 text-xs text-brand-muted">{hint}</p>}
        </div>
      </CardContent>
    </Card>
  );
}

export function StaffingDispositionView() {
  const { data, error, isLoading, mutate } = useStaffingDisposition();
  const { data: overview } = useStaffingOverview();
  if (error) return <LoadError onRetry={() => void mutate()} />;
  if (isLoading || !data) return <LoadingRows />;
  const d = data.data;
  const license = d.license;
  const licenseValue = !license.valid ? "Fehlt" : license.valid_to ? `bis ${formatDate(license.valid_to)}` : "Unbefristet";
  const deadlines = overview?.data.deadlines ?? [];
  return (
    <div className="space-y-8">
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-5">
        <Stat icon={HardHat} label="Aktive Einsätze" value={d.active_assignments} hint={`${d.planned_assignments} geplant`} />
        <Stat icon={UserRoundX} label="Bench" value={d.bench_count} hint="ohne aktiven oder geplanten Einsatz" warn={d.bench_count > 0} />
        <Stat icon={ClipboardList} label="Offene Checklisten" value={d.open_checklist_assignments} hint="geplante oder aktive Einsätze" />
        <Stat icon={Hourglass} label="Stundenzettel-Rückstand" value={d.timesheet_backlog} hint={`${d.inbox.open_overdue} überfällig · ${d.inbox.approved_unbilled} nicht abgerechnet`} warn={d.timesheet_backlog > 0} />
        <Stat icon={FileCheck2} label="AÜG-Erlaubnis" value={<span className="text-xl">{licenseValue}</span>} hint={license.valid ? undefined : "Ohne gültige Erlaubnis kann kein Einsatz aktiviert werden."} />
      </div>
      {!license.valid && (
        <ErrorBanner message="Es ist keine gültige Erlaubnis zur Arbeitnehmerüberlassung hinterlegt. Ohne sie kann kein Einsatz aktiviert werden. Bitte unter „Compliance“ eintragen (nur Admins)." />
      )}

      <section>
        <h2 className="mb-3 font-semibold">Einsatz-Board</h2>
        <StaffingAssignmentBoard />
      </section>

      <div className="grid grid-cols-1 gap-6 xl:grid-cols-2">
        <section>
          <div className="mb-3 flex items-center gap-2">
            <AlertTriangle size={15} className="text-brand-silver" aria-hidden />
            <h2 className="font-semibold">Fristen-Radar</h2>
          </div>
          {deadlines.length === 0 ? <EmptyHint>Keine laufenden oder fortsetzbaren Überlassungen.</EmptyHint> : (
            <div className="space-y-2">
              {deadlines.slice(0, 8).map((deadline) => <DeadlineRow key={`${deadline.worker_id}:${deadline.client_company_id}`} deadline={deadline} />)}
            </div>
          )}
          <p className="mt-3 text-xs text-brand-muted">{LEGAL_NOTICE}</p>
        </section>

        <section>
          <h2 className="mb-3 font-semibold">Stundenzettel-Eingang</h2>
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
            {[
              ["Offen", d.inbox.open],
              ["Beim Kunden", d.inbox.submitted],
              ["Freigegeben, nicht abgerechnet", d.inbox.approved_unbilled],
              ["Abgelehnt", d.inbox.rejected],
            ].map(([label, value]) => (
              <Card key={String(label)}><CardContent className="py-3"><p className="text-[9.5px] uppercase tracking-wider text-brand-gray">{label}</p><p className="mt-1 text-xl font-semibold">{value}</p></CardContent></Card>
            ))}
          </div>
          <h2 className="mb-3 mt-6 font-semibold">Bench</h2>
          {d.bench.length === 0 ? <EmptyHint>Alle aktiven Leiharbeitnehmer sind eingeplant.</EmptyHint> : (
            <ul className="space-y-2">
              {d.bench.map((w) => (
                <li key={w.worker_id}>
                  <Link href={`/ueberlassung/leiharbeitnehmer/${w.worker_id}`} className="flex items-center justify-between gap-3 rounded-lg border border-white/10 p-3 transition-colors hover:bg-brand-hover/40">
                    <span className="min-w-0 truncate text-sm font-medium">{w.worker_name}{w.pay_grade ? <span className="text-brand-muted"> · {w.pay_grade}</span> : null}</span>
                    <span className="shrink-0 text-xs text-brand-muted">{w.free_since ? `frei seit ${formatDate(w.free_since)} (${w.days_free} Tage)` : "frei seit unbekannt"}</span>
                  </Link>
                </li>
              ))}
            </ul>
          )}
        </section>
      </div>
    </div>
  );
}
