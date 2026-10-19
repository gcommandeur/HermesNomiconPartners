"use client";

// NOMICON: Überlassung - kompakte Übersicht für Vermittler/Disponenten: nur "Meine Einsätze" und
// "Meine nächsten Schritte", je eine Zeile mit Link auf den Einsatz. Fristen, Erlaubnis und
// Checklisten-Details (die Compliance-Tabellen) sehen nur Admins und Teamleiter. Fristen, Equal Pay,
// überfällige Einsätze, fehlende Verträge und Erlaubnis meldet das System von selbst: als Aufgabe
// (Tagesjob) und in der Glocke. Keine Lohn- oder Margenwerte.
import Link from "next/link";
import { ArrowRight, CalendarClock, HardHat } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader } from "@/components/ui/card";
import { useStaffingAssignments, useStaffingTasks } from "@/lib/api/staffing-hooks";
import { taskHref } from "@/lib/staffing-tasks";
import { formatDate } from "@/lib/utils";
import { AssignmentStatusBadge, EmptyHint, LoadError, LoadingRows } from "./staffing-ui";

const MAX_STEPS = 8;

export function StaffingMyOverview() {
  const assignments = useStaffingAssignments({});
  const tasks = useStaffingTasks();
  if (assignments.error || tasks.error) return <LoadError onRetry={() => { void assignments.mutate(); void tasks.mutate(); }} />;
  if (assignments.isLoading || tasks.isLoading || !assignments.data || !tasks.data) return <LoadingRows />;
  const mine = assignments.data.data.filter((a) => a.status === "planned" || a.status === "active");
  // "license" betrifft die Erlaubnis (Compliance) und ist nicht Sache der Vermittler
  const steps = tasks.data.data.tasks.filter((task) => task.kind !== "license").slice(0, MAX_STEPS);

  return (
    <div className="grid grid-cols-1 gap-6 xl:grid-cols-2">
      <Card>
        <CardHeader>
          <div className="flex items-center gap-2"><HardHat size={17} className="text-brand-platinum" /><h2 className="font-semibold">Meine Einsätze</h2></div>
          <Badge tone="gray">{mine.length} offen</Badge>
        </CardHeader>
        <CardContent className="space-y-2">
          {mine.length === 0 && <EmptyHint>Du betreust gerade keinen geplanten oder aktiven Einsatz.</EmptyHint>}
          {mine.map((a) => (
            <Link key={a.id} href={`/ueberlassung/einsaetze/${a.id}`} className="flex items-center justify-between gap-3 rounded-lg border border-white/10 p-3 transition-colors hover:bg-brand-hover/40">
              <span className="min-w-0">
                <span className="block truncate text-sm font-medium">{a.worker_name} <span className="text-brand-muted">bei</span> {a.client_name}</span>
                <span className="block truncate text-xs text-brand-muted">
                  {formatDate(a.start_date)} – {a.planned_end_date ? formatDate(a.planned_end_date) : "offen"}
                </span>
              </span>
              <span className="flex shrink-0 items-center gap-2">
                {a.is_overdue && <Badge tone="red">Überfällig</Badge>}
                <AssignmentStatusBadge status={a.status} />
              </span>
            </Link>
          ))}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <div className="flex items-center gap-2"><CalendarClock size={17} className="text-brand-platinum" /><h2 className="font-semibold">Meine nächsten Schritte</h2></div>
          <Badge tone="gray">{steps.length}</Badge>
        </CardHeader>
        <CardContent className="space-y-2">
          {steps.length === 0 && <EmptyHint>Nichts zu tun – alles im grünen Bereich.</EmptyHint>}
          {steps.map((task, index) => (
            <Link key={`${task.kind}-${task.assignment_id ?? task.worker_id ?? "x"}-${index}`} href={taskHref(task)} className="flex items-center gap-3 rounded-lg border border-white/10 p-3 transition-colors hover:bg-brand-hover/40">
              <span className="min-w-0 flex-1 truncate text-sm">{task.title}</span>
              <ArrowRight size={14} className="shrink-0 text-brand-muted" aria-hidden />
            </Link>
          ))}
        </CardContent>
      </Card>
    </div>
  );
}
