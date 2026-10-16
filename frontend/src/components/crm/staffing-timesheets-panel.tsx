"use client";

// NOMICON: Überlassung - Stundenzettel eines Einsatzes: erfassen, einreichen, Freigabelink für den Kunden.
import { useState } from "react";
import { Copy, FilePlus2, Send } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Modal } from "@/components/ui/modal";
import { ErrorBanner } from "@/components/crm/error-banner";
import { invalidateStaffing, useStaffingTimesheets } from "@/lib/api/staffing-hooks";
import {
  TIMESHEET_STATUS_LABELS,
  createStaffingTimesheet,
  saveStaffingTimesheetEntries,
  submitStaffingTimesheet,
  type StaffingTimesheet,
  type StaffingTimesheetStatus,
  type StaffingTimesheetSubmitResult,
} from "@/lib/api/staffing";
import { formatDate, formatDateTime } from "@/lib/utils";
import { EmptyHint, LoadError, LoadingRows, labelClass } from "./staffing-ui";
import { formatHours } from "@/lib/format"; // NOMICON

const STATUS_TONE: Record<StaffingTimesheetStatus, "gray" | "blue" | "green" | "red"> = {
  open: "gray",
  submitted: "blue",
  approved: "green",
  rejected: "red",
};

function isoDate(date: Date): string {
  const year = date.getFullYear();
  const month = String(date.getMonth() + 1).padStart(2, "0");
  const day = String(date.getDate()).padStart(2, "0");
  return `${year}-${month}-${day}`;
}

/** Alle Tage von start bis end (jeweils inklusive) als ISO-Datum. */
function daysBetween(start: string, end: string): string[] {
  const days: string[] = [];
  const cursor = new Date(`${start}T12:00:00`);
  const last = new Date(`${end}T12:00:00`);
  while (cursor <= last && days.length < 93) {
    days.push(isoDate(cursor));
    cursor.setDate(cursor.getDate() + 1);
  }
  return days;
}

function weekday(iso: string): string {
  return new Intl.DateTimeFormat("de-DE", { weekday: "short", day: "2-digit", month: "2-digit" }).format(new Date(`${iso}T12:00:00`));
}

function previousMonth(): { start: string; end: string } {
  const now = new Date();
  return { start: isoDate(new Date(now.getFullYear(), now.getMonth() - 1, 1)), end: isoDate(new Date(now.getFullYear(), now.getMonth(), 0)) };
}

