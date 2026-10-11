"use client";

// NOMICON: Arbeitnehmerüberlassung - gemeinsame Bausteine der Seiten unter /ueberlassung.
import Link from "next/link";
import { usePathname } from "next/navigation";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { ErrorState } from "@/components/crm/error-state";
import { cn } from "@/lib/utils";
import {
  ASSIGNMENT_STATUS_LABELS,
  TRAFFIC_LABELS,
  WORKER_STATUS_LABELS,
  formatElapsed,
  formatRemaining,
  type StaffingAssignmentStatus,
  type StaffingDeadline,
  type StaffingWorkerStatus,
  type Traffic,
} from "@/lib/api/staffing";
import { formatDate } from "@/lib/utils";

export const LEGAL_NOTICE =
  "Hinweis: Die Fristen beruhen auf einstellbaren Annahmen und sind kein Rechtsrat. Bitte mit Fachanwalt oder Verband bestätigen; Tarifverträge können abweichen.";

const TRAFFIC_TONE = { green: "green", yellow: "amber", red: "red" } as const;

export function TrafficBadge({ traffic, label }: { traffic: Traffic; label?: string }) {
  return <Badge tone={TRAFFIC_TONE[traffic]}>{label ?? TRAFFIC_LABELS[traffic]}</Badge>;
}

export function AssignmentStatusBadge({ status }: { status: StaffingAssignmentStatus }) {
  const tone = status === "active" ? "green" : status === "planned" ? "blue" : status === "aborted" ? "red" : "gray";
  return <Badge tone={tone}>{ASSIGNMENT_STATUS_LABELS[status]}</Badge>;
}

export function WorkerStatusBadge({ status }: { status: StaffingWorkerStatus }) {
  const tone = status === "active" ? "green" : status === "applicant" ? "blue" : status === "left" ? "gray" : "amber";
  return <Badge tone={tone}>{WORKER_STATUS_LABELS[status]}</Badge>;
}

const SUB_NAV = [
  { href: "/ueberlassung", label: "Übersicht", exact: true },
  { href: "/ueberlassung/einsaetze", label: "Einsätze", exact: false },
  { href: "/ueberlassung/leiharbeitnehmer", label: "Leiharbeitnehmer", exact: false },
  { href: "/ueberlassung/abrechnung", label: "Abrechnung", exact: false },
  { href: "/ueberlassung/compliance", label: "Compliance", exact: false },
];

/** Reiter-Leiste oben auf allen Überlassungs-Seiten (auf dem Handy seitlich scrollbar). */
export function StaffingSubNav() {
  const pathname = usePathname();
  return (
    <nav aria-label="Überlassung" className="scrollbar-subtle mb-5 flex gap-1 overflow-x-auto border-b border-white/10">
      {SUB_NAV.map((item) => {
        const active = item.exact ? pathname === item.href : pathname.startsWith(item.href);
        return (
          <Link
            key={item.href}
            href={item.href}
            className={cn(
              "whitespace-nowrap border-b-2 px-3 py-2.5 text-sm font-medium transition-colors",
              active ? "border-brand-platinum text-brand-text" : "border-transparent text-brand-muted hover:text-brand-text",
            )}
          >
            {item.label}
          </Link>
        );
      })}
    </nav>
  );
}

export function LoadingRows({ rows = 4 }: { rows?: number }) {
  return (
    <div className="space-y-2" aria-busy="true" aria-label="Wird geladen">
      {Array.from({ length: rows }, (_, index) => (
        <div key={index} className="h-14 animate-pulse rounded-lg bg-brand-surface" />
      ))}
    </div>
  );
}

export function EmptyHint({ children }: { children: React.ReactNode }) {
  return <p className="rounded-lg border border-dashed border-white/10 p-6 text-center text-sm text-brand-dim">{children}</p>;
}

/** Fehlerzustand (Backend nicht erreichbar) mit Neu-Laden-Knopf. */
export function LoadError({ onRetry }: { onRetry: () => void }) {
  return <ErrorState onRetry={onRetry} />;
}

export function Fact({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div>
      <p className="text-[9.5px] font-semibold uppercase tracking-wider text-brand-gray">{label}</p>
      <div className="mt-1.5 text-sm">{children || "—"}</div>
    </div>
  );
}

/** Fortschrittsbalken der Überlassungsdauer samt Equal-Pay-Marke und Ampel. */
export function DeadlineMeter({ deadline, maxMonths = 18 }: { deadline: StaffingDeadline; maxMonths?: number }) {
  if (!deadline.has_chain) {
    return <p className="text-sm text-brand-muted">Kein laufender Zähler – ein neuer Einsatz beginnt bei null.</p>;
  }
  const totalDays = Math.max(1, deadline.counted_days + Math.max(0, deadline.days_remaining ?? 0));
  const percent = Math.min(100, Math.round((deadline.counted_days / totalDays) * 100));
  const bar = deadline.traffic === "red" ? "bg-brand-danger" : deadline.traffic === "yellow" ? "bg-brand-warning" : "bg-brand-success";
  return (
    <div>
      <div className="flex flex-wrap items-center justify-between gap-2">
        <p className="text-sm font-medium">
          {formatElapsed(deadline)} <span className="text-brand-muted">von {maxMonths} Monaten</span>
        </p>
        <TrafficBadge traffic={deadline.traffic} label={formatRemaining(deadline.days_remaining)} />
      </div>
      <div
        className="mt-3 h-2 overflow-hidden rounded-full bg-brand-surface"
        role="progressbar"
        aria-valuemin={0}
        aria-valuemax={100}
        aria-valuenow={percent}
        aria-label="Bisherige Überlassungsdauer"
      >
        <div className={cn("h-full rounded-full transition-all", bar)} style={{ width: `${percent}%` }} />
      </div>
      <dl className="mt-3 grid grid-cols-1 gap-x-6 gap-y-1 text-xs text-brand-soft sm:grid-cols-3">
        <div><dt className="text-brand-muted">Zähler seit</dt><dd>{formatDate(deadline.chain_start)}</dd></div>
        <div>
          <dt className="text-brand-muted">Equal Pay</dt>
          <dd>{deadline.equal_pay_reached ? `gilt seit ${formatDate(deadline.equal_pay_from)}` : `ab ${formatDate(deadline.equal_pay_from)}`}</dd>
        </div>
        <div><dt className="text-brand-muted">Höchstdauer bis</dt><dd>{formatDate(deadline.max_end_date)}</dd></div>
      </dl>
    </div>
  );
}

export function PrimaryLink({ href, children }: { href: string; children: React.ReactNode }) {
  return (
    <Button asChild size="sm" variant="outline">
      <Link href={href}>{children}</Link>
    </Button>
  );
}

export const labelClass = "mb-1 block text-xs text-brand-muted";
export const selectClass =
  "h-10 w-full rounded-md border border-white/10 bg-brand-surface px-3 text-sm text-brand-text outline-none focus:border-brand-accent";
