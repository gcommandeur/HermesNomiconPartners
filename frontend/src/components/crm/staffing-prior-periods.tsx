"use client";

// NOMICON: Überlassung - Vorzeiten beim Kunden (früher geleistete Überlassungszeiten, z. B. über
// einen anderen Verleiher oder vor dem CRM-Start). Sie zählen in Höchstdauer und Equal Pay mit.
import { useState } from "react";
import { Check, Pencil, Plus, Trash2 } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Modal } from "@/components/ui/modal";
import { SearchSelect } from "@/components/ui/search-select";
import { ErrorBanner } from "@/components/crm/error-banner";
import { searchClients } from "@/lib/api/search-select-helpers";
import { invalidateStaffing, useStaffingPriorConfirmations, useStaffingPriorPeriods } from "@/lib/api/staffing-hooks";
import {
  PRIOR_SOURCE_LABELS,
  confirmNoPriorPeriods,
  createStaffingPriorPeriod,
  deleteStaffingPriorPeriod,
  updateStaffingPriorPeriod,
  withdrawNoPriorPeriods,
  type StaffingPriorPeriod,
  type StaffingPriorPeriodSource,
} from "@/lib/api/staffing";
import { formatDate } from "@/lib/utils";
import { EmptyHint, LoadError, LoadingRows, labelClass, selectClass } from "./staffing-ui";

export function StaffingPriorPeriodsSection({ workerId }: { workerId: string }) {
  const { data, error, isLoading, mutate } = useStaffingPriorPeriods(workerId);
  const { data: confirmations } = useStaffingPriorConfirmations(workerId);
  const [editing, setEditing] = useState<StaffingPriorPeriod | "new" | null>(null);
  const [confirming, setConfirming] = useState(false);
  const [removing, setRemoving] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);

  async function remove(id: string) {
    setActionError(null);
    try {
      await deleteStaffingPriorPeriod(id);
      await invalidateStaffing();
    } catch (exception) {
      setActionError(exception instanceof Error ? exception.message : "Entfernen fehlgeschlagen.");
    } finally {
      setRemoving(null);
    }
  }

  async function withdraw(clientCompanyId: string) {
    setActionError(null);
    try {
      await withdrawNoPriorPeriods(workerId, clientCompanyId);
      await invalidateStaffing();
    } catch (exception) {
      setActionError(exception instanceof Error ? exception.message : "Zurücknehmen fehlgeschlagen.");
    }
  }

  return (
    <section>
      <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
        <div>
          <h3 className="font-semibold">Vorzeiten beim Kunden</h3>
          <p className="text-xs text-brand-muted">
            Früher beim selben Kunden geleistete Zeiten (auch über einen anderen Verleiher oder vor dem CRM-Start). Sie zählen in
            Höchstdauer und Equal Pay mit – Annahme, kein Rechtsrat.
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          <Button size="sm" variant="outline" onClick={() => setConfirming(true)}><Check size={14} />Keine Vorzeiten bestätigen</Button>
          <Button size="sm" variant="outline" onClick={() => setEditing("new")}><Plus size={14} />Vorzeit hinzufügen</Button>
        </div>
      </div>
      <ErrorBanner message={actionError} />
      {error ? (
        <LoadError onRetry={() => void mutate()} />
      ) : isLoading || !data ? (
        <LoadingRows rows={1} />
      ) : data.data.length === 0 ? (
        <EmptyHint>Keine Vorzeiten erfasst.</EmptyHint>
      ) : (
        <ul className="space-y-2">
          {data.data.map((period) => (
            <li key={period.id} className="flex flex-col gap-2 rounded-lg border border-white/10 p-3 sm:flex-row sm:items-center sm:justify-between">
              <div className="min-w-0">
                <p className="truncate text-sm font-medium">{period.client_name}</p>
                <p className="truncate text-xs text-brand-muted">
                  {formatDate(period.start_date)} – {formatDate(period.end_date)}
                  {period.note ? ` · ${period.note}` : ""}
                </p>
              </div>
              <div className="flex flex-wrap items-center gap-2">
                <Badge tone="gray">{PRIOR_SOURCE_LABELS[period.source]}</Badge>
                <Button size="sm" variant="outline" aria-label={`Vorzeit bei ${period.client_name} bearbeiten`} onClick={() => setEditing(period)}><Pencil size={14} /></Button>
                {removing === period.id ? (
                  <>
                    <Button size="sm" variant="outline" onClick={() => void remove(period.id)}>Wirklich entfernen</Button>
                    <Button size="sm" variant="outline" onClick={() => setRemoving(null)}>Abbrechen</Button>
                  </>
                ) : (
                  <Button size="sm" variant="outline" aria-label={`Vorzeit bei ${period.client_name} entfernen`} onClick={() => setRemoving(period.id)}><Trash2 size={14} /></Button>
                )}
              </div>
            </li>
          ))}
        </ul>
      )}
      {(confirmations?.data.length ?? 0) > 0 && (
        <ul className="mt-3 space-y-2" aria-label="Bestätigte Keine-Vorzeiten">
          {confirmations?.data.map((item) => (
            <li key={item.id} className="flex flex-col gap-2 rounded-lg border border-white/10 p-3 sm:flex-row sm:items-center sm:justify-between">
              <p className="text-sm">
                <span className="font-medium">{item.client_name}</span>: keine Vorzeiten – bestätigt am {formatDate(item.confirmed_on)}
                {item.confirmed_by_name ? ` von ${item.confirmed_by_name}` : ""}
                {item.note ? ` · ${item.note}` : ""}
              </p>
              <Button size="sm" variant="outline" onClick={() => void withdraw(item.client_company_id)}>Zurücknehmen</Button>
            </li>
          ))}
        </ul>
      )}
      {confirming && <NoPriorModal workerId={workerId} onClose={() => setConfirming(false)} />}
      {editing && <PriorPeriodModal workerId={workerId} period={editing === "new" ? null : editing} onClose={() => setEditing(null)} />}
    </section>
  );
}

