"use client";

// NOMICON: Überlassungs-Kanban mit drei Spalten. "In Auswahl" (geplante Einsätze und Personen ohne Einsatz) und
// "In Überlassung" (aktive Einsätze) füllt man von Hand: Karte ziehen oder "In Überlassung setzen" (der Server
// prüft Checkliste, Vertrag und Erlaubnis und meldet, was fehlt). "Überlassung endet bald" füllt sich von selbst,
// sechs Wochen vor dem geplanten Ende. Auf der Karte: Kandidat, Kunde und - nur für Admins - der Stundensatz
// (Verrechnungssatz); Lohn und Marge zeigt der Server nur Admins.
import { useMemo, useState } from "react";
import Link from "next/link";
import { useCurrentUser } from "@/lib/api/hooks";
import { invalidateStaffing, useStaffingAssignments, useStaffingWorkers } from "@/lib/api/staffing-hooks";
import { changeStaffingAssignmentStatus, formatMoney, type StaffingAssignment, type StaffingWorker } from "@/lib/api/staffing";
import { applicantsWithoutAssignment, classifyKanban, daysUntilEnd, ENDING_SOON_WEEKS, type KanbanColumn } from "@/lib/staffing-board";
import { Button } from "@/components/ui/button";
import { ErrorBanner } from "@/components/crm/error-banner";
import { formatDate } from "@/lib/utils";
import { EmptyHint, LoadError, LoadingRows } from "./staffing-ui";

const COLUMNS: { key: KanbanColumn; title: string; hint: string }[] = [
  { key: "selection", title: "In Auswahl", hint: "von Hand: Karte nach „In Überlassung“ ziehen" },
  { key: "running", title: "In Überlassung", hint: "aktive Einsätze" },
  { key: "ending", title: "Überlassung endet bald", hint: `automatisch ${ENDING_SOON_WEEKS} Wochen vor dem Ende` },
];

function endText(a: StaffingAssignment, today: Date): string {
  const left = daysUntilEnd(a, today);
  if (left === null) return "ohne Enddatum";
  if (left < 0) return `Ende ${formatDate(a.planned_end_date as string)} – überfällig`;
  return `Ende ${formatDate(a.planned_end_date as string)} – in ${left} ${left === 1 ? "Tag" : "Tagen"}`;
}

export function StaffingKanban() {
  const { data, error, isLoading, mutate } = useStaffingAssignments({});
  const { data: applicantData } = useStaffingWorkers("applicant");
  const { data: me } = useCurrentUser();
  const isAdmin = me?.data.is_admin ?? false;
  const [moveError, setMoveError] = useState<string | null>(null);
  const [busyId, setBusyId] = useState<string | null>(null);
  const today = useMemo(() => new Date(), []);

  const columns = useMemo(() => {
    const grouped: Record<KanbanColumn, StaffingAssignment[]> = { selection: [], running: [], ending: [] };
    for (const assignment of data?.data ?? []) {
      const key = classifyKanban(assignment, today);
      if (key) grouped[key].push(assignment);
    }
    return grouped;
  }, [data, today]);

  const applicants: StaffingWorker[] = useMemo(() => {
    const ids = new Set(applicantsWithoutAssignment(applicantData?.data ?? [], data?.data ?? []));
    return (applicantData?.data ?? []).filter((worker) => ids.has(worker.id));
  }, [applicantData, data]);

  async function activate(id: string) {
    setMoveError(null);
    setBusyId(id);
    try {
      await changeStaffingAssignmentStatus(id, "active");
      await invalidateStaffing();
    } catch (exception) {
      setMoveError(exception instanceof Error ? exception.message : "Der Einsatz ließ sich nicht in Überlassung setzen.");
    } finally {
      setBusyId(null);
    }
  }

  if (error) return <LoadError onRetry={() => void mutate()} />;
  if (isLoading || !data) return <LoadingRows />;

  return (
    <div className="space-y-3">
      <ErrorBanner message={moveError} />
      <div className="grid grid-cols-1 gap-3 lg:grid-cols-3">
        {COLUMNS.map((column) => {
          const count = columns[column.key].length + (column.key === "selection" ? applicants.length : 0);
          return (
            <section
              key={column.key}
              aria-label={column.title}
              className="min-w-0 rounded-xl border border-white/10 bg-brand-surface p-2"
              onDragOver={column.key === "running" ? (event) => event.preventDefault() : undefined}
              onDrop={
                column.key === "running"
                  ? (event) => {
                      event.preventDefault();
                      const id = event.dataTransfer.getData("text/plain");
                      if (id && columns.selection.some((a) => a.id === id)) void activate(id);
                    }
                  : undefined
              }
            >
              <header className="px-2 py-2">
                <div className="flex items-center justify-between">
                  <h3 className="truncate text-sm font-semibold text-brand-text">{column.title}</h3>
                  <span className="grid size-5 shrink-0 place-items-center rounded-full border border-white/10 bg-brand-panel text-[9.5px] text-brand-soft">{count}</span>
                </div>
                <p className="mt-0.5 text-[10.45px] text-brand-muted">{column.hint}</p>
              </header>
              <ul className="space-y-2">
                {column.key === "selection" && applicants.map((worker) => (
                  <li key={worker.id} className="rounded-lg border border-dashed border-white/20 bg-brand-panel p-2.5">
                    <p className="truncate text-sm font-semibold">{worker.candidate_name}</p>
                    <p className="mt-0.5 text-xs text-brand-muted">Kunde: noch keiner · kein Einsatz angelegt</p>
                    <Button asChild size="sm" variant="outline" className="mt-2">
                      <Link href={`/kandidaten/${worker.candidate_id}?tab=ueberlassung`}>Einsatz anlegen</Link>
                    </Button>
                  </li>
                ))}
                {columns[column.key].map((a) => (
                  <li
                    key={a.id}
                    className="rounded-lg border border-white/10 bg-brand-panel p-2.5 transition-colors hover:border-brand-accent/50"
                    draggable={column.key === "selection"}
                    onDragStart={column.key === "selection" ? (event) => event.dataTransfer.setData("text/plain", a.id) : undefined}
                  >
                    <Link href={`/ueberlassung/einsaetze/${a.id}`} className="block">
                      <p className="truncate text-sm font-semibold">{a.worker_name}</p>
                      <p className="mt-0.5 truncate text-xs text-brand-muted" title={a.client_name}>{a.client_name}</p>
                      {isAdmin && a.billing_rate && <p className="mt-1 text-xs text-brand-soft">Stundensatz {formatMoney(a.billing_rate)}</p>}
                      {column.key === "ending" && (
                        <p className="mt-1 text-xs font-medium text-brand-warning">{endText(a, today)}</p>
                      )}
                      {column.key === "running" && <p className="mt-1 text-xs text-brand-muted">{endText(a, today)}</p>}
                      {column.key === "selection" && (
                        <p className="mt-1 text-xs text-brand-muted">ab {formatDate(a.start_date)} · Checkliste {a.checklist_done}/{a.checklist_total}</p>
                      )}
                    </Link>
                    {column.key === "selection" && (
                      <Button size="sm" variant="outline" className="mt-2" disabled={busyId === a.id} onClick={() => void activate(a.id)}>
                        {busyId === a.id ? "Wird gesetzt…" : "In Überlassung setzen"}
                      </Button>
                    )}
                  </li>
                ))}
                {count === 0 && <li><EmptyHint>Keine Einträge.</EmptyHint></li>}
              </ul>
            </section>
          );
        })}
      </div>
    </div>
  );
}
