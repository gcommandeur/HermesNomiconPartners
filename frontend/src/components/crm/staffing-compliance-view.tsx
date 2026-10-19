"use client";

// NOMICON: Überlassung - Compliance: AÜG-Erlaubnis, Fristen, einstellbare Rechtswerte.
import { useState } from "react";
import { Pencil, Plus } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Modal } from "@/components/ui/modal";
import { ErrorBanner } from "@/components/crm/error-banner";
import { useCurrentUser } from "@/lib/api/hooks";
import {
  invalidateStaffing,
  useStaffingDeadlines,
  useStaffingLicenses,
  useStaffingOverview,
  useStaffingSettings,
} from "@/lib/api/staffing-hooks";
import {
  createStaffingLicense,
  saveStaffingSettings,
  updateStaffingLicense,
  type StaffingLicense,
  type StaffingSettings,
} from "@/lib/api/staffing";
import { formatDate } from "@/lib/utils";
import { DeadlineRow } from "./staffing-overview-view";
import { StaffingTakeoverTiers } from "./staffing-takeover-tiers";
import { EmptyHint, LEGAL_NOTICE, LoadError, LoadingRows, TrafficBadge, labelClass } from "./staffing-ui";

export function StaffingComplianceView() {
  const { data: me } = useCurrentUser();
  const isAdmin = me?.data.is_admin ?? false;
  return (
    <div className="space-y-8">
      <LicenseSection isAdmin={isAdmin} />
      <DeadlineSection />
      <SettingsSection isAdmin={isAdmin} />
      <StaffingTakeoverTiers isAdmin={isAdmin} /> {/* NOMICON: Übernahme-Fee-Staffel */}
    </div>
  );
}

// --- Erlaubnis ---------------------------------------------------------------------------------

function LicenseSection({ isAdmin }: { isAdmin: boolean }) {
  const { data: overview } = useStaffingOverview();
  const { data, error, isLoading, mutate } = useStaffingLicenses();
  const [editing, setEditing] = useState<StaffingLicense | "new" | null>(null);
  const status = overview?.data.license;
  return (
    <section>
      <div className="mb-3 flex flex-wrap items-center justify-between gap-3">
        <div className="flex flex-wrap items-center gap-3">
          <h2 className="font-semibold">Erlaubnis zur Arbeitnehmerüberlassung</h2>
          {status && (
            <TrafficBadge
              traffic={status.traffic}
              label={!status.valid ? "Keine gültige Erlaubnis" : status.valid_to ? `gültig bis ${formatDate(status.valid_to)}` : "unbefristet gültig"}
            />
          )}
        </div>
        {isAdmin && <Button size="sm" onClick={() => setEditing("new")}><Plus size={14} />Erlaubnis eintragen</Button>}
      </div>
      {error ? (
        <LoadError onRetry={() => void mutate()} />
      ) : isLoading || !data ? (
        <LoadingRows rows={2} />
      ) : data.data.length === 0 ? (
        <EmptyHint>Noch keine Erlaubnis hinterlegt. Ohne gültige Erlaubnis kann kein Einsatz aktiviert werden.</EmptyHint>
      ) : (
        <ul className="space-y-2">
          {data.data.map((lic) => (
            <li key={lic.id} className="flex flex-col gap-2 rounded-lg border border-white/10 p-3 sm:flex-row sm:items-center sm:justify-between">
              <div className="min-w-0">
                <p className="truncate text-sm font-medium">{lic.authority}{lic.file_number ? ` · Az. ${lic.file_number}` : ""}</p>
                <p className="text-xs text-brand-muted">
                  {formatDate(lic.valid_from)} – {lic.valid_to ? formatDate(lic.valid_to) : "unbefristet"} · Erinnerung {lic.reminder_days} Tage vorher
                </p>
              </div>
              {isAdmin && <Button size="sm" variant="ghost" onClick={() => setEditing(lic)}><Pencil size={14} />Bearbeiten</Button>}
            </li>
          ))}
        </ul>
      )}
      {editing && <LicenseModal license={editing === "new" ? null : editing} onClose={() => setEditing(null)} />}
    </section>
  );
}

function LicenseModal({ license, onClose }: { license: StaffingLicense | null; onClose: () => void }) {
  const [form, setForm] = useState({
    authority: license?.authority ?? "Bundesagentur für Arbeit",
    file_number: license?.file_number ?? "",
    valid_from: license?.valid_from ?? "",
    valid_to: license?.valid_to ?? "",
    reminder_days: String(license?.reminder_days ?? 90),
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
      const body = {
        authority: form.authority,
        file_number: form.file_number || null,
        valid_from: form.valid_from,
        valid_to: form.valid_to || null,
        reminder_days: Number(form.reminder_days),
      };
      if (license) await updateStaffingLicense(license.id, body);
      else await createStaffingLicense(body);
      await invalidateStaffing();
      onClose();
    } catch (exception) {
      setError(exception instanceof Error ? exception.message : "Speichern fehlgeschlagen.");
    } finally {
      setBusy(false);
    }
  }
  return (
    <Modal title={license ? "Erlaubnis bearbeiten" : "Erlaubnis eintragen"} eyebrow="Compliance" onClose={onClose}>
      <form className="space-y-4" onSubmit={submit}>
        <div><label className={labelClass} htmlFor="li-auth">Behörde *</label><Input id="li-auth" required value={form.authority} onChange={(e) => set("authority", e.target.value)} /></div>
        <div><label className={labelClass} htmlFor="li-az">Aktenzeichen</label><Input id="li-az" value={form.file_number} onChange={(e) => set("file_number", e.target.value)} /></div>
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
          <div><label className={labelClass} htmlFor="li-from">Gültig ab *</label><Input id="li-from" type="date" required value={form.valid_from} onChange={(e) => set("valid_from", e.target.value)} /></div>
          <div><label className={labelClass} htmlFor="li-to">Gültig bis (leer = unbefristet)</label><Input id="li-to" type="date" min={form.valid_from || undefined} value={form.valid_to} onChange={(e) => set("valid_to", e.target.value)} /></div>
        </div>
        <div><label className={labelClass} htmlFor="li-rem">Erinnerung (Tage vor Ablauf)</label><Input id="li-rem" type="number" min={0} max={730} required value={form.reminder_days} onChange={(e) => set("reminder_days", e.target.value)} /></div>
        <ErrorBanner message={error} />
        <div className="flex justify-end gap-2">
          <Button type="button" variant="outline" onClick={onClose}>Abbrechen</Button>
          <Button type="submit" disabled={busy}>{busy ? "Speichern…" : "Speichern"}</Button>
        </div>
      </form>
    </Modal>
  );
}