export function StaffingTimesheetsPanel({ assignmentId, enabled }: { assignmentId: string; enabled: boolean }) {
  const { data, error, isLoading, mutate } = useStaffingTimesheets(assignmentId, enabled);
  const [creating, setCreating] = useState(false);
  const [editing, setEditing] = useState<StaffingTimesheet | null>(null);
  const [link, setLink] = useState<StaffingTimesheetSubmitResult | null>(null);
  const [busyId, setBusyId] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);

  if (!enabled) return null;

  async function submit(sheet: StaffingTimesheet) {
    setBusyId(sheet.id);
    setActionError(null);
    try {
      setLink(await submitStaffingTimesheet(sheet.id));
      await invalidateStaffing();
    } catch (exception) {
      setActionError(exception instanceof Error ? exception.message : "Einreichen fehlgeschlagen.");
    } finally {
      setBusyId(null);
    }
  }

  return (
    <Card>
      <CardContent>
        <div className="flex flex-wrap items-center justify-between gap-3">
          <h3 className="font-semibold">Stundenzettel</h3>
          <Button size="sm" variant="outline" onClick={() => setCreating(true)}><FilePlus2 size={14} />Neuer Stundenzettel</Button>
        </div>
        <ErrorBanner message={actionError} className="mt-3" />
        <div className="mt-4">
          {error ? (
            <LoadError onRetry={() => void mutate()} />
          ) : isLoading || !data ? (
            <LoadingRows rows={2} />
          ) : data.data.length === 0 ? (
            <EmptyHint>Noch kein Stundenzettel. Pro Monat einen anlegen, Stunden erfassen und dem Kunden zur Freigabe schicken.</EmptyHint>
          ) : (
            <ul className="space-y-2">
              {data.data.map((sheet) => (
                <li key={sheet.id} className="rounded-lg border border-white/10 p-3">
                  <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
                    <div className="min-w-0">
                      <p className="text-sm font-medium">{formatDate(sheet.period_start)} – {formatDate(sheet.period_end)}</p>
                      <p className="text-xs text-brand-muted">
                        {formatHours(sheet.total_hours)} an {sheet.entries.length} Tag(en)
                        {sheet.status === "approved" && sheet.decided_by_name ? ` · freigegeben von ${sheet.decided_by_name}, ${formatDateTime(sheet.decided_at)}` : ""}
                        {sheet.status === "submitted" && sheet.approval_link_expires_at ? ` · Link gültig bis ${formatDate(sheet.approval_link_expires_at)}` : ""}
                      </p>
                    </div>
                    <div className="flex flex-wrap items-center gap-2">
                      <Badge tone={STATUS_TONE[sheet.status]}>{TIMESHEET_STATUS_LABELS[sheet.status]}</Badge>
                      {(sheet.status === "open" || sheet.status === "rejected") && (
                        <Button size="sm" variant="outline" onClick={() => setEditing(sheet)}>Stunden erfassen</Button>
                      )}
                      {(sheet.status === "open" || sheet.status === "rejected") && sheet.entries.length > 0 && (
                        <Button size="sm" disabled={busyId === sheet.id} onClick={() => void submit(sheet)}><Send size={14} />Einreichen</Button>
                      )}
                      {sheet.status === "submitted" && (
                        <Button size="sm" variant="outline" disabled={busyId === sheet.id} onClick={() => void submit(sheet)}>Link neu erzeugen</Button>
                      )}
                    </div>
                  </div>
                  {sheet.status === "rejected" && sheet.rejection_reason && (
                    <p role="status" className="mt-2 rounded border border-brand-warning/30 bg-brand-warning/10 p-2 text-xs text-brand-warning">
                      Vom Kunden abgelehnt{sheet.decided_by_name ? ` (${sheet.decided_by_name})` : ""}: {sheet.rejection_reason}
                    </p>
                  )}
                </li>
              ))}
            </ul>
          )}
        </div>
      </CardContent>
      {creating && <CreateModal assignmentId={assignmentId} onClose={() => setCreating(false)} onCreated={(sheet) => { setCreating(false); setEditing(sheet); }} />}
      {editing && <EntriesModal sheet={editing} onClose={() => setEditing(null)} />}
      {link && <LinkModal result={link} onClose={() => setLink(null)} />}
    </Card>
  );
}

function CreateModal({ assignmentId, onClose, onCreated }: { assignmentId: string; onClose: () => void; onCreated: (sheet: StaffingTimesheet) => void }) {
  const initial = previousMonth();
  const [start, setStart] = useState(initial.start);
  const [end, setEnd] = useState(initial.end);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  async function submit(event: React.FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const sheet = await createStaffingTimesheet(assignmentId, start, end);
      await invalidateStaffing();
      onCreated(sheet);
    } catch (exception) {
      setError(exception instanceof Error ? exception.message : "Stundenzettel konnte nicht angelegt werden.");
    } finally {
      setBusy(false);
    }
  }
  return (
    <Modal title="Neuer Stundenzettel" eyebrow="Überlassung" onClose={onClose}>
      <form className="space-y-4" onSubmit={submit}>
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
          <div><label className={labelClass} htmlFor="ts-start">Von *</label><Input id="ts-start" type="date" required value={start} onChange={(e) => setStart(e.target.value)} /></div>
          <div><label className={labelClass} htmlFor="ts-end">Bis *</label><Input id="ts-end" type="date" required min={start} value={end} onChange={(e) => setEnd(e.target.value)} /></div>
        </div>
        <p className="text-xs text-brand-muted">Voreingestellt ist der Vormonat. Ein Stundenzettel umfasst höchstens 62 Tage und muss im Einsatzzeitraum liegen.</p>
        <ErrorBanner message={error} />
        <div className="flex justify-end gap-2">
          <Button type="button" variant="outline" onClick={onClose}>Abbrechen</Button>
          <Button type="submit" disabled={busy}>{busy ? "Anlegen…" : "Anlegen"}</Button>
        </div>
      </form>
    </Modal>
  );
}

