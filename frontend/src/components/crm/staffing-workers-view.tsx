"use client";

// NOMICON: Überlassung - Leiharbeitnehmer anlegen und bearbeiten. Es gibt keine eigene Personenliste und
// keine eigene Detailseite mehr: Leiharbeitnehmer sind Kandidaten (Kandidatenliste mit Überlassungsfilter,
// Reiter "Überlassung" am Kandidatenprofil). Diese Formulare benutzt der Reiter.
import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Modal } from "@/components/ui/modal";
import { SearchSelect } from "@/components/ui/search-select";
import { ErrorBanner } from "@/components/crm/error-banner";
import { searchCandidates } from "@/lib/api/search-select-helpers";
import { useCurrentUser } from "@/lib/api/hooks";
import { invalidateStaffing } from "@/lib/api/staffing-hooks";
import {
  WORKER_STATUS_LABELS,
  createStaffingWorker,
  updateStaffingWorker,
  type StaffingWorker,
  type StaffingWorkerStatus,
} from "@/lib/api/staffing";
import { labelClass, selectClass } from "./staffing-ui";

// --- Anlegen -----------------------------------------------------------------------------------

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

// --- Bearbeiten --------------------------------------------------------------------------------

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