function PriorPeriodModal({ workerId, period, onClose }: { workerId: string; period: StaffingPriorPeriod | null; onClose: () => void }) {
  const today = new Date().toISOString().slice(0, 10);
  const [form, setForm] = useState({
    client_company_id: period?.client_company_id ?? "",
    start_date: period?.start_date ?? "",
    end_date: period?.end_date ?? "",
    source: (period?.source ?? "other_provider") as StaffingPriorPeriodSource,
    note: period?.note ?? "",
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
      if (!period && !form.client_company_id) throw new Error("Bitte einen Kunden wählen.");
      const common = { start_date: form.start_date, end_date: form.end_date, source: form.source, note: form.note || null };
      if (period) await updateStaffingPriorPeriod(period.id, common);
      else await createStaffingPriorPeriod(workerId, { client_company_id: form.client_company_id, ...common });
      await invalidateStaffing();
      onClose();
    } catch (exception) {
      setError(exception instanceof Error ? exception.message : "Speichern fehlgeschlagen.");
    } finally {
      setBusy(false);
    }
  }
  return (
    <Modal title={period ? "Vorzeit bearbeiten" : "Vorzeit hinzufügen"} eyebrow="Überlassung" onClose={onClose} maxWidth="max-w-xl">
      <form className="space-y-4" onSubmit={submit}>
        <div>
          <label className={labelClass}>Kunde *</label>
          {period ? (
            <p className="text-sm">{period.client_name}</p>
          ) : (
            <SearchSelect value={form.client_company_id} onChange={(value) => set("client_company_id", value)} onSearch={searchClients} placeholder="Kunde suchen…" required />
          )}
          {period && <p className="mt-1 text-xs text-brand-muted">Der Kunde lässt sich nicht ändern – bei falschem Kunden die Vorzeit entfernen und neu anlegen.</p>}
        </div>
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
          <div><label className={labelClass} htmlFor="pp-start">Beginn *</label><Input id="pp-start" required type="date" max={today} value={form.start_date} onChange={(e) => set("start_date", e.target.value)} /></div>
          <div><label className={labelClass} htmlFor="pp-end">Ende *</label><Input id="pp-end" required type="date" min={form.start_date || undefined} max={today} value={form.end_date} onChange={(e) => set("end_date", e.target.value)} /></div>
        </div>
        <div>
          <label className={labelClass} htmlFor="pp-source">Herkunft</label>
          <select id="pp-source" className={selectClass} value={form.source} onChange={(e) => set("source", e.target.value as StaffingPriorPeriodSource)}>
            {(Object.keys(PRIOR_SOURCE_LABELS) as StaffingPriorPeriodSource[]).map((key) => <option key={key} value={key}>{PRIOR_SOURCE_LABELS[key]}</option>)}
          </select>
        </div>
        <div>
          <label className={labelClass} htmlFor="pp-note">Notiz (z. B. Quelle des Nachweises)</label>
          <Input id="pp-note" value={form.note} onChange={(e) => set("note", e.target.value)} maxLength={2000} />
        </div>
        <p className="text-xs text-brand-muted">Vorzeiten sind abgeschlossene Zeiträume. Laufende Zeiten gehören in einen Einsatz.</p>
        <ErrorBanner message={error} />
        <div className="flex justify-end gap-2">
          <Button type="button" variant="outline" onClick={onClose}>Abbrechen</Button>
          <Button type="submit" disabled={busy}>{busy ? "Speichern…" : "Speichern"}</Button>
        </div>
      </form>
    </Modal>
  );
}


