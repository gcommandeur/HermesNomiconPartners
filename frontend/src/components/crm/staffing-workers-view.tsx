"use client";

// NOMICON: Überlassung - Leiharbeitnehmer: Liste, Anlegen aus einem Kandidaten, Detail.
import { useMemo, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { Pencil, Plus } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Modal } from "@/components/ui/modal";
import { SearchSelect } from "@/components/ui/search-select";
import { ErrorBanner } from "@/components/crm/error-banner";
import { searchCandidates } from "@/lib/api/search-select-helpers";
import { useCurrentUser } from "@/lib/api/hooks";
import { invalidateStaffing, useStaffingDeadlines, useStaffingWorker, useStaffingWorkers } from "@/lib/api/staffing-hooks";
import {
  WORKER_STATUS_LABELS,
  createStaffingWorker,
  formatMoney,
  updateStaffingWorker,
  type StaffingWorker,
  type StaffingWorkerStatus,
} from "@/lib/api/staffing";
import { formatDate } from "@/lib/utils";
import { StaffingAssignmentCreateButton } from "./staffing-assignment-create-modal";
import { StaffingAssignmentsView } from "./staffing-assignments-view";
import { DeadlineRow } from "./staffing-overview-view";
import { EmptyHint, Fact, LoadError, LoadingRows, WorkerStatusBadge, labelClass, selectClass } from "./staffing-ui";
import { formatHours } from "@/lib/format"; // NOMICON

// --- Liste -------------------------------------------------------------------------------------

