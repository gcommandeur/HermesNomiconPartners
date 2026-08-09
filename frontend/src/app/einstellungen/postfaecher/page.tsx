"use client";

import { useState } from "react";
import { AlertTriangle, Mail, Plus, RefreshCw, ShieldOff, Star, Trash2 } from "lucide-react";
import { PageHeader } from "@/components/crm/page-header";
import { ErrorBanner } from "@/components/crm/error-banner";
import { ErrorState } from "@/components/crm/error-state";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader } from "@/components/ui/card";
import { apiDelete, apiPatch, apiPost } from "@/lib/api/client";
import {
  invalidateMailAccountsCache,
  useCurrentUser,
  useMailAccountsCache,
} from "@/lib/api/hooks";
import type { MailAccount, MailSyncResult } from "@/lib/api/types";

const EMPTY_FORM = {
  address: "",
  label: "",
  imap_host: "",
  imap_port: "993",
  smtp_host: "",
  smtp_port: "587",
  username: "",
  password: "",
};

function formatDateTime(value: string | null): string {
  if (!value) return "noch nie";
  return new Date(value).toLocaleString("de-DE", { dateStyle: "short", timeStyle: "short" });
}

export default function PostfaecherPage() {
  const { data: meData, isLoading: meLoading } = useCurrentUser();
  const isAdmin = meData?.data.is_admin ?? false;
  const { data, isLoading, error, mutate: retry } = useMailAccountsCache(isAdmin);
  const accounts = data?.data ?? [];

  const [form, setForm] = useState({ ...EMPTY_FORM });
  const [showForm, setShowForm] = useState(false);
  const [saving, setSaving] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);
  const [rowError, setRowError] = useState<string | null>(null);
  const [busyId, setBusyId] = useState<string | null>(null);
  // Ergebnis des letzten manuellen Abrufs je Postfach - bleibt stehen, bis
  // erneut abgerufen wird, damit der Grund eines Fehlschlags lesbar ist.
  const [syncResults, setSyncResults] = useState<Record<string, MailSyncResult>>({});

  function set<K extends keyof typeof form>(key: K, value: string) {
    setForm((current) => ({ ...current, [key]: value }));
  }

  async function refresh() {
    await Promise.all([retry(), invalidateMailAccountsCache()]);
  }

  async function handleCreate(event: React.FormEvent) {
    event.preventDefault();
    setSaving(true);
    setFormError(null);
    try {
      await apiPost("/mail-accounts", {
        ...form,
        imap_port: Number(form.imap_port),
        smtp_port: Number(form.smtp_port),
      });
      setForm({ ...EMPTY_FORM });
      setShowForm(false);
      await refresh();
    } catch (exception) {
      setFormError(exception instanceof Error ? exception.message : "Anlegen fehlgeschlagen.");
    } finally {
      setSaving(false);
    }
  }

  async function patchAccount(account: MailAccount, body: Record<string, unknown>) {
    setBusyId(account.id);
    setRowError(null);
    try {
      await apiPatch(`/mail-accounts/${account.id}`, body);
      await refresh();
    } catch (exception) {
      setRowError(exception instanceof Error ? exception.message : "Änderung fehlgeschlagen.");
    } finally {
      setBusyId(null);
    }
  }

  async function handleSync(account: MailAccount) {
    setBusyId(account.id);
    setRowError(null);
    try {
      const result = await apiPost<MailSyncResult>(
        `/mail-accounts/${account.id}/sync`,
        {},
        // Ein erster Abruf holt bis zu 200 Mails - deutlich laenger als eine
        // normale JSON-Anfrage.
        120_000,
      );
      setSyncResults((current) => ({ ...current, [account.id]: result }));
      await refresh();
    } catch (exception) {
      setRowError(exception instanceof Error ? exception.message : "Abruf fehlgeschlagen.");
    } finally {
      setBusyId(null);
    }
  }

  async function handleDelete(account: MailAccount) {
    if (!window.confirm(`Postfach ${account.address} wirklich entfernen?`)) return;
    setBusyId(account.id);
    setRowError(null);
    try {
      await apiDelete(`/mail-accounts/${account.id}`);
      await refresh();
    } catch (exception) {
      setRowError(exception instanceof Error ? exception.message : "Entfernen fehlgeschlagen.");
    } finally {
      setBusyId(null);
    }
  }

  if (meLoading) {
    return (
      <div className="space-y-2">
        {Array.from({ length: 3 }).map((_, index) => (
          <div key={index} className="h-16 animate-pulse rounded-lg bg-[#0D1B2E]" />
        ))}
      </div>
    );
  }

  if (!isAdmin) {
    return (
      <>
        <PageHeader eyebrow="Hermes" title="E-Mails & Konten" />
        <Card>
          <CardContent className="flex flex-col items-center gap-3 py-16 text-center">
            <ShieldOff size={28} className="text-[#747C89]" />
            <p className="text-sm text-[#94A3B8]">
              Diese Seite ist Administratoren vorbehalten - hier liegen die Zugangsdaten aller
              Firmen-Postfächer.
            </p>
          </CardContent>
        </Card>
      </>
    );
  }

  if (error) {
    return (
      <>
        <PageHeader eyebrow="Hermes" title="E-Mails & Konten" />
        <ErrorState onRetry={() => void retry()} />
      </>
    );
  }

  return (
    <>
      <PageHeader eyebrow="Hermes" title="E-Mails & Konten" />

      <div className="space-y-5">
        <Card>
          <CardHeader>
            <div className="flex flex-wrap items-start justify-between gap-3">
              <div>
                <h2 className="font-semibold">Verbundene Postfächer</h2>
                <p className="mt-1 text-xs text-[#94A3B8]">
                  Eingehende Mails werden Kandidat:innen und Kanzlei-Kontakten zugeordnet und in
                  der Timeline abgelegt. Passwörter werden verschlüsselt gespeichert und nie
                  wieder angezeigt.
                </p>
              </div>
              <Button size="sm" variant="outline" onClick={() => setShowForm((open) => !open)}>
                <Plus size={14} />
                {showForm ? "Abbrechen" : "Postfach verbinden"}
              </Button>
            </div>
          </CardHeader>

          <CardContent className="space-y-4">
            <ErrorBanner message={rowError} />

            {showForm && (
              <form
                onSubmit={handleCreate}
                className="rounded-lg border border-white/10 bg-[#071426] p-4"
              >
                <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
                  <Field label="E-Mail-Adresse *">
                    <input
                      required
                      type="email"
                      value={form.address}
                      onChange={(e) => set("address", e.target.value)}
                      placeholder="info@commandeurconsulting.de"
                      className={inputClass}
                    />
                  </Field>
                  <Field label="Bezeichnung *">
                    <input
                      required
                      value={form.label}
                      onChange={(e) => set("label", e.target.value)}
                      placeholder="info-linkedin"
                      className={inputClass}
                    />
                  </Field>
                  <Field label="IMAP-Server *">
                    <input
                      required
                      value={form.imap_host}
                      onChange={(e) => set("imap_host", e.target.value)}
                      className={inputClass}
                    />
                  </Field>
                  <Field label="IMAP-Port">
                    <input
                      value={form.imap_port}
                      onChange={(e) => set("imap_port", e.target.value)}
                      inputMode="numeric"
                      className={inputClass}
                    />
                  </Field>
                  <Field label="SMTP-Server *">
                    <input
                      required
                      value={form.smtp_host}
                      onChange={(e) => set("smtp_host", e.target.value)}
                      className={inputClass}
                    />
                  </Field>
                  <Field label="SMTP-Port">
                    <input
                      value={form.smtp_port}
                      onChange={(e) => set("smtp_port", e.target.value)}
                      inputMode="numeric"
                      className={inputClass}
                    />
                  </Field>
                  <Field label="Benutzername *">
                    <input
                      required
                      value={form.username}
                      onChange={(e) => set("username", e.target.value)}
                      className={inputClass}
                    />
                  </Field>
                  <Field label="Passwort *">
                    <input
                      required
                      type="password"
                      value={form.password}
                      onChange={(e) => set("password", e.target.value)}
                      autoComplete="new-password"
                      className={inputClass}
                    />
                  </Field>
                </div>
                <ErrorBanner message={formError} className="mt-3" />
                <Button type="submit" size="sm" className="mt-3" disabled={saving}>
                  {saving ? "Wird verbunden…" : "Postfach verbinden"}
                </Button>
              </form>
            )}

            {isLoading && accounts.length === 0 && (
              <div className="space-y-2">
                {Array.from({ length: 2 }).map((_, index) => (
                  <div key={index} className="h-20 animate-pulse rounded-lg bg-[#0D1B2E]" />
                ))}
              </div>
            )}

            {!isLoading && accounts.length === 0 && (
              <div className="flex flex-col items-center gap-2 py-10 text-center">
                <Mail size={24} className="text-[#747C89]" />
                <p className="text-sm text-[#94A3B8]">Noch kein Postfach verbunden.</p>
              </div>
            )}

            {accounts.map((account) => {
              const result = syncResults[account.id];
              const busy = busyId === account.id;
              return (
                <div
                  key={account.id}
                  className="rounded-lg border border-white/10 bg-[#0D1B2E]/60 p-4"
                >
                  <div className="flex flex-wrap items-start justify-between gap-3">
                    <div className="min-w-0">
                      <p className="flex flex-wrap items-center gap-2 font-medium text-[#F8FAFC]">
                        {account.address}
                        <span className="rounded bg-[#12243A] px-2 py-0.5 text-[10px] uppercase tracking-wider text-[#94A3B8]">
                          {account.label}
                        </span>
                        {account.default_for_cv_out && (
                          <span className="flex items-center gap-1 rounded bg-[#1F5FA8]/25 px-2 py-0.5 text-[10px] text-[#69A7EA]">
                            <Star size={10} />CV-OUT-Standard
                          </span>
                        )}
                        {!account.is_active && (
                          <span className="rounded bg-[#3A2416] px-2 py-0.5 text-[10px] text-[#F0B429]">
                            inaktiv
                          </span>
                        )}
                      </p>
                      <p className="mt-1 text-xs text-[#747C89]">
                        IMAP {account.imap_host}:{account.imap_port} · SMTP {account.smtp_host}:
                        {account.smtp_port} · zuletzt abgerufen: {formatDateTime(account.last_synced_at)}
                      </p>
                    </div>

                    <div className="flex flex-wrap gap-2">
                      <Button
                        size="sm"
                        variant="outline"
                        onClick={() => void handleSync(account)}
                        disabled={busy}
                      >
                        <RefreshCw size={13} />
                        {busy ? "Läuft…" : "Jetzt abrufen"}
                      </Button>
                      <Button
                        size="sm"
                        variant="outline"
                        onClick={() =>
                          void patchAccount(account, { default_for_cv_out: !account.default_for_cv_out })
                        }
                        disabled={busy}
                      >
                        <Star size={13} />
                        {account.default_for_cv_out ? "Standard aufheben" : "Als CV-OUT-Standard"}
                      </Button>
                      <Button
                        size="sm"
                        variant="outline"
                        onClick={() => void patchAccount(account, { is_active: !account.is_active })}
                        disabled={busy}
                      >
                        {account.is_active ? "Deaktivieren" : "Aktivieren"}
                      </Button>
                      <Button
                        size="sm"
                        variant="outline"
                        onClick={() => void handleDelete(account)}
                        disabled={busy}
                      >
                        <Trash2 size={13} />
                      </Button>
                    </div>
                  </div>

                  {/* Fehler des letzten Abrufs - laut Nutzer-Vorgabe muss
                      erkennbar sein, ob es an den Zugangsdaten oder an
                      etwas anderem lag. */}
                  {(account.sync_error || result?.error) && (
                    <div className="mt-3 flex gap-2 rounded-md border border-[#F0B429]/30 bg-[#3A2416]/40 p-3">
                      <AlertTriangle size={14} className="mt-0.5 shrink-0 text-[#F0B429]" />
                      <div className="min-w-0">
                        <p className="text-xs font-semibold text-[#F0B429]">
                          Letzter Abruf fehlgeschlagen
                        </p>
                        <p className="mt-1 break-words font-mono text-[11px] text-[#D8DADF]">
                          {result?.error ?? account.sync_error}
                        </p>
                      </div>
                    </div>
                  )}

                  {result?.ok && (
                    <p className="mt-3 rounded-md border border-[#1F5FA8]/30 bg-[#102A4C]/50 p-2.5 text-xs text-[#69A7EA]">
                      {result.fetched} neue Mail(s) · {result.created_activities} Aktivität(en)
                      angelegt · {result.pending_review} zur Prüfung · {result.skipped_duplicates}{" "}
                      bereits bekannt
                      {result.failed_messages > 0 && ` · ${result.failed_messages} fehlerhaft`}
                    </p>
                  )}
                </div>
              );
            })}
          </CardContent>
        </Card>
      </div>
    </>
  );
}

const inputClass =
  "h-10 w-full rounded-md border border-white/10 bg-[#0D1B2E] px-3 text-xs text-[#F8FAFC] outline-none focus:border-[#1F5FA8]";

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div>
      <label className="mb-1 block text-xs text-[#94A3B8]">{label}</label>
      {children}
    </div>
  );
}
