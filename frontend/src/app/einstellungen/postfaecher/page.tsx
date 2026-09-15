"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import {
  AlertTriangle,
  ChevronDown,
  ChevronRight,
  Linkedin,
  Mail,
  Plus,
  RefreshCw,
  ShieldOff,
  Star,
  Trash2,
  Unplug,
} from "lucide-react";
import { PageHeader } from "@/components/crm/page-header";
import { ErrorBanner } from "@/components/crm/error-banner";
import { ErrorState } from "@/components/crm/error-state";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader } from "@/components/ui/card";
import { apiDelete, apiPatch, apiPost } from "@/lib/api/client";
import { getMailMessages, startMicrosoftOAuth } from "@/lib/api/queries";
import {
  invalidateMailAccountsCache,
  useCurrentUser,
  useMailAccountsCache,
} from "@/lib/api/hooks";
import type { MailAccount, MailMatchStatus, MailMessageListItem, MailSyncResult } from "@/lib/api/types";

const MESSAGES_PAGE_SIZE = 50;

// "Unbekannt" (UNMATCHED - Newsletter/Werbung o.ae.) ist per Default
// ausgeblendet, damit die Liste nicht mit irrelevanten Mails vollläuft
// (Nutzer-Vorgabe) - ueber den Filter weiterhin einsehbar. undefined = kein
// match_status-Parameter = Backend liefert alle Status.
const FILTER_OPTIONS: { value: string; label: string; statuses?: MailMatchStatus[] }[] = [
  { value: "not_unmatched", label: "Alle außer Unbekannt", statuses: ["matched", "pending_review"] },
  { value: "all", label: "Alle" },
  { value: "matched", label: "Nur Zugeordnet", statuses: ["matched"] },
  { value: "pending_review", label: "Nur Zur Prüfung", statuses: ["pending_review"] },
  { value: "unmatched", label: "Nur Unbekannt", statuses: ["unmatched"] },
];

const STATUS_LABEL: Record<MailMatchStatus, string> = {
  matched: "Zugeordnet",
  pending_review: "Zur Prüfung",
  unmatched: "Unbekannt",
};

const STATUS_TONE: Record<MailMatchStatus, "green" | "amber" | "gray"> = {
  matched: "green",
  pending_review: "amber",
  unmatched: "gray",
};

function formatMessageDate(value: string): string {
  return new Date(value).toLocaleString("de-DE", { dateStyle: "short", timeStyle: "short" });
}

/** Ziel-Link fuer eine zugeordnete Mail - Kontaktpersonen haben keine eigene
 * Detailseite, deshalb geht der Link dort zur Kanzlei (siehe
 * MailMessageListItem-Docstring im Backend). */
function messageLink(message: MailMessageListItem): { href: string; label: string } | null {
  if (message.matched_candidate_id) {
    return { href: `/kandidaten/${message.matched_candidate_id}`, label: message.matched_candidate_name ?? "Kandidat:in" };
  }
  if (message.matched_contact_person_id && message.matched_contact_person_client_company_id) {
    return {
      href: `/kanzleien/${message.matched_contact_person_client_company_id}`,
      label: message.matched_contact_person_name ?? "Kontaktperson",
    };
  }
  if (message.matched_client_company_id) {
    return { href: `/kanzleien/${message.matched_client_company_id}`, label: message.matched_client_company_name ?? "Kanzlei" };
  }
  return null;
}

/** Aufklappbare Liste der ueber ein Konto eingelesenen Mails - eigener
 * State/Fetch pro Konto (nicht ueber useSWR, da paginiert per "mehr laden"
 * statt einmalig geladen), damit mehrere Konten unabhaengig aufklappbar
 * sind. */
