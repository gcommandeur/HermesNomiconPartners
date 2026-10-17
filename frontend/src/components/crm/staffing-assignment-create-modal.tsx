"use client";

// NOMICON: Überlassung - Einsatz anlegen.
import { useState } from "react";
import { useRouter } from "next/navigation";
import { Plus } from "lucide-react";
import { Modal } from "@/components/ui/modal";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { SearchSelect } from "@/components/ui/search-select";
import { ErrorBanner } from "@/components/crm/error-banner";
import { labelClass, selectClass } from "@/components/crm/staffing-ui";
import { searchClients } from "@/lib/api/search-select-helpers";
import { useAssignableUsersCache, useCurrentUser } from "@/lib/api/hooks";
import { useStaffingContracts, useStaffingPriorPeriods, useStaffingWorkers } from "@/lib/api/staffing-hooks";
import { createStaffingAssignment, type NewAssignmentInput } from "@/lib/api/staffing";
import { EngagementConflictNotice } from "@/components/crm/engagement-conflict-notice";
import { isEngagementConflict } from "@/lib/api/engagement";
import { invalidateStaffing } from "@/lib/api/staffing-hooks";

export function StaffingAssignmentCreateButton({ workerId }: { workerId?: string }) {
  const router = useRouter();
  const [open, setOpen] = useState(false);
  return (
    <>
      <Button onClick={() => setOpen(true)}><Plus size={15} />Neuer Einsatz</Button>
      {open && (
        <CreateForm
          workerId={workerId}
          onClose={() => setOpen(false)}
          onCreated={(id) => {
            setOpen(false);
            router.push(`/ueberlassung/einsaetze/${id}`);
          }}
        />
      )}
    </>
  );
}

