"use client";

// NOMICON: Einsatz-Board der Disposition. Spalten: Anwärter/Onboarding (geplant, Checkliste offen),
// Geplant, Aktiv, Läuft aus (aktiv mit gelber/roter Frist oder Ende in den nächsten Tagen),
// Beendet (letzte 30 Tage). Lohn und Verrechnungssatz zeigt der Server nur Admins.
import { useMemo } from "react";
import Link from "next/link";
import { useCurrentUser } from "@/lib/api/hooks";
import { useStaffingAssignments, useStaffingOverview } from "@/lib/api/staffing-hooks";
import { formatMoney, type StaffingAssignment, type Traffic } from "@/lib/api/staffing";
import { formatDate } from "@/lib/utils";
import { EmptyHint, LoadError, LoadingRows, TrafficBadge } from "./staffing-ui";

type ColumnKey = "onboarding" | "planned" | "active" | "ending" | "ended";

const COLUMNS: { key: ColumnKey; title: string }[] = [
  { key: "onboarding", title: "Anwärter / Onboarding" },
  { key: "planned", title: "Geplant" },
  { key: "active", title: "Aktiv" },
  { key: "ending", title: "Läuft aus" },
  { key: "ended", title: "Beendet" },
];
const ENDING_SOON_DAYS = 30;
const ENDED_VISIBLE_DAYS = 30;

function daysBetween(from: Date, to: Date): number {
  return Math.round((to.getTime() - from.getTime()) / 86_400_000);
}

export function classifyAssignment(a: StaffingAssignment, traffic: Traffic | undefined, today: Date): ColumnKey | null {
  if (a.status === "aborted") return null;
  if (a.status === "ended") {
    const end = a.actual_end_date ?? a.planned_end_date;
    return end && daysBetween(new Date(end), today) <= ENDED_VISIBLE_DAYS ? "ended" : null;
  }
  if (a.status === "planned") return a.checklist_done < a.checklist_total ? "onboarding" : "planned";
  const endsSoon = a.planned_end_date !== null && daysBetween(today, new Date(a.planned_end_date)) <= ENDING_SOON_DAYS;
  return traffic === "yellow" || traffic === "red" || endsSoon ? "ending" : "active";
}

export function StaffingAssignmentBoard() {
  const { data, error, isLoading, mutate } = useStaffingAssignments({});
  const { data: overview } = useStaffingOverview();
  const { data: me } = useCurrentUser();
  const isAdmin = me?.data.is_admin ?? false;
  const columns = useMemo(() => {
    const traffic = new Map<string, Traffic>();
    for (const d of overview?.data.deadlines ?? []) traffic.set(`${d.worker_id}:${d.client_company_id}`, d.traffic);
    const grouped: Record<ColumnKey, { assignment: StaffingAssignment; traffic?: Traffic }[]> = { onboarding: [], planned: [], active: [], ending: [], ended: [] };
    const today = new Date();
    for (const assignment of data?.data ?? []) {
      const pairTraffic = traffic.get(`${assignment.worker_id}:${assignment.client_company_id}`);
      const key = classifyAssignment(assignment, pairTraffic, today);
      if (key) grouped[key].push({ assignment, traffic: pairTraffic });
    }
    return grouped;
  }, [data, overview]);

  if (error) return <LoadError onRetry={() => void mutate()} />;
  if (isLoading || !data) return <LoadingRows />;
  if (data.data.length === 0) return <EmptyHint>Noch keine Einsätze angelegt.</EmptyHint>;

  return (
    <div className="grid grid-cols-1 gap-3 md:grid-cols-2 xl:grid-cols-5">
      {COLUMNS.map((column) => (
        <section key={column.key} aria-label={column.title} className="min-w-0 rounded-xl border border-white/10 bg-brand-surface p-2">
          <header className="flex items-center justify-between px-2 py-2">
            <h3 className="truncate text-xs font-semibold text-brand-text">{column.title}</h3>
            <span className="grid size-5 shrink-0 place-items-center rounded-full border border-white/10 bg-brand-panel text-[9.5px] text-brand-soft">{columns[column.key].length}</span>
          </header>
          <ul className="space-y-2">
            {columns[column.key].map(({ assignment: a, traffic }) => (
              <li key={a.id}>
                <Link href={`/ueberlassung/einsaetze/${a.id}`} className="block rounded-lg border border-white/10 bg-brand-panel p-2.5 transition-colors hover:border-brand-accent/50">
                  <p className="truncate text-xs font-semibold">{a.worker_name}</p>
                  <p className="mt-0.5 truncate text-[10.45px] text-brand-muted" title={a.client_name}>{a.client_name}</p>
                  <p className="mt-1 text-[10.45px] text-brand-muted">
                    {formatDate(a.start_date)} – {a.actual_end_date ? formatDate(a.actual_end_date) : a.planned_end_date ? formatDate(a.planned_end_date) : "offen"}
                  </p>
                  <div className="mt-1.5 flex flex-wrap items-center justify-between gap-1">
                    <span className="text-[10.45px] text-brand-soft">Checkliste {a.checklist_done}/{a.checklist_total}</span>
                    {traffic && <TrafficBadge traffic={traffic} />}
                  </div>
                  {isAdmin && (a.billing_rate || a.hourly_wage) && (
                    <p className="mt-1 text-[10.45px] text-brand-muted">Satz {formatMoney(a.billing_rate)} · Lohn {formatMoney(a.hourly_wage)}</p>
                  )}
                </Link>
              </li>
            ))}
            {columns[column.key].length === 0 && <li className="rounded-lg border border-dashed border-white/10 p-4 text-center text-[10.45px] text-brand-muted">Keine Einsätze</li>}
          </ul>
        </section>
      ))}
    </div>
  );
}