function NoPriorModal({ workerId, onClose }: { workerId: string; onClose: () => void }) {
  const today = new Date().toISOString().slice(0, 10);
  const [form, setForm] = useState({ client_company_id: "", confirmed_on: today, note: "" });
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  async function submit(event: React.FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      if (!form.client_company_id) throw new Error("Bitte einen Kunden wählen.");
      await confirmNoPriorPeriods(workerId, { client_company_id: form.client_company_id, confirmed_on: form.confirmed_on || null, note: form.note || null });
      await invalidateStaffing();
      onClose();
    } catch (exception) {
      setError(exception instanceof Error ? exception.message : "Bestätigen fehlgeschlagen.");
    } finally {
      setBusy(false);
    }
  }
  return (
    <Modal title="Keine Vorzeiten bestätigen" eyebrow="Überlassung" onClose={onClose} maxWidth="max-w-xl">
      <form className="space-y-4" onSubmit={submit}>
        <p className="text-sm text-brand-muted">
          Sie bestätigen, dass diese Person vor dem ersten Einsatz bei diesem Kunden dort nie überlassen war (auch nicht über einen anderen
          Verleiher). Datum und Ihr Name werden festgehalten. Ohne diese Bestätigung bleibt die Frist „vorläufig“.
        </p>
        <div>
          <label className={labelClass}>Kunde *</label>
          <SearchSelect value={form.client_company_id} onChange={(value) => setForm((c) => ({ ...c, client_company_id: value }))} onSearch={searchClients} placeholder="Kunde suchen…" required />
        </div>
        <div><label className={labelClass} htmlFor="np-date">Geprüft am *</label><Input id="np-date" required type="date" max={today} value={form.confirmed_on} onChange={(e) => setForm((c) => ({ ...c, confirmed_on: e.target.value }))} /></div>
        <div><label className={labelClass} htmlFor="np-note">Notiz (z. B. Nachweis)</label><Input id="np-note" value={form.note} onChange={(e) => setForm((c) => ({ ...c, note: e.target.value }))} maxLength={2000} /></div>
        <ErrorBanner message={error} />
        <div className="flex justify-end gap-2">
          <Button type="button" variant="outline" onClick={onClose}>Abbrechen</Button>
          <Button type="submit" disabled={busy}>{busy ? "Bestätigen…" : "Keine Vorzeiten bestätigen"}</Button>
        </div>
      </form>
    </Modal>
  );
}