function CreateForm({ workerId, onClose, onCreated }: { workerId?: string; onClose: () => void; onCreated: (id: string) => void }) {
  const { data: me } = useCurrentUser();
  const isAdmin = me?.data.is_admin ?? false;
  const { data: workersData } = useStaffingWorkers();
  const workers = (workersData?.data ?? []).filter((w) => w.status === "applicant" || w.status === "active");
  const { data: usersData } = useAssignableUsersCache();
  const users = usersData?.data ?? [];
  const [form, setForm] = useState({
    worker_id: workerId ?? "",
    client_company_id: "",
    contract_id: "",
    owner_user_id: "",
    start_date: "",
    planned_end_date: "",
    location: "",
    activity: "",
    billing_rate: "",
    hourly_wage: "",
  });
  const { data: contractsData } = useStaffingContracts(form.client_company_id || undefined);
  const contracts = form.client_company_id ? (contractsData?.data ?? []) : [];
  // Hinweis (kein Zwang): Vorzeiten beim Kunden zählen für die Höchstdauer mit.
  const { data: priorData } = useStaffingPriorPeriods(form.worker_id || null);
  const askForPriorPeriods =
    Boolean(form.worker_id && form.client_company_id) &&
    priorData !== undefined &&
    !priorData.data.some((period) => period.client_company_id === form.client_company_id);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [conflict, setConflict] = useState<string | null>(null);

  function set<K extends keyof typeof form>(key: K, value: (typeof form)[K]) {
    setForm((current) => ({ ...current, [key]: value }));
  }

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    await send(false);
  }

  async function send(confirmEngagement: boolean) {
    setBusy(true);
    setError(null);
    setConflict(null);
    try {
      if (!form.worker_id) throw new Error("Bitte einen Leiharbeitnehmer wählen.");
      if (!form.client_company_id) throw new Error("Bitte einen Kunden wählen.");
      const input: NewAssignmentInput = {
        worker_id: form.worker_id,
        client_company_id: form.client_company_id,
        start_date: form.start_date,
        contract_id: form.contract_id || undefined,
        owner_user_id: form.owner_user_id || undefined,
        planned_end_date: form.planned_end_date || undefined,
        location: form.location || undefined,
        activity: form.activity || undefined,
        // Lohn/Verrechnungssatz nur für Admins mitschicken (das Backend lehnt sie sonst ab).
        ...(isAdmin && form.billing_rate ? { billing_rate: form.billing_rate.replace(",", ".") } : {}),
        ...(isAdmin && form.hourly_wage ? { hourly_wage: form.hourly_wage.replace(",", ".") } : {}),
      };
      const created = await createStaffingAssignment(input, confirmEngagement);
      await invalidateStaffing();
      onCreated(created.id);
    } catch (exception) {
      const message = exception instanceof Error ? exception.message : "Einsatz konnte nicht angelegt werden.";
      if (isEngagementConflict(message) && !message.includes("gesperrt")) setConflict(message);
      else setError(message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <Modal title="Einsatz anlegen" eyebrow="Überlassung" onClose={onClose} maxWidth="max-w-xl">
      <form className="space-y-4" onSubmit={submit}>
        <div>
          <label className={labelClass} htmlFor="sa-worker">Leiharbeitnehmer *</label>
          <select id="sa-worker" required className={selectClass} value={form.worker_id} onChange={(e) => set("worker_id", e.target.value)} disabled={Boolean(workerId)}>
            <option value="" disabled>Leiharbeitnehmer wählen…</option>
            {workers.map((w) => <option key={w.id} value={w.id}>{w.candidate_name}</option>)}
          </select>
          {workers.length === 0 && <p className="mt-1 text-xs text-brand-muted">Noch kein Leiharbeitnehmer angelegt – zuerst unter „Leiharbeitnehmer“ oder am Kandidaten anlegen.</p>}
        </div>
        <div>
          <label className={labelClass}>Kunde *</label>
          <SearchSelect
            value={form.client_company_id}
            onChange={(value) => setForm((current) => ({ ...current, client_company_id: value, contract_id: "" }))}
            onSearch={searchClients}
            placeholder="Kunde suchen…"
            required
          />
        </div>
        {askForPriorPeriods && (
          <p className="rounded-md border border-white/10 bg-brand-surface p-3 text-xs text-brand-soft" role="note">
            Hat die Person schon früher bei diesem Kunden gearbeitet, auch über einen anderen Verleiher oder vor dem CRM-Start? Dann bitte zuerst am
            Leiharbeitnehmer unter „Vorzeiten beim Kunden“ eintragen – diese Zeiten zählen für Höchstdauer und Equal Pay mit.
          </p>
        )}
        {contracts.length > 0 && (
          <div>
            <label className={labelClass} htmlFor="sa-contract">Überlassungs-/Rahmenvertrag</label>
            <select id="sa-contract" className={selectClass} value={form.contract_id} onChange={(e) => set("contract_id", e.target.value)}>
              <option value="">Ohne Vertrag</option>
              {contracts.map((c) => <option key={c.id} value={c.id}>{c.contract_number ?? "ohne Nummer"} ({c.client_name})</option>)}
            </select>
          </div>
        )}
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
          <div><label className={labelClass} htmlFor="sa-start">Beginn *</label><Input id="sa-start" required type="date" value={form.start_date} onChange={(e) => set("start_date", e.target.value)} /></div>
          <div><label className={labelClass} htmlFor="sa-end">Geplantes Ende</label><Input id="sa-end" type="date" value={form.planned_end_date} min={form.start_date || undefined} onChange={(e) => set("planned_end_date", e.target.value)} /></div>
        </div>
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
          <div><label className={labelClass} htmlFor="sa-location">Einsatzort</label><Input id="sa-location" value={form.location} onChange={(e) => set("location", e.target.value)} /></div>
          <div><label className={labelClass} htmlFor="sa-activity">Tätigkeit</label><Input id="sa-activity" value={form.activity} onChange={(e) => set("activity", e.target.value)} /></div>
        </div>
        <div>
          <label className={labelClass} htmlFor="sa-owner">Disponent</label>
          <select id="sa-owner" className={selectClass} value={form.owner_user_id} onChange={(e) => set("owner_user_id", e.target.value)}>
            <option value="">Ich selbst</option>
            {users.map((u) => <option key={u.id} value={u.id}>{u.display_name ?? u.email}</option>)}
          </select>
        </div>
        {isAdmin && (
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
            <div><label className={labelClass} htmlFor="sa-rate">Verrechnungssatz €/Std.</label><Input id="sa-rate" inputMode="decimal" value={form.billing_rate} onChange={(e) => set("billing_rate", e.target.value)} /></div>
            <div><label className={labelClass} htmlFor="sa-wage">Lohn €/Std. (leer = vom Leiharbeitnehmer)</label><Input id="sa-wage" inputMode="decimal" value={form.hourly_wage} onChange={(e) => set("hourly_wage", e.target.value)} /></div>
          </div>
        )}
        <ErrorBanner message={error} />
        {conflict && <EngagementConflictNotice message={conflict} busy={busy} onConfirm={() => void send(true)} onCancel={() => setConflict(null)} />}
        <div className="flex justify-end gap-2">
          <Button type="button" variant="outline" onClick={onClose}>Abbrechen</Button>
          <Button type="submit" disabled={busy}>{busy ? "Speichern…" : "Einsatz anlegen"}</Button>
        </div>
      </form>
    </Modal>
  );
}