// --- Fristen -----------------------------------------------------------------------------------

function DeadlineSection() {
  const { data, error, isLoading, mutate } = useStaffingDeadlines();
  return (
    <section>
      <h2 className="mb-3 font-semibold">Fristen je Leiharbeitnehmer und Kunde</h2>
      {error ? (
        <LoadError onRetry={() => void mutate()} />
      ) : isLoading || !data ? (
        <LoadingRows rows={2} />
      ) : data.data.length === 0 ? (
        <EmptyHint>Keine laufenden oder fortsetzbaren Überlassungen.</EmptyHint>
      ) : (
        <div className="space-y-2">{data.data.map((d) => <DeadlineRow key={`${d.worker_id}:${d.client_company_id}`} deadline={d} />)}</div>
      )}
    </section>
  );
}

// --- Einstellungen -----------------------------------------------------------------------------

type SettingsForm = Record<"max_months" | "equal_pay_months" | "reset_gap_months" | "yellow_days" | "red_days", string>;

const FIELDS: { key: keyof SettingsForm; label: string; hint: string }[] = [
  { key: "max_months", label: "Höchstüberlassungsdauer (Monate)", hint: "Standard 18" },
  { key: "equal_pay_months", label: "Equal Pay nach (Monaten)", hint: "Standard 9; gilt ab dem Folgetag" },
  { key: "reset_gap_months", label: "Unterbrechung, die den Zähler zurücksetzt (Monate)", hint: "Standard 3; gilt bei mehr als diesem Wert" },
  { key: "yellow_days", label: "Ampel gelb unter (Tagen Restlaufzeit)", hint: "Standard 60" },
  { key: "red_days", label: "Ampel rot unter (Tagen Restlaufzeit)", hint: "Standard 30; überschritten ist immer rot" },
];

function SettingsSection({ isAdmin }: { isAdmin: boolean }) {
  const { data, error, isLoading, mutate } = useStaffingSettings();
  if (error) return <LoadError onRetry={() => void mutate()} />;
  if (isLoading || !data) return <LoadingRows rows={2} />;
  return <SettingsCard settings={data.data} isAdmin={isAdmin} />;
}

function SettingsCard({ settings, isAdmin }: { settings: StaffingSettings; isAdmin: boolean }) {
  const initial: SettingsForm = {
    max_months: String(settings.max_months),
    equal_pay_months: String(settings.equal_pay_months),
    reset_gap_months: String(settings.reset_gap_months),
    yellow_days: String(settings.yellow_days),
    red_days: String(settings.red_days),
  };
  const [form, setForm] = useState(initial);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);
  async function submit(event: React.FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    setSaved(false);
    try {
      await saveStaffingSettings({
        max_months: Number(form.max_months),
        equal_pay_months: Number(form.equal_pay_months),
        reset_gap_months: Number(form.reset_gap_months),
        yellow_days: Number(form.yellow_days),
        red_days: Number(form.red_days),
      });
      await invalidateStaffing();
      setSaved(true);
    } catch (exception) {
      setError(exception instanceof Error ? exception.message : "Speichern fehlgeschlagen.");
    } finally {
      setBusy(false);
    }
  }
  return (
    <section>
      <div className="mb-3 flex flex-wrap items-center gap-3">
        <h2 className="font-semibold">Rechtliche Werte</h2>
        <Badge tone="amber">kein Rechtsrat</Badge>
      </div>
      <Card>
        <CardContent>
          <p className="mb-4 text-xs text-brand-muted">{settings.notice || LEGAL_NOTICE}</p>
          <form className="grid grid-cols-1 gap-4 sm:grid-cols-2" onSubmit={submit}>
            {FIELDS.map((field) => (
              <div key={field.key}>
                <label className={labelClass} htmlFor={`st-${field.key}`}>{field.label}</label>
                <Input
                  id={`st-${field.key}`}
                  type="number"
                  min={1}
                  required
                  disabled={!isAdmin}
                  value={form[field.key]}
                  onChange={(e) => { setSaved(false); setForm((current) => ({ ...current, [field.key]: e.target.value })); }}
                />
                <p className="mt-1 text-[10.45px] text-brand-dim">{field.hint}</p>
              </div>
            ))}
            <div className="sm:col-span-2">
              <ErrorBanner message={error} />
              {isAdmin ? (
                <div className="mt-3 flex items-center justify-end gap-3">
                  {saved && <span role="status" className="text-xs text-brand-success-text">Gespeichert.</span>}
                  <Button type="submit" disabled={busy}>{busy ? "Speichern…" : "Speichern"}</Button>
                </div>
              ) : (
                <p className="text-xs text-brand-muted">Nur Admins können diese Werte ändern.</p>
              )}
            </div>
          </form>
        </CardContent>
      </Card>
    </section>
  );
}
