"use client";

// NOMICON: Überlassung - Einsatz: Stammdaten, Fristen, Pflicht-Checkliste, Statuswechsel.
import { useState } from "react";
import Link from "next/link";
import { CheckCircle2, Circle, Pencil } from "lucide-react";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Modal } from "@/components/ui/modal";
import { ErrorBanner } from "@/components/crm/error-banner";
import { useCurrentUser } from "@/lib/api/hooks";
import { invalidateStaffing, useStaffingAssignment } from "@/lib/api/staffing-hooks";
import {
  CHECKLIST_LABELS,
  changeStaffingAssignmentStatus,
  formatMoney,
  setStaffingChecklistItem,
  updateStaffingAssignment,
  type StaffingAssignmentDetail,
  type StaffingAssignmentStatus,
} from "@/lib/api/staffing";
import { formatDate } from "@/lib/utils";
import {
  AssignmentStatusBadge,
  DeadlineMeter,
  Fact,
  LEGAL_NOTICE,
  LoadError,
  LoadingRows,
  labelClass,
} from "./staffing-ui";

function today(): string {
  return new Date().toISOString().slice(0, 10);
}

export function StaffingAssignmentDetailView({ id }: { id: string }) {
  const { data, error, isLoading, mutate } = useStaffingAssignment(id);
  const { data: me } = useCurrentUser();
  const isAdmin = me?.data.is_admin ?? false;
  const [busy, setBusy] = useState(false);
  const [actionError, setActionError] = useState<string | null>(null);
  const [editing, setEditing] = useState(false);
  const [ending, setEnding] = useState<"ended" | "aborted" | null>(null);

  if (error) return <LoadError onRetry={() => void mutate()} />;
  if (isLoading || !data) return <LoadingRows />;
  const assignment = data.data;
  if (!assignment) return <p className="text-sm text-brand-muted">Einsatz nicht gefunden.</p>;
  const editable = assignment.status === "planned" || assignment.status === "active";
  const hasProblems = assignment.activation_problems.length > 0;

  async function run(action: () => Promise<unknown>) {
    setBusy(true);
    setActionError(null);
    try {
      await action();
      await invalidateStaffing();
    } catch (exception) {
      setActionError(exception instanceof Error ? exception.message : "Aktion fehlgeschlagen.");
    } finally {
      setBusy(false);
    }
  }

  const margin =
    isAdmin && assignment.billing_rate !== null && assignment.hourly_wage !== null
      ? Number(assignment.billing_rate) - Number(assignment.hourly_wage)
      : null;

  return (
    <div className="space-y-5">
      <div className="flex flex-col justify-between gap-3 sm:flex-row sm:items-start">
        <div className="min-w-0">
          <div className="mb-2 flex flex-wrap items-center gap-2">
            <AssignmentStatusBadge status={assignment.status} />
            <span className="text-xs text-brand-muted">Beginn {formatDate(assignment.start_date)}</span>
          </div>
          <h2 className="text-xl font-semibold tracking-[-.02em]">
            <Link href={`/ueberlassung/leiharbeitnehmer/${assignment.worker_id}`} className="hover:underline">{assignment.worker_name}</Link>
            <span className="text-brand-muted"> bei </span>
            <Link href={`/kanzleien/${assignment.client_company_id}`} className="hover:underline">{assignment.client_name}</Link>
          </h2>
        </div>
        <div className="flex flex-wrap gap-2">
          {editable && <Button size="sm" variant="outline" onClick={() => setEditing(true)}><Pencil size={14} />Bearbeiten</Button>}
          {assignment.status === "planned" && (
            <Button size="sm" disabled={busy || hasProblems} title={hasProblems ? "Erst die offenen Punkte unten erledigen" : undefined}
              onClick={() => void run(() => changeStaffingAssignmentStatus(id, "active"))}>
              Einsatz aktivieren
            </Button>
          )}
          {assignment.status === "active" && <Button size="sm" disabled={busy} onClick={() => setEnding("ended")}>Einsatz beenden</Button>}
          {editable && <Button size="sm" variant="ghost" disabled={busy} onClick={() => setEnding("aborted")}>Abbrechen</Button>}
        </div>
      </div>

      <ErrorBanner message={actionError} />

      {assignment.status === "planned" && hasProblems && (
        <div role="status" className="rounded-lg border border-brand-warning/30 bg-brand-warning/10 p-3 text-xs text-brand-warning">
          <p className="font-semibold">Noch nicht aktivierbar:</p>
          <ul className="mt-1 list-disc space-y-0.5 pl-5">
            {assignment.activation_problems.map((problem) => <li key={problem}>{problem}</li>)}
          </ul>
        </div>
      )}

      <div className="grid grid-cols-1 gap-5 lg:grid-cols-[1.2fr_.8fr]">
        <Card>
          <CardContent>
            <h3 className="font-semibold">Einsatz</h3>
            <div className="mt-4 grid grid-cols-1 gap-5 sm:grid-cols-2">
              <Fact label="Geplantes Ende">{assignment.planned_end_date ? formatDate(assignment.planned_end_date) : "offen"}</Fact>
              <Fact label="Tatsächliches Ende">{assignment.actual_end_date ? formatDate(assignment.actual_end_date) : null}</Fact>
              <Fact label="Einsatzort">{assignment.location}</Fact>
              <Fact label="Tätigkeit">{assignment.activity}</Fact>
              {isAdmin && (
                <>
                  <Fact label="Verrechnungssatz">{formatMoney(assignment.billing_rate)}</Fact>
                  <Fact label="Lohn">{formatMoney(assignment.hourly_wage)}</Fact>
                  <Fact label="Marge je Stunde">{margin === null ? null : formatMoney(margin.toFixed(2))}</Fact>
                </>
              )}
            </div>
            {assignment.notes && <p className="mt-5 whitespace-pre-line border-t border-white/10 pt-4 text-sm text-brand-soft">{assignment.notes}</p>}
          </CardContent>
        </Card>
        <Card>
          <CardContent>
            <h3 className="font-semibold">Fristen (Paar {assignment.worker_name} / {assignment.client_name})</h3>
            <div className="mt-4"><DeadlineMeter deadline={assignment.deadline} /></div>
            <p className="mt-4 text-xs text-brand-muted">{LEGAL_NOTICE}</p>
          </CardContent>
        </Card>
      </div>

      <Card>
        <CardContent>
          <div className="flex items-baseline justify-between gap-3">
            <h3 className="font-semibold">Pflicht-Checkliste</h3>
            <span className="text-xs text-brand-muted">{assignment.checklist_done} von {assignment.checklist_total} erledigt</span>
          </div>
          <ul className="mt-3 divide-y divide-white/5">
            {assignment.checklist.map((item) => (
              <li key={item.id}>
                <button
                  type="button"
                  disabled={busy || !editable}
                  aria-pressed={item.done}
                  onClick={() => void run(() => setStaffingChecklistItem(id, item.id, !item.done))}
                  className="flex w-full items-center gap-3 py-2.5 text-left text-sm disabled:cursor-default disabled:opacity-70"
                >
                  {item.done ? <CheckCircle2 size={18} className="text-brand-success" aria-hidden /> : <Circle size={18} className="text-brand-muted" aria-hidden />}
                  <span className="flex-1">{CHECKLIST_LABELS[item.item_key]}</span>
                  {item.done_on && <span className="text-xs text-brand-muted">{formatDate(item.done_on)}</span>}
                </button>
              </li>
            ))}
          </ul>
        </CardContent>
      </Card>

      {editing && <EditModal assignment={assignment} isAdmin={isAdmin} onClose={() => setEditing(false)} />}
      {ending && (
        <EndModal
          mode={ending}
          startDate={assignment.start_date}
          onClose={() => setEnding(null)}
          onConfirm={async (date) => {
            await run(() => changeStaffingAssignmentStatus(id, ending, assignment.status === "active" ? date : undefined));
            setEnding(null);
          }}
        />
      )}
    </div>
  );
}