function MessageList({ accountId }: { accountId: string }) {
  const [open, setOpen] = useState(false);
  const [filter, setFilter] = useState(FILTER_OPTIONS[0].value);
  const [messages, setMessages] = useState<MailMessageListItem[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [hasMore, setHasMore] = useState(true);

  // filterValue explizit statt aus dem filter-State gelesen: bei einem
  // Filterwechsel wuerde ein setState + direkt anschliessender Aufruf sonst
  // noch den ALTEN State-Wert sehen (React committet setState asynchron).
  async function load(filterValue: string, offsetOverride: number) {
    setLoading(true);
    setError(null);
    try {
      const statuses = FILTER_OPTIONS.find((option) => option.value === filterValue)?.statuses;
      const { data: page } = await getMailMessages(accountId, {
        matchStatus: statuses,
        offset: offsetOverride,
        limit: MESSAGES_PAGE_SIZE,
      });
      setMessages((current) => (offsetOverride === 0 ? page : [...current, ...page]));
      setHasMore(page.length === MESSAGES_PAGE_SIZE);
    } catch (exception) {
      setError(exception instanceof Error ? exception.message : "Mails konnten nicht geladen werden.");
    } finally {
      setLoading(false);
    }
  }

  function toggleOpen() {
    const next = !open;
    setOpen(next);
    if (next && messages.length === 0 && !loading) void load(filter, 0);
  }

  function changeFilter(value: string) {
    setFilter(value);
    setMessages([]);
    setHasMore(true);
    void load(value, 0);
  }

  return (
    <div className="mt-3 border-t border-white/5 pt-3">
      <button
        type="button"
        onClick={toggleOpen}
        className="flex items-center gap-1.5 text-xs font-medium text-[#94A3B8] hover:text-white"
      >
        {open ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
        Eingelesene Mails
      </button>

      {open && (
        <div className="mt-3 space-y-2">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <select
              value={filter}
              onChange={(e) => changeFilter(e.target.value)}
              className="h-8 rounded-md border border-white/10 bg-[#0D1B2E] px-2 text-[11px] text-[#D8DADF] outline-none focus:border-[#1F5FA8]"
            >
              {FILTER_OPTIONS.map((option) => (
                <option key={option.value} value={option.value}>
                  {option.label}
                </option>
              ))}
            </select>
          </div>

          <ErrorBanner message={error} />

          {loading && messages.length === 0 && (
            <div className="space-y-1.5">
              {Array.from({ length: 3 }).map((_, index) => (
                <div key={index} className="h-10 animate-pulse rounded-md bg-[#0D1B2E]" />
              ))}
            </div>
          )}

          {!loading && messages.length === 0 && !error && (
            <p className="py-4 text-center text-xs text-[#747C89]">Keine Mails für diesen Filter.</p>
          )}

          <div className="divide-y divide-white/5 overflow-hidden rounded-md border border-white/5">
            {messages.map((message) => {
              const link = messageLink(message);
              return (
                <div
                  key={message.id}
                  className="flex flex-wrap items-center gap-2 bg-[#071426]/60 px-3 py-2 text-xs"
                >
                  <span className="shrink-0 text-[#747C89]">{formatMessageDate(message.received_at)}</span>
                  {message.is_linkedin && <Linkedin size={12} className="shrink-0 text-[#69A7EA]" />}
                  <span className="min-w-0 flex-1 truncate text-[#D8DADF]">
                    <span className="font-medium">{message.from_name ?? message.from_address ?? "Unbekannt"}</span>
                    {message.subject && <span className="text-[#747C89]"> — {message.subject}</span>}
                  </span>
                  <Badge tone={STATUS_TONE[message.match_status]}>{STATUS_LABEL[message.match_status]}</Badge>
                  {link ? (
                    <Link href={link.href} className="shrink-0 text-[#69A7EA] hover:underline">
                      {link.label} →
                    </Link>
                  ) : message.match_status === "pending_review" ? (
                    // Kernfall: LinkedIn-Antwort ohne Namenstreffer - kein
                    // Link, aber der Name aus der Mail bleibt sichtbar,
                    // damit klar ist, wer manuelles Eingreifen braucht.
                    <span className="shrink-0 text-[#F0B429]">
                      {message.from_name ?? "Name unbekannt"} – kein Treffer
                    </span>
                  ) : null}
                </div>
              );
            })}
          </div>

          {hasMore && messages.length > 0 && (
            <Button
              size="sm"
              variant="outline"
              onClick={() => void load(filter, messages.length)}
              disabled={loading}
            >
              {loading ? "Lädt…" : "Mehr laden"}
            </Button>
          )}
        </div>
      )}
    </div>
  );
}

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

/** Rate-Limiting fuer den SMTP-Versand (Backend services/mail_send.py) -
 * Pause zwischen Sends + Tageslimit sind je Postfach konfigurierbar statt
 * hart verdrahtet (Nutzer-Vorgabe "Schnelle Submission", Schritt 1). Eigene
 * lokale Draft-Werte statt direkt `account.*` zu binden, damit Tippen keinen
 * PATCH pro Tastendruck ausloest - erst "Speichern" persistiert. */
function ThrottleSettingsEditor({
  account,
  busy,
  onSave,
}: {
  account: MailAccount;
  busy: boolean;
  onSave: (values: { send_throttle_seconds: number; daily_send_limit: number }) => void;
}) {
  const [throttleSeconds, setThrottleSeconds] = useState(String(account.send_throttle_seconds));
  const [dailyLimit, setDailyLimit] = useState(String(account.daily_send_limit));

  const dirty =
    Number(throttleSeconds) !== account.send_throttle_seconds ||
    Number(dailyLimit) !== account.daily_send_limit;

  return (
    <div className="mt-2 flex flex-wrap items-center gap-2 text-xs text-[#94A3B8]">
      <span>Versand-Pause</span>
      <input
        type="number"
        min={0}
        max={3600}
        value={throttleSeconds}
        onChange={(e) => setThrottleSeconds(e.target.value)}
        className="h-7 w-16 rounded border border-white/10 bg-[#0D1B2E] px-1.5 text-center text-[#F8FAFC] outline-none focus:border-[#1F5FA8]"
      />
      <span>s · Tageslimit</span>
      <input
        type="number"
        min={1}
        max={10000}
        value={dailyLimit}
        onChange={(e) => setDailyLimit(e.target.value)}
        className="h-7 w-20 rounded border border-white/10 bg-[#0D1B2E] px-1.5 text-center text-[#F8FAFC] outline-none focus:border-[#1F5FA8]"
      />
      <span>Mails/Tag</span>
      {dirty && (
        <Button
          size="sm"
          variant="outline"
          disabled={busy}
          onClick={() =>
            onSave({
              send_throttle_seconds: Number(throttleSeconds),
              daily_send_limit: Number(dailyLimit),
            })
          }
        >
          Speichern
        </Button>
      )}
    </div>
  );
}

export default function PostfaecherPage() {
  const { data: meData, isLoading: meLoading } = useCurrentUser();
  const isAdmin = meData?.data.is_admin ?? false;
  const { data, isLoading, error, mutate: retry } = useMailAccountsCache(isAdmin);
  const accounts = data?.data ?? [];

  // Rueckkehr aus dem "Mit Microsoft anmelden"-Flow (siehe api/v1/
  // mail_accounts.py::mail_oauth_callback) - der Callback redirected mit
  // ?ms_connected=<adresse> bzw. ?ms_error=<meldung> hierher zurueck.
  const router = useRouter();
  const searchParams = useSearchParams();
  const [msConnectedNotice, setMsConnectedNotice] = useState<string | null>(null);
  const [msErrorNotice, setMsErrorNotice] = useState<string | null>(null);
  useEffect(() => {
    const connected = searchParams.get("ms_connected");
    const oauthErrorParam = searchParams.get("ms_error");
    if (connected) {
      setMsConnectedNotice(connected);
      void invalidateMailAccountsCache();
      router.replace("/einstellungen/postfaecher");
    } else if (oauthErrorParam) {
      setMsErrorNotice(oauthErrorParam);
      router.replace("/einstellungen/postfaecher");
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

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

  const [oauthError, setOauthError] = useState<string | null>(null);
  const [oauthBusy, setOauthBusy] = useState(false);

  async function handleConnectMicrosoft() {
    setOauthBusy(true);
    setOauthError(null);
    try {
      const result = await startMicrosoftOAuth();
      if (!result.data.authorization_url) {
        throw new Error("Keine Autorisierungs-URL erhalten.");
      }
      // Voller Seitenwechsel (kein SPA-Routing) - der Browser muss die
      // Backend-Domain zum Microsoft-Login verlassen (Auftrag "M365-
      // Postfach-Integration").
      window.location.href = result.data.authorization_url;
    } catch (exception) {
      setOauthError(
        exception instanceof Error ? exception.message : "Verbindung zu Microsoft fehlgeschlagen.",
      );
      setOauthBusy(false);
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
              <div className="flex flex-wrap gap-2">
                <Button size="sm" variant="outline" disabled={oauthBusy} onClick={() => void handleConnectMicrosoft()}>
                  <Mail size={14} />
                  {oauthBusy ? "Öffne Microsoft…" : "Mit Microsoft anmelden"}
                </Button>
                <Button size="sm" variant="outline" onClick={() => setShowForm((open) => !open)}>
                  <Plus size={14} />
                  {showForm ? "Abbrechen" : "IMAP/SMTP-Postfach verbinden"}
                </Button>
              </div>
            </div>
          </CardHeader>

          <CardContent className="space-y-4">
            {msConnectedNotice && (
              <div className="rounded-lg border border-[#4f8a68]/35 bg-[#244d38]/45 p-3 text-xs text-[#a9d6b8]">
                Postfach {msConnectedNotice} erfolgreich über Microsoft verbunden.
              </div>
            )}
            <ErrorBanner message={msErrorNotice} />
            <ErrorBanner message={oauthError} />
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
                        {account.provider === "microsoft_graph" && (
                          <span className="rounded bg-[#1F5FA8]/25 px-2 py-0.5 text-[10px] text-[#69A7EA]">
                            Microsoft 365
                          </span>
                        )}
                        {account.oauth_status === "needs_reconnect" && (
                          <span className="flex items-center gap-1 rounded bg-[#3A2416] px-2 py-0.5 text-[10px] text-[#F0B429]">
                            <Unplug size={10} />Verbindung abgelaufen
                          </span>
                        )}
                      </p>
                      <p className="mt-1 text-xs text-[#747C89]">
                        {account.provider === "microsoft_graph"
                          ? "Microsoft Graph (OAuth)"
                          : `IMAP ${account.imap_host}:${account.imap_port} · SMTP ${account.smtp_host}:${account.smtp_port}`}
                        {" · zuletzt abgerufen: "}
                        {formatDateTime(account.last_synced_at)}
                      </p>
                      <ThrottleSettingsEditor
                        account={account}
                        busy={busy}
                        onSave={(values) => void patchAccount(account, values)}
                      />
                    </div>

                    <div className="flex flex-wrap gap-2">
                      {account.oauth_status === "needs_reconnect" ? (
                        <Button
                          size="sm"
                          disabled={oauthBusy}
                          onClick={() => void handleConnectMicrosoft()}
                        >
                          <Unplug size={13} />
                          {oauthBusy ? "Öffne Microsoft…" : "Postfach neu verbinden"}
                        </Button>
                      ) : (
                        <Button
                          size="sm"
                          variant="outline"
                          onClick={() => void handleSync(account)}
                          disabled={busy}
                        >
                          <RefreshCw size={13} />
                          {busy ? "Läuft…" : "Jetzt abrufen"}
                        </Button>
                      )}
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
                      {result.auto_created_candidates > 0 &&
                        ` · ${result.auto_created_candidates} Kandidat(en) automatisch angelegt`}
                    </p>
                  )}

                  <MessageList accountId={account.id} />
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
