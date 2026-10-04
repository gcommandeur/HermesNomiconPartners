"use client";

import { useCallback, useEffect, useState } from "react";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import {
  createMyMailAccount,
  deleteMyMailAccount,
  getMyMailAccounts,
  setMyDefaultSender,
  testMailConnection,
  testMyMailAccount,
  updateMyMailAccount,
} from "@/lib/api/queries";
import type { MailConnectionTestResult, MyMailAccount } from "@/lib/api/types";

const DEMO_MODE = process.env.NEXT_PUBLIC_CC_CRM_DEMO_MODE === "true";
const labelClass = "mb-1 block text-xs text-brand-muted";

const EMPTY_FORM = {
  address: "",
  label: "",
  imap_host: "",
  imap_port: "993",
  smtp_host: "",
  smtp_port: "587",
  smtp_use_ssl: false,
  username: "",
  password: "",
};

function TestResult({ result }: { result: MailConnectionTestResult }) {
  const line = (name: string, ok: boolean, error: string | null) => (
    <p className={ok ? "text-emerald-300" : "text-red-300"}>
      {name}: {ok ? "Anmeldung erfolgreich" : (error ?? "fehlgeschlagen")}
    </p>
  );
  return (
    <div className="mt-2 space-y-1 text-xs">
      {line("Eingang (IMAP)", result.imap_ok, result.imap_error)}
      {line("Ausgang (SMTP)", result.smtp_ok, result.smtp_error)}
    </div>
  );
}

/** Einstellungen → „Mein Postfach“: eigenes IMAP/SMTP-Postfach verbinden, testen und als
 * Standard-Absender setzen. Nur Versand ist Standard; der Posteingang wird nur auf Wunsch
 * abgerufen. Das Passwort (bei Gmail/Outlook/GMX ein App-Passwort) wird verschlüsselt
 * gespeichert und nie wieder angezeigt. */