function EndModal({ mode, startDate, onClose, onConfirm }: {
  mode: "ended" | "aborted";
  startDate: string;
  onClose: () => void;
  onConfirm: (date: string) => Promise<void>;
}) {
  const [date, setDate] = useState(today());
  const label: Record<"ended" | "aborted", string> = { ended: "Einsatz beenden", aborted: "Einsatz abbrechen" };
  const status: StaffingAssignmentStatus = mode;
  return (
    <Modal title={label[mode]} eyebrow="Überlassung" onClose={onClose}>
      <form className="space-y-4" onSubmit={(event) => { event.preventDefault(); void onConfirm(date); }}>
        <p className="text-sm text-brand-soft">
          {status === "ended" ? "Der Einsatz wird als beendet gespeichert und ist danach nicht mehr änderbar." : "Ein abgebrochener Einsatz zählt nicht für die Überlassungsdauer und ist danach nicht mehr änderbar."}
        </p>
        <div>
          <label className={labelClass} htmlFor="end-date">Tatsächliches Ende</label>
          <Input id="end-date" type="date" required min={startDate} value={date} onChange={(e) => setDate(e.target.value)} />
        </div>
        <div className="flex justify-end gap-2">
          <Button type="button" variant="outline" onClick={onClose}>Zurück</Button>
          <Button type="submit">{label[mode]}</Button>
        </div>
      </form>
    </Modal>
  );
}

