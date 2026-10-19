"use client";

// NOMICON: Überlassung - kompakte Übersicht für Vermittler/Disponenten: das Kanban (In Auswahl, In Überlassung,
// Überlassung endet bald) und "Meine nächsten Schritte", je eine Zeile mit Link. Fristen, Erlaubnis und
// Checklisten-Details (die Compliance-Tabellen) sehen nur Admins und Teamleiter. Fristen, Equal Pay,
// überfällige Einsätze, fehlende Verträge und Erlaubnis meldet das System von selbst: als Aufgabe
// (Tagesjob) und in der Glocke. Keine Lohn- oder Margenwerte (der Stundensatz erscheint nur Admins).
import Link from "next/link";
import { ArrowRight, CalendarClock } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader } from "@/components/ui/card";
import { useStaffingTasks } from "@/lib/api/staffing-hooks";
import { taskHref } from "@/lib/staffing-tasks";
import { StaffingKanban } from "./staffing-kanban";
import { EmptyHint, LoadError, LoadingRows } from "./staffing-ui";

const MAX_STEPS = 8;

export function StaffingMyOverview() {
  const tasks = useStaffingTasks();
  if (tasks.error) return <LoadError onRetry={() => void tasks.mutate()} />;
  if (tasks.isLoading || !tasks.data) return <LoadingRows />;
  // "license" betrifft die Erlaubnis (Compliance) und ist nicht Sache der Vermittler
  const steps = tasks.data.data.tasks.filter((task) => task.kind !== "license").slice(0, MAX_STEPS);

  return (
    <div className="space-y-6">
      <section>
        <h2 className="mb-3 font-semibold">Meine Überlassungen</h2>
        <StaffingKanban />
      </section>

      <Card>
        <CardHeader>
          <div className="flex items-center gap-2"><CalendarClock size={17} className="text-brand-platinum" /><h2 className="font-semibold">Meine nächsten Schritte</h2></div>
          <Badge tone="gray">{steps.length}</Badge>
        </CardHeader>
        <CardContent className="space-y-2">
          {steps.length === 0 && <EmptyHint>Nichts zu tun – alles im grünen Bereich.</EmptyHint>}
          {steps.map((task, index) => (
            <Link key={`${task.kind}-${task.assignment_id ?? task.worker_id ?? "x"}-${index}`} href={taskHref(task)} className="flex items-center gap-3 rounded-lg border border-white/10 p-3 transition-colors hover:border-brand-accent/50">
              <span className="min-w-0 flex-1 truncate text-sm">{task.title}</span>
              <ArrowRight size={14} className="shrink-0 text-brand-muted" aria-hidden />
            </Link>
          ))}
        </CardContent>
      </Card>
    </div>
  );
}