export function StaffingWorkersView() {
  const [status, setStatus] = useState<StaffingWorkerStatus | "">("");
  const [search, setSearch] = useState("");
  const { data, error, isLoading, mutate } = useStaffingWorkers(status || undefined);
  const rows = useMemo(() => {
    const term = search.trim().toLowerCase();
    const all = data?.data ?? [];
    return term ? all.filter((w) => `${w.candidate_name} ${w.candidate_number ?? ""} ${w.pay_grade ?? ""}`.toLowerCase().includes(term)) : all;
  }, [data, search]);

  return (
    <div>
      <div className="mb-4 flex flex-col gap-2 sm:flex-row">
        <Input aria-label="Leiharbeitnehmer durchsuchen" placeholder="Suchen: Name, Nummer, Entgeltgruppe…" value={search} onChange={(e) => setSearch(e.target.value)} className="sm:max-w-xs" />
        <select aria-label="Status filtern" className={`${selectClass} sm:max-w-[200px]`} value={status} onChange={(e) => setStatus(e.target.value as StaffingWorkerStatus | "")}>
          <option value="">Alle Status</option>
          {(Object.keys(WORKER_STATUS_LABELS) as StaffingWorkerStatus[]).map((key) => <option key={key} value={key}>{WORKER_STATUS_LABELS[key]}</option>)}
        </select>
      </div>
      {error ? (
        <LoadError onRetry={() => void mutate()} />
      ) : isLoading || !data ? (
        <LoadingRows />
      ) : rows.length === 0 ? (
        <EmptyHint>{data.data.length === 0 ? "Noch keine Leiharbeitnehmer. Mit „Neuer Leiharbeitnehmer“ einen vorhandenen Kandidaten übernehmen." : "Keine Treffer zu diesem Filter."}</EmptyHint>
      ) : (
        <ul className="space-y-2">
          {rows.map((w) => (
            <li key={w.id}>
              <Link href={`/ueberlassung/leiharbeitnehmer/${w.id}`} className="flex flex-col gap-2 rounded-lg border border-white/10 p-3 transition-colors hover:bg-brand-hover/40 sm:flex-row sm:items-center sm:justify-between">
                <div className="min-w-0">
                  <p className="truncate text-sm font-medium">{w.candidate_name}{w.candidate_number ? <span className="text-brand-muted"> · Nr. {w.candidate_number}</span> : null}</p>
                  <p className="truncate text-xs text-brand-muted">{[w.pay_grade, w.weekly_hours ? `${formatHours(w.weekly_hours, { unit: "Std./Woche" })}` : null, w.entry_date ? `${w.status === "applicant" ? "Eintritt ab" : "seit"} ${formatDate(w.entry_date)}` : null].filter(Boolean).join(" · ") || "Keine Angaben"}</p>
                </div>
                <WorkerStatusBadge status={w.status} />
              </Link>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

// --- Anlegen -----------------------------------------------------------------------------------

export function StaffingWorkerCreateButton() {
  const [open, setOpen] = useState(false);
  const router = useRouter();
  return (
    <>
      <Button onClick={() => setOpen(true)}><Plus size={15} />Neuer Leiharbeitnehmer</Button>
      {open && (
        <WorkerCreateForm
          onClose={() => setOpen(false)}
          onCreated={(id) => { setOpen(false); router.push(`/ueberlassung/leiharbeitnehmer/${id}`); }}
        />
      )}
    </>
  );
}

function WorkerCreateForm({ initialCandidateId, onClose, onCreated }: {
  initialCandidateId?: string;
  onClose: () => void;
  onCreated: (id: string) => void;
}) {
  const { data: me } = useCurrentUser();
  const isAdmin = me?.data.is_admin ?? false;
  const [form, setForm] = useState({ candidate_id: initialCandidateId ?? "", entry_date: "", pay_grade: "", weekly_hours: "", work_permit_valid_until: "", hourly_wage: "" });
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
      if (!form.candidate_id) throw new Error("Bitte einen Kandidaten wählen.");
      const created = await createStaffingWorker({
        candidate_id: form.candidate_id,
        entry_date: form.entry_date || undefined,
        pay_grade: form.pay_grade || undefined,
        weekly_hours: form.weekly_hours ? form.weekly_hours.replace(",", ".") : undefined,
        work_permit_valid_until: form.work_permit_valid_until || undefined,
        ...(isAdmin && form.hourly_wage ? { hourly_wage: form.hourly_wage.replace(",", ".") } : {}),
      });
      await invalidateStaffing();
      onCreated(created.id);
    } catch (exception) {
      setError(exception instanceof Error ? exception.message : "Leiharbeitnehmer konnte nicht angelegt werden.");
    } finally {
      setBusy(false);
    }
  }
  return (
    <Modal title="Leiharbeitnehmer anlegen" eyebrow="Überlassung" onClose={onClose} maxWidth="max-w-xl">
      <form className="space-y-4" onSubmit={submit}>
        {!initialCandidateId && (
          <div>
            <label className={labelClass}>Kandidat *</label>
            <SearchSelect value={form.candidate_id} onChange={(value) => set("candidate_id", value)} onSearch={searchCandidates} placeholder="Kandidat suchen…" required />
            <p className="mt-1 text-xs text-brand-muted">Der Kandidat bleibt im gemeinsamen Pool und bekommt zusätzlich ein Überlassungsprofil.</p>
          </div>
        )}
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
          <div><label className={labelClass} htmlFor="sw-entry">Eintritt</label><Input id="sw-entry" type="date" value={form.entry_date} onChange={(e) => set("entry_date", e.target.value)} /></div>
          <div><label className={labelClass} htmlFor="sw-permit">Arbeitserlaubnis gültig bis</label><Input id="sw-permit" type="date" value={form.work_permit_valid_until} onChange={(e) => set("work_permit_valid_until", e.target.value)} /></div>
          <div><label className={labelClass} htmlFor="sw-grade">Tarif-/Entgeltgruppe</label><Input id="sw-grade" value={form.pay_grade} onChange={(e) => set("pay_grade", e.target.value)} /></div>
          <div><label className={labelClass} htmlFor="sw-hours">Wochenstunden</label><Input id="sw-hours" inputMode="decimal" value={form.weekly_hours} onChange={(e) => set("weekly_hours", e.target.value)} /></div>
          {isAdmin && <div><label className={labelClass} htmlFor="sw-wage">Stundenlohn €</label><Input id="sw-wage" inputMode="decimal" value={form.hourly_wage} onChange={(e) => set("hourly_wage", e.target.value)} /></div>}
        </div>
        <ErrorBanner message={error} />
        <div className="flex justify-end gap-2">
          <Button type="button" variant="outline" onClick={onClose}>Abbrechen</Button>
          <Button type="submit" disabled={busy}>{busy ? "Speichern…" : "Anlegen"}</Button>
        </div>
      </form>
    </Modal>
  );
}

/** Für den Reiter „Überlassung“ am Kandidaten: Anlegen mit festem Kandidaten. */
export function WorkerCreateFromCandidate({ candidateId, onCreated, onClose }: { candidateId: string; onCreated: (id: string) => void; onClose: () => void }) {
  return <WorkerCreateForm initialCandidateId={candidateId} onClose={onClose} onCreated={onCreated} />;
}

// --- Detail ------------------------------------------------------------------------------------

export function StaffingWorkerDetailView({ id }: { id: string }) {
  const { data, error, isLoading, mutate } = useStaffingWorker(id);
  const { data: deadlines } = useStaffingDeadlines();
  const { data: me } = useCurrentUser();
  const isAdmin = me?.data.is_admin ?? false;
  const [editing, setEditing] = useState(false);
  if (error) return <LoadError onRetry={() => void mutate()} />;
  if (isLoading || !data) return <LoadingRows />;
  const worker = data.data;
  if (!worker) return <p className="text-sm text-brand-muted">Leiharbeitnehmer nicht gefunden.</p>;
  const myDeadlines = (deadlines?.data ?? []).filter((d) => d.worker_id === worker.id);
  return (
    <div className="space-y-6">
      <div className="flex flex-col justify-between gap-3 sm:flex-row sm:items-start">
        <div className="min-w-0">
          <div className="mb-2 flex items-center gap-2"><WorkerStatusBadge status={worker.status} /></div>
          <h2 className="text-xl font-semibold tracking-[-.02em]">{worker.candidate_name}</h2>
          <Link href={`/kandidaten/${worker.candidate_id}?tab=Überlassung`} className="mt-1 inline-block text-xs text-brand-muted underline hover:text-brand-platinum">Zum Kandidatenprofil</Link>
        </div>
        <div className="flex flex-wrap gap-2">
          <Button size="sm" variant="outline" onClick={() => setEditing(true)}><Pencil size={14} />Bearbeiten</Button>
          {(worker.status === "active" || worker.status === "applicant") && <StaffingAssignmentCreateButton workerId={worker.id} />}
        </div>
      </div>
      <Card>
        <CardContent>
          <div className="grid grid-cols-1 gap-5 sm:grid-cols-2 lg:grid-cols-3">
            <Fact label="Eintritt">{worker.entry_date ? formatDate(worker.entry_date) : null}</Fact>
            <Fact label="Austritt">{worker.exit_date ? formatDate(worker.exit_date) : null}</Fact>
            <Fact label="Tarif-/Entgeltgruppe">{worker.pay_grade}</Fact>
            <Fact label="Wochenstunden">{worker.weekly_hours ? formatHours(worker.weekly_hours) : null}</Fact>
            <Fact label="Arbeitserlaubnis gültig bis">{worker.work_permit_valid_until ? formatDate(worker.work_permit_valid_until) : null}</Fact>
            {isAdmin && <Fact label="Stundenlohn">{formatMoney(worker.hourly_wage)}</Fact>}
          </div>
          {worker.notes && <p className="mt-5 whitespace-pre-line border-t border-white/10 pt-4 text-sm text-brand-soft">{worker.notes}</p>}
        </CardContent>
      </Card>
      {myDeadlines.length > 0 && (
        <section>
          <h3 className="mb-3 font-semibold">Fristen</h3>
          <div className="space-y-2">{myDeadlines.map((d) => <DeadlineRow key={d.client_company_id} deadline={d} />)}</div>
        </section>
      )}
      <section>
        <h3 className="mb-3 font-semibold">Einsätze</h3>
        <StaffingAssignmentsView workerId={worker.id} />
      </section>
      {editing && <WorkerEditModal worker={worker} isAdmin={isAdmin} onClose={() => setEditing(false)} />}
    </div>
  );
}

export function WorkerEditModal({ worker, isAdmin, onClose }: { worker: StaffingWorker; isAdmin: boolean; onClose: () => void }) {
  const [form, setForm] = useState({
    status: worker.status,
    entry_date: worker.entry_date ?? "",
    exit_date: worker.exit_date ?? "",
    pay_grade: worker.pay_grade ?? "",
    weekly_hours: worker.weekly_hours ?? "",
    work_permit_valid_until: worker.work_permit_valid_until ?? "",
    hourly_wage: worker.hourly_wage ?? "",
    notes: worker.notes ?? "",
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
      await updateStaffingWorker(worker.id, {
        status: form.status,
        entry_date: form.entry_date || null,
        exit_date: form.exit_date || null,
        pay_grade: form.pay_grade || null,
        weekly_hours: form.weekly_hours ? String(form.weekly_hours).replace(",", ".") : null,
        work_permit_valid_until: form.work_permit_valid_until || null,
        notes: form.notes || null,
        ...(isAdmin ? { hourly_wage: form.hourly_wage ? String(form.hourly_wage).replace(",", ".") : null } : {}),
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
    <Modal title="Leiharbeitnehmer bearbeiten" eyebrow="Überlassung" onClose={onClose} maxWidth="max-w-xl">
      <form className="space-y-4" onSubmit={submit}>
        <div>
          <label className={labelClass} htmlFor="we-status">Status</label>
          <select id="we-status" className={selectClass} value={form.status} onChange={(e) => set("status", e.target.value as StaffingWorkerStatus)}>
            {(Object.keys(WORKER_STATUS_LABELS) as StaffingWorkerStatus[]).map((key) => <option key={key} value={key}>{WORKER_STATUS_LABELS[key]}</option>)}
          </select>
        </div>
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
          <div><label className={labelClass} htmlFor="we-entry">Eintritt</label><Input id="we-entry" type="date" value={form.entry_date} onChange={(e) => set("entry_date", e.target.value)} /></div>
          <div><label className={labelClass} htmlFor="we-exit">Austritt</label><Input id="we-exit" type="date" min={form.entry_date || undefined} value={form.exit_date} onChange={(e) => set("exit_date", e.target.value)} /></div>
          <div><label className={labelClass} htmlFor="we-grade">Tarif-/Entgeltgruppe</label><Input id="we-grade" value={form.pay_grade} onChange={(e) => set("pay_grade", e.target.value)} /></div>
          <div><label className={labelClass} htmlFor="we-hours">Wochenstunden</label><Input id="we-hours" inputMode="decimal" value={form.weekly_hours} onChange={(e) => set("weekly_hours", e.target.value)} /></div>
          <div><label className={labelClass} htmlFor="we-permit">Arbeitserlaubnis gültig bis</label><Input id="we-permit" type="date" value={form.work_permit_valid_until} onChange={(e) => set("work_permit_valid_until", e.target.value)} /></div>
          {isAdmin && <div><label className={labelClass} htmlFor="we-wage">Stundenlohn €</label><Input id="we-wage" inputMode="decimal" value={form.hourly_wage} onChange={(e) => set("hourly_wage", e.target.value)} /></div>}
        </div>
        <div>
          <label className={labelClass} htmlFor="we-notes">Notizen</label>
          <textarea id="we-notes" rows={3} className="w-full rounded-md border border-white/10 bg-brand-surface px-3 py-2 text-sm text-brand-text outline-none focus:border-brand-accent" value={form.notes} onChange={(e) => set("notes", e.target.value)} />
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