function EditModal({ assignment, isAdmin, onClose }: { assignment: StaffingAssignmentDetail; isAdmin: boolean; onClose: () => void }) {
  const [form, setForm] = useState({
    planned_end_date: assignment.planned_end_date ?? "",
    location: assignment.location ?? "",
    activity: assignment.activity ?? "",
    notes: assignment.notes ?? "",
    billing_rate: assignment.billing_rate ?? "",
    hourly_wage: assignment.hourly_wage ?? "",
  });
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  function set<K extends keyof typeof form>(key: K, value: (typeof form)[K]) {
    setForm((current) => ({ ...current, [key]: value }));
  }
  async function submit(event: React.FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await updateStaffingAssignment(assignment.id, {
        planned_end_date: form.planned_end_date || null,
        location: form.location || null,
        activity: form.activity || null,
        notes: form.notes || null,
        ...(isAdmin ? { billing_rate: form.billing_rate ? form.billing_rate.replace(",", ".") : null, hourly_wage: form.hourly_wage ? form.hourly_wage.replace(",", ".") : null } : {}),
      });
      await invalidateStaffing();
      onClose();
    } catch (exception) {
      setError(exception instanceof Error ? exception.message : "Speichern fehlgeschlagen.");
    } finally {
      setBusy(false);
    }
  }
  return (
    <Modal title="Einsatz bearbeiten" eyebrow="Überlassung" onClose={onClose}>
      <form className="space-y-4" onSubmit={submit}>
        <div><label className={labelClass} htmlFor="ed-end">Geplantes Ende</label><Input id="ed-end" type="date" min={assignment.start_date} value={form.planned_end_date} onChange={(e) => set("planned_end_date", e.target.value)} /></div>
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
          <div><label className={labelClass} htmlFor="ed-loc">Einsatzort</label><Input id="ed-loc" value={form.location} onChange={(e) => set("location", e.target.value)} /></div>
          <div><label className={labelClass} htmlFor="ed-act">Tätigkeit</label><Input id="ed-act" value={form.activity} onChange={(e) => set("activity", e.target.value)} /></div>
        </div>
        {isAdmin && (
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
            <div><label className={labelClass} htmlFor="ed-rate">Verrechnungssatz €/Std.</label><Input id="ed-rate" inputMode="decimal" value={form.billing_rate} onChange={(e) => set("billing_rate", e.target.value)} /></div>
            <div><label className={labelClass} htmlFor="ed-wage">Lohn €/Std.</label><Input id="ed-wage" inputMode="decimal" value={form.hourly_wage} onChange={(e) => set("hourly_wage", e.target.value)} /></div>
          </div>
        )}
        <div>
          <label className={labelClass} htmlFor="ed-notes">Notizen</label>
          <textarea id="ed-notes" rows={3} className="w-full rounded-md border border-white/10 bg-brand-surface px-3 py-2 text-sm text-brand-text outline-none focus:border-brand-accent" value={form.notes} onChange={(e) => set("notes", e.target.value)} />
        </div>
        <ErrorBanner message={error} />
        <div className="flex justify-end gap-2">
          <Button type="button" variant="outline" onClick={onClose}>Abbrechen</Button>
          <Button type="submit" disabled={busy}>{busy ? "Speichern…" : "Speichern"}</Button>
        </div>
      </form>
    </Modal>
  );
}