function EntriesModal({ sheet, onClose }: { sheet: StaffingTimesheet; onClose: () => void }) {
  const days = daysBetween(sheet.period_start, sheet.period_end);
  const existing = new Map(sheet.entries.map((entry) => [entry.work_date, entry]));
  const [rows, setRows] = useState(() =>
    Object.fromEntries(days.map((day) => [day, { hours: existing.get(day) ? String(Number(existing.get(day)?.hours)) : "", pause: String(existing.get(day)?.break_minutes ?? 0) }])),
  );
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  function setRow(day: string, field: "hours" | "pause", value: string) {
    setRows((current) => ({ ...current, [day]: { ...current[day], [field]: value } }));
  }
  const total = days.reduce((sum, day) => sum + (Number((rows[day]?.hours ?? "").replace(",", ".")) || 0), 0);

  async function save(event: React.FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const entries = days.flatMap((day) => {
        const hours = (rows[day]?.hours ?? "").trim().replace(",", ".");
        if (!hours) return [];
        const value = Number(hours);
        if (!Number.isFinite(value) || value <= 0 || value > 24) throw new Error(`${weekday(day)}: Stunden zwischen 0 und 24 angeben.`);
        const pause = Number(rows[day]?.pause || 0);
        if (!Number.isInteger(pause) || pause < 0 || pause > 600) throw new Error(`${weekday(day)}: Pause in Minuten (0 bis 600).`);
        return [{ work_date: day, hours: value.toFixed(2), break_minutes: pause }];
      });
      await saveStaffingTimesheetEntries(sheet.id, entries);
      await invalidateStaffing();
      onClose();
    } catch (exception) {
      setError(exception instanceof Error ? exception.message : "Speichern fehlgeschlagen.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <Modal title="Stunden erfassen" eyebrow={`${formatDate(sheet.period_start)} – ${formatDate(sheet.period_end)}`} onClose={onClose} maxWidth="max-w-xl">
      <form onSubmit={save}>
        <div className="max-h-[55vh] space-y-1 overflow-y-auto pr-1">
          <div className="grid grid-cols-[1fr_5.5rem_5.5rem] gap-2 text-[9.5px] font-semibold uppercase tracking-wider text-brand-gray">
            <span>Tag</span><span>Stunden</span><span>Pause (Min.)</span>
          </div>
          {days.map((day) => (
            <div key={day} className="grid grid-cols-[1fr_5.5rem_5.5rem] items-center gap-2">
              <span className="text-sm">{weekday(day)}</span>
              <Input aria-label={`Stunden ${weekday(day)}`} inputMode="decimal" className="h-9" value={rows[day]?.hours ?? ""} onChange={(e) => setRow(day, "hours", e.target.value)} />
              <Input aria-label={`Pause ${weekday(day)}`} inputMode="numeric" className="h-9" value={rows[day]?.pause ?? "0"} onChange={(e) => setRow(day, "pause", e.target.value)} />
            </div>
          ))}
        </div>
        <p className="mt-3 text-sm font-medium">Summe: {formatHours(total)}</p>
        <ErrorBanner message={error} className="mt-3" />
        <div className="mt-4 flex justify-end gap-2">
          <Button type="button" variant="outline" onClick={onClose}>Abbrechen</Button>
          <Button type="submit" disabled={busy}>{busy ? "Speichern…" : "Speichern"}</Button>
        </div>
      </form>
    </Modal>
  );
}

function LinkModal({ result, onClose }: { result: StaffingTimesheetSubmitResult; onClose: () => void }) {
  const url = typeof window === "undefined" ? result.approval_path : `${window.location.origin}${result.approval_path}`;
  const [copied, setCopied] = useState(false);
  async function copy() {
    try {
      await navigator.clipboard.writeText(url);
      setCopied(true);
    } catch {
      setCopied(false);
    }
  }
  return (
    <Modal title="Freigabelink für den Kunden" eyebrow="Stundenzettel eingereicht" onClose={onClose} maxWidth="max-w-xl">
      <div className="space-y-4">
        <p className="text-sm text-brand-soft">
          Diesen Link an den Kunden schicken. Er funktioniert ohne Anmeldung, nur einmal und gilt bis {formatDate(result.expires_at)}.
          <strong> Der Link wird nur jetzt angezeigt</strong> – später kann über „Link neu erzeugen“ ein neuer erstellt werden (der alte wird dann ungültig).
        </p>
        <div className="flex gap-2">
          <Input readOnly aria-label="Freigabelink" value={url} onFocus={(e) => e.currentTarget.select()} />
          <Button type="button" variant="outline" onClick={() => void copy()}><Copy size={14} />{copied ? "Kopiert" : "Kopieren"}</Button>
        </div>
        <div className="flex justify-end"><Button type="button" onClick={onClose}>Fertig</Button></div>
      </div>
    </Modal>
  );
}