export function MyMailAccountCard() {
  const [accounts, setAccounts] = useState<MyMailAccount[] | null>(null);
  const [adding, setAdding] = useState(false);
  const [form, setForm] = useState(EMPTY_FORM);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [results, setResults] = useState<Record<string, MailConnectionTestResult>>({});
  const [formResult, setFormResult] = useState<MailConnectionTestResult | null>(null);

  const load = useCallback(async () => {
    const result = await getMyMailAccounts();
    setAccounts(result.data);
  }, []);

  useEffect(() => {
    if (DEMO_MODE) return;
    void load();
  }, [load]);

  async function run(action: () => Promise<void>) {
    setBusy(true);
    setMessage(null);
    try {
      await action();
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Aktion fehlgeschlagen.");
    } finally {
      setBusy(false);
    }
  }

  const payloadFromForm = () => ({
    imap_host: form.imap_host.trim(),
    imap_port: Number(form.imap_port) || 993,
    imap_use_ssl: true,
    smtp_host: form.smtp_host.trim(),
    smtp_port: Number(form.smtp_port) || 587,
    smtp_use_ssl: form.smtp_use_ssl,
    username: form.username.trim() || form.address.trim(),
    password: form.password,
  });
  const set = (key: keyof typeof EMPTY_FORM, value: string | boolean) =>
    setForm((current) => ({ ...current, [key]: value }));
  const formComplete = form.address && form.imap_host && form.smtp_host && form.password;

  if (DEMO_MODE || accounts === null) return null;

  return (
    <Card className="mb-5">
      <CardContent className="space-y-4">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <p className="font-semibold">Mein Postfach</p>
            <p className="mt-1 max-w-2xl text-xs text-brand-muted">
              Verbinde dein eigenes E-Mail-Konto (IMAP/SMTP), damit Mailings und CV-Out-Mails aus deinem
              Postfach rausgehen. Es gehört nur dir – andere Nutzer und Admins können es weder nutzen noch lesen.
              Standardmäßig wird nur gesendet; der Posteingang wird nur auf Wunsch abgerufen.
            </p>
          </div>
          {!adding && (
            <Button size="sm" variant="outline" onClick={() => setAdding(true)}>
              Postfach hinzufügen
            </Button>
          )}
        </div>

        {accounts.map((account) => (
          <div key={account.id} className="rounded-lg border border-white/10 p-3">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <div className="min-w-0">
                <p className="text-sm font-medium">
                  {account.label} <span className="text-brand-muted">· {account.address}</span>
                </p>
                <p className="text-xs text-brand-muted">
                  {account.provider === "microsoft_graph" ? "Microsoft (Outlook)" : "IMAP/SMTP"}
                  {account.is_default_sender && " · Standard-Absender"}
                  {!account.is_active && " · deaktiviert"}
                  {account.sync_enabled ? " · Posteingang wird abgerufen" : " · nur Versand"}
                </p>
              </div>
              <div className="flex flex-wrap gap-2">
                {!account.is_default_sender && account.is_active && (
                  <Button
                    size="sm"
                    variant="outline"
                    disabled={busy}
                    onClick={() => void run(async () => { await setMyDefaultSender(account.id); await load(); })}
                  >
                    Als Standard
                  </Button>
                )}
                {account.provider === "imap_smtp" && (
                  <>
                    <Button
                      size="sm"
                      variant="outline"
                      disabled={busy}
                      onClick={() =>
                        void run(async () => {
                          const result = await testMyMailAccount(account.id);
                          setResults((current) => ({ ...current, [account.id]: result }));
                        })
                      }
                    >
                      Testen
                    </Button>
                    <Button
                      size="sm"
                      variant="outline"
                      disabled={busy}
                      onClick={() =>
                        void run(async () => {
                          await updateMyMailAccount(account.id, { sync_enabled: !account.sync_enabled });
                          await load();
                        })
                      }
                    >
                      {account.sync_enabled ? "Abruf ausschalten" : "Posteingang abrufen"}
                    </Button>
                    <Button
                      size="sm"
                      variant="outline"
                      disabled={busy}
                      onClick={() =>
                        void run(async () => {
                          if (!window.confirm(`Postfach „${account.label}“ entfernen?`)) return;
                          await deleteMyMailAccount(account.id);
                          await load();
                        })
                      }
                    >
                      Entfernen
                    </Button>
                  </>
                )}
              </div>
            </div>
            {account.sync_enabled && account.provider === "imap_smtp" && (
              <p className="mt-2 text-xs text-amber-200/80">
                Mails mit Kandidaten und Kontakten erscheinen in deren Verlauf – für alle sichtbar.
              </p>
            )}
            {results[account.id] && <TestResult result={results[account.id]} />}
          </div>
        ))}
        {accounts.length === 0 && !adding && <p className="text-xs text-brand-muted">Noch kein eigenes Postfach.</p>}

        {adding && (
          <div className="space-y-3 rounded-lg border border-white/10 p-3">
            <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
              <div>
                <label className={labelClass}>E-Mail-Adresse *</label>
                <Input type="email" value={form.address} onChange={(e) => set("address", e.target.value)} />
              </div>
              <div>
                <label className={labelClass}>Bezeichnung *</label>
                <Input placeholder="z. B. Lukas" value={form.label} onChange={(e) => set("label", e.target.value)} />
              </div>
              <div>
                <label className={labelClass}>IMAP-Server (Eingang) *</label>
                <Input placeholder="imap.beispiel.de" value={form.imap_host} onChange={(e) => set("imap_host", e.target.value)} />
              </div>
              <div>
                <label className={labelClass}>IMAP-Port</label>
                <Input value={form.imap_port} onChange={(e) => set("imap_port", e.target.value)} />
              </div>
              <div>
                <label className={labelClass}>SMTP-Server (Ausgang) *</label>
                <Input placeholder="smtp.beispiel.de" value={form.smtp_host} onChange={(e) => set("smtp_host", e.target.value)} />
              </div>
              <div>
                <label className={labelClass}>SMTP-Port (587 = STARTTLS, 465 = SSL)</label>
                <Input
                  value={form.smtp_port}
                  onChange={(e) => {
                    set("smtp_port", e.target.value);
                    set("smtp_use_ssl", e.target.value.trim() === "465");
                  }}
                />
              </div>
              <div>
                <label className={labelClass}>Benutzername (leer = E-Mail-Adresse)</label>
                <Input value={form.username} onChange={(e) => set("username", e.target.value)} />
              </div>
              <div>
                <label className={labelClass}>Passwort / App-Passwort *</label>
                <Input type="password" autoComplete="new-password" value={form.password} onChange={(e) => set("password", e.target.value)} />
              </div>
            </div>
            <p className="text-xs text-brand-muted">
              Bei Gmail, Outlook.com, GMX u. a. ist ein <strong>App-Passwort</strong> nötig (nicht das normale
              Passwort). Es wird verschlüsselt gespeichert und nie wieder angezeigt.
            </p>
            {formResult && <TestResult result={formResult} />}
            {message && <p className="text-xs text-red-300">{message}</p>}
            <div className="flex flex-wrap gap-2">
              <Button
                size="sm"
                variant="outline"
                disabled={busy || !formComplete}
                onClick={() =>
                  void run(async () => {
                    setFormResult(await testMailConnection(payloadFromForm()));
                  })
                }
              >
                Verbindung testen
              </Button>
              <Button
                size="sm"
                disabled={busy || !formComplete || !form.label.trim()}
                onClick={() =>
                  void run(async () => {
                    await createMyMailAccount({
                      address: form.address.trim(),
                      label: form.label.trim(),
                      ...payloadFromForm(),
                    });
                    setForm(EMPTY_FORM);
                    setFormResult(null);
                    setAdding(false);
                    await load();
                  })
                }
              >
                Speichern
              </Button>
              <Button size="sm" variant="outline" disabled={busy} onClick={() => { setAdding(false); setFormResult(null); setMessage(null); }}>
                Abbrechen
              </Button>
            </div>
          </div>
        )}
        {!adding && message && <p className="text-xs text-red-300">{message}</p>}
      </CardContent>
    </Card>
  );
}
