"use client";

// NOMICON: Startseite "Übersicht" in der Ansicht Überlassung: Hinweisleiste und Aufgaben zu Fristen,
// Stundenzetteln, Checklisten, Bench und Erlaubnis statt der Direct-To-dos. Daten: /staffing/tasks
// (Besitzbereich des Nutzers, keine Lohn- oder Margenangaben).
import Link from "next/link";
import { AlertTriangle, CalendarClock, HardHat } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader } from "@/components/ui/card";
import { useStaffingTasks } from "@/lib/api/staffing-hooks";
import { countBySeverity, taskHref, TASK_KIND_LABELS } from "@/lib/staffing-tasks";
import { formatDate } from "@/lib/utils";
import { EmptyHint, LoadError, LoadingRows } from "./staffing-ui";

const SEVERITY_TONE = { red: "red", yellow: "amber", info: "gray" } as const;
const SEVERITY_LABEL = { red: "Dringend", yellow: "Bald", info: "Hinweis" } as const;

export function StaffingHome() {
  const { data, error, isLoading, mutate } = useStaffingTasks();
  if (error) return <LoadError onRetry={() => void mutate()} />;
  if (isLoading || !data) return <LoadingRows />;
  const { tasks, alerts } = data.data;
  const counts = countBySeverity(tasks);

  return (
    <>
      {alerts.length > 0 && (
        <section className="mb-5 flex gap-2 overflow-x-auto pb-1 lg:grid lg:grid-cols-3 lg:overflow-visible lg:pb-0" aria-label="Hinweise Überlassung">
          {alerts.map((alert, index) => (
            <div
              key={alert}
              title={alert}
              className={
                "flex max-w-[260px] shrink-0 items-center gap-2 rounded-full border px-3 py-2 text-[10.45px] lg:w-full lg:max-w-none lg:shrink lg:rounded-xl lg:text-xs " +
                (index === 0 ? "border-brand-accent/40 bg-brand-accent-strong/60 text-white" : "border-brand-platinum/20 bg-brand-accent-soft/55 text-brand-soft")
              }
            >
              <AlertTriangle size={14} className="shrink-0 text-brand-platinum" />
              <span className="overflow-hidden text-ellipsis whitespace-nowrap lg:overflow-visible lg:whitespace-normal">{alert}</span>
            </div>
          ))}
        </section>
      )}
      <Card>
        <CardHeader>
          <div>
            <div className="flex items-center gap-2"><HardHat size={17} className="text-brand-platinum" /><h2 className="font-semibold">Aufgaben Überlassung</h2></div>
            <p className="mt-1 text-xs text-brand-muted">Fristen, Stundenzettel, Checklisten, Bench und Erlaubnis – dringendste zuerst</p>
          </div>
          <div className="flex gap-1.5">
            {counts.red > 0 && <Badge tone="red">{counts.red} dringend</Badge>}
            {counts.yellow > 0 && <Badge tone="amber">{counts.yellow} bald</Badge>}
            <Badge tone="gray">{tasks.length} offen</Badge>
          </div>
        </CardHeader>
        <CardContent className="space-y-2">
          {tasks.length === 0 && <EmptyHint>Keine offenen Aufgaben – alle Fristen, Stundenzettel und Checklisten sind in Ordnung.</EmptyHint>}
          {tasks.map((task, index) => (
            <Link
              key={`${task.kind}-${task.assignment_id ?? task.worker_id ?? "x"}-${index}`}
              href={taskHref(task)}
              className="flex items-center gap-3 rounded-lg border bg-brand-surface/75 p-3 transition-colors hover:border-brand-accent/50"
            >
              <CalendarClock size={15} className="shrink-0 text-brand-platinum" />
              <div className="min-w-0 flex-1">
                <p className="text-xs font-semibold">{task.title}</p>
                <p className="mt-1 text-xs text-brand-muted">{task.detail}</p>
              </div>
              <div className="flex shrink-0 flex-col items-end gap-1">
                <Badge tone={SEVERITY_TONE[task.severity]}>{SEVERITY_LABEL[task.severity]}</Badge>
                <span className="text-[9.5px] text-brand-silver">{TASK_KIND_LABELS[task.kind]}{task.due_at ? ` · ${formatDate(task.due_at)}` : ""}</span>
              </div>
            </Link>
          ))}
        </CardContent>
      </Card>
    </>
  );
}
