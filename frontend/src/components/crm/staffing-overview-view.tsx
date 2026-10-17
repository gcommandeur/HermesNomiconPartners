"use client";

// NOMICON: Überlassung - Übersicht: aktive Einsätze, Fristen nach Dringlichkeit, Erlaubnis, offene Checklisten.
import Link from "next/link";
import { AlertTriangle, ClipboardList, FileCheck2, HardHat } from "lucide-react";
import { Card, CardContent } from "@/components/ui/card";
import { ErrorBanner } from "@/components/crm/error-banner";
import { useStaffingOverview } from "@/lib/api/staffing-hooks";
import { formatDate } from "@/lib/utils";
import { formatPriorDays } from "@/lib/staffing-deadline-text";
import { formatElapsed, formatRemaining, type StaffingPairDeadline } from "@/lib/api/staffing";
import { EmptyHint, LEGAL_NOTICE, LoadError, LoadingRows, TrafficBadge } from "./staffing-ui";

function Stat({ icon: Icon, label, value, hint }: { icon: typeof HardHat; label: string; value: React.ReactNode; hint?: string }) {
  return (
    <Card>
      <CardContent className="flex items-start gap-3">
        <Icon size={18} className="mt-0.5 text-brand-silver" aria-hidden />
        <div className="min-w-0">
          <p className="text-[9.5px] font-semibold uppercase tracking-wider text-brand-gray">{label}</p>
          <p className="mt-1 text-2xl font-semibold tracking-[-.02em]">{value}</p>
          {hint && <p className="mt-0.5 text-xs text-brand-muted">{hint}</p>}
        </div>
      </CardContent>
    </Card>
  );
}

export function DeadlineRow({ deadline }: { deadline: StaffingPairDeadline }) {
  return (
    <Link
      href={`/ueberlassung/leiharbeitnehmer/${deadline.worker_id}`}
      className="flex flex-col gap-2 rounded-lg border border-white/10 p-3 transition-colors hover:bg-brand-hover/40 sm:flex-row sm:items-center sm:justify-between"
    >
      <div className="min-w-0">
        <p className="truncate text-sm font-medium">{deadline.worker_name}</p>
        <p className="truncate text-xs text-brand-muted">
          {deadline.client_name} · {formatElapsed(deadline)}
          {deadline.prior_days > 0 ? ` (${formatPriorDays(deadline.prior_days)})` : ""} · Höchstdauer bis {formatDate(deadline.max_end_date)}
        </p>
      </div>
      <div className="flex flex-wrap items-center gap-2">
        {deadline.equal_pay_reached && <span className="text-xs text-brand-muted">Equal Pay seit {formatDate(deadline.equal_pay_from)}</span>}
        <TrafficBadge traffic={deadline.traffic} label={formatRemaining(deadline.days_remaining)} />
      </div>
    </Link>
  );
}

export function StaffingOverviewView() {
  const { data, error, isLoading, mutate } = useStaffingOverview();
  if (error) return <LoadError onRetry={() => void mutate()} />;
  if (isLoading || !data) return <LoadingRows />;
  const overview = data.data;
  const license = overview.license;
  const licenseValue = !license.valid ? "Fehlt" : license.valid_to ? `bis ${formatDate(license.valid_to)}` : "Unbefristet";
  return (
    <div className="space-y-6">
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <Stat icon={HardHat} label="Aktive Einsätze" value={overview.active_assignments} hint={`${overview.planned_assignments} geplant`} />
        <Stat icon={ClipboardList} label="Offene Checklisten" value={overview.open_checklist_assignments} hint="geplante oder aktive Einsätze" />
        <Stat
          icon={FileCheck2}
          label="AÜG-Erlaubnis"
          value={<span className="text-xl">{licenseValue}</span>}
          hint={license.valid ? undefined : "Ohne gültige Erlaubnis kann kein Einsatz aktiviert werden."}
        />
        <Stat
          icon={AlertTriangle}
          label="Dringende Fristen"
          value={overview.deadlines.filter((d) => d.traffic !== "green").length}
          hint="gelb oder rot"
        />
      </div>
      {!license.valid && (
        <ErrorBanner
          message="Es ist keine gültige Erlaubnis zur Arbeitnehmerüberlassung hinterlegt. Ohne sie kann kein Einsatz aktiviert werden. Bitte unter „Compliance“ eintragen (nur Admins)."
        />
      )}
      <section>
        <div className="mb-3 flex items-baseline justify-between gap-3">
          <h2 className="font-semibold">Fristen nach Dringlichkeit</h2>
          <TrafficLegend />
        </div>
        {overview.deadlines.length === 0 ? (
          <EmptyHint>Keine laufenden oder fortsetzbaren Überlassungen.</EmptyHint>
        ) : (
          <div className="space-y-2">
            {overview.deadlines.map((deadline) => (
              <DeadlineRow key={`${deadline.worker_id}:${deadline.client_company_id}`} deadline={deadline} />
            ))}
          </div>
        )}
        <p className="mt-3 text-xs text-brand-muted">{LEGAL_NOTICE}</p>
      </section>
    </div>
  );
}

function TrafficLegend() {
  return (
    <div className="flex flex-wrap items-center gap-2">
      <TrafficBadge traffic="green" />
      <TrafficBadge traffic="yellow" label="unter 60 Tagen" />
      <TrafficBadge traffic="red" label="unter 30 Tagen / überschritten" />
    </div>
  );
}
