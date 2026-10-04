"use client";

import { useState } from "react";
import Link from "next/link";
import { CalendarCheck2, Check, CheckCircle2, ListTodo, ShieldOff, X } from "lucide-react";
import { Card, CardContent, CardHeader } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { resolveTask, snoozeTask } from "@/lib/api/queries";
import { formatDate } from "@/lib/utils";
import type { CockpitItem } from "@/lib/api/types";

const SNOOZE_OPTIONS = [
  { days: 1, label: "1 Tag" },
  { days: 3, label: "3 Tage" },
  { days: 7, label: "7 Tage" },
];

/** Nur "important"-Eintraege mit kind="task" tragen eine task_id (siehe
 * Backend schemas/operational.py::CockpitItem) - die uebrigen sind heisse
 * Prozesse ohne Task-Bezug und gehoeren nicht in diese Sektion. */
function isTaskItem(item: CockpitItem): item is CockpitItem & { task_id: string } {
  return Boolean(item.task_id);
}

export function DashboardTodo({ items }: { items: CockpitItem[] }) {
  const [rows, setRows] = useState(() => items.filter(isTaskItem));
  const [busyId, setBusyId] = useState<string | null>(null);
  const [schedulingId, setSchedulingId] = useState<string | null>(null);
  const [scheduledAt, setScheduledAt] = useState("");
  const [errorById, setErrorById] = useState<Record<string, string>>({});

  function removeRow(taskId: string) {
    setRows((current) => current.filter((row) => row.task_id !== taskId));
  }

  function setRowError(taskId: string, message: string | null) {
    setErrorById((current) => {
      const next = { ...current };
      if (message) next[taskId] = message;
      else delete next[taskId];
      return next;
    });
  }

  async function handleSnooze(taskId: string, days: number) {
    setBusyId(taskId);
    setRowError(taskId, null);
    try {
      await snoozeTask(taskId, days);
      removeRow(taskId);
    } catch {
      setRowError(taskId, "Zurückstellen fehlgeschlagen - bitte erneut versuchen.");
    } finally {
      setBusyId(null);
    }
  }

  async function handleNoResponse(taskId: string) {
    setBusyId(taskId);
    setRowError(taskId, null);
    try {
      await resolveTask(taskId, { outcome: "no_response" });
      removeRow(taskId);
    } catch {
      setRowError(taskId, "Konnte nicht geschlossen werden - bitte erneut versuchen.");
    } finally {
      setBusyId(null);
    }
  }

  // Schlichtes "Erledigt" fuer alles, was keinen Kalendereintrag braucht -
  // abgearbeitet oder anderweitig geklaert. "Nicht relevant" ist bewusst ein
  // eigener Abschlussgrund (nicht unter "done" mitgezaehlt), damit sich
  // spaeter auswerten laesst, wie oft der Mail-Agent eine Aufgabe faelschlich
  // erzeugt (Werbemail, Fehlzuordnung) - siehe Backend schemas/task.py.
  async function handleResolve(taskId: string, outcome: "done" | "not_relevant") {
    setBusyId(taskId);
    setRowError(taskId, null);
    try {
      await resolveTask(taskId, { outcome });
      removeRow(taskId);
    } catch {
      setRowError(taskId, "Konnte nicht geschlossen werden - bitte erneut versuchen.");
    } finally {
      setBusyId(null);
    }
  }

  async function handleMeetingScheduled(taskId: string) {
    if (!scheduledAt) {
      setRowError(taskId, "Bitte Datum/Uhrzeit auswählen.");
      return;
    }
    setBusyId(taskId);
    setRowError(taskId, null);
    try {
      await resolveTask(taskId, {
        outcome: "meeting_scheduled",
        scheduled_at: new Date(scheduledAt).toISOString(),
      });
      setSchedulingId(null);
      setScheduledAt("");
      removeRow(taskId);
    } catch {
      setRowError(taskId, "Termin konnte nicht angelegt werden - bitte erneut versuchen.");
    } finally {
      setBusyId(null);
    }
  }

  if (rows.length === 0) return null;

  return (
    <Card className="mb-4">
      <CardHeader>
        <div>
          <div className="flex items-center gap-2">
            <ListTodo size={17} className="text-brand-accent-light" />
            <h2 className="font-semibold">To-Do</h2>
          </div>
          <p className="mt-1 text-xs text-brand-muted">Offene Aufgaben aus Postfach-Antworten und Nachfass-Terminen</p>
        </div>
        <Badge tone="amber">{rows.length} offen</Badge>
      </CardHeader>
      <CardContent className="space-y-2">
        {rows.map((row) => {
          const taskId = row.task_id;
          const isBusy = busyId === taskId;
          const isScheduling = schedulingId === taskId;
          const rowError = errorById[taskId];
          return (
            <div key={taskId} className="rounded-lg border bg-brand-surface/75 p-3">
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div className="min-w-0 flex-1">
                  {row.candidate_id ? (
                    <Link href={`/kandidaten/${row.candidate_id}`} className="text-xs font-semibold text-brand-accent-light hover:underline">
                      {row.title}
                    </Link>
                  ) : (
                    <p className="text-xs font-semibold">{row.title}</p>
                  )}
                  <p className="mt-1 truncate text-xs text-brand-muted">{row.detail}</p>
                  <p className="mt-1 text-[9.5px] text-brand-silver">{row.due_at ? formatDate(row.due_at) : "Kein Fälligkeitsdatum"}</p>
                </div>

                <div className="flex flex-wrap items-center gap-1.5">
                  {SNOOZE_OPTIONS.map((option) => (
                    <Button
                      key={option.days}
                      variant="outline"
                      size="sm"
                      disabled={isBusy}
                      onClick={() => handleSnooze(taskId, option.days)}
                    >
                      +{option.label}
                    </Button>
                  ))}
                  <Button variant="ghost" size="sm" disabled={isBusy} onClick={() => handleNoResponse(taskId)}>
                    <X size={13} /> Keine Rückmeldung
                  </Button>
                  <Button
                    variant="outline"
                    size="sm"
                    disabled={isBusy}
                    onClick={() => {
                      setSchedulingId(isScheduling ? null : taskId);
                      setScheduledAt("");
                      setRowError(taskId, null);
                    }}
                  >
                    <CalendarCheck2 size={13} /> Gespräch vereinbart
                  </Button>
                  <Button variant="outline" size="sm" disabled={isBusy} onClick={() => handleResolve(taskId, "done")}>
                    <Check size={13} /> Erledigt
                  </Button>
                  <Button
                    variant="ghost"
                    size="sm"
                    disabled={isBusy}
                    onClick={() => handleResolve(taskId, "not_relevant")}
                    title="Fehlzuordnung des Mail-Agenten (Werbemail, falscher Treffer) - wird separat ausgewertet."
                  >
                    <ShieldOff size={13} /> Nicht relevant
                  </Button>
                </div>
              </div>

              {isScheduling ? (
                <div className="mt-3 flex flex-wrap items-center gap-2 border-t border-white/10 pt-3">
                  <input
                    type="datetime-local"
                    value={scheduledAt}
                    onChange={(event) => setScheduledAt(event.target.value)}
                    className="h-8 rounded-md border border-white/15 bg-white/5 px-2 text-xs text-white"
                  />
                  <Button size="sm" disabled={isBusy} onClick={() => handleMeetingScheduled(taskId)}>
                    <CheckCircle2 size={13} /> Termin speichern
                  </Button>
                </div>
              ) : null}

              {rowError ? <p className="mt-2 text-[9.5px] text-red-400">{rowError}</p> : null}
            </div>
          );
        })}
      </CardContent>
    </Card>
  );
}
