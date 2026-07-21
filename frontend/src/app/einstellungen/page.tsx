"use client";

import { useState } from "react";
import Link from "next/link";
import { mutate } from "swr";
import { Check, Copy, RefreshCw, Users } from "lucide-react";
import { PageHeader } from "@/components/crm/page-header";
import { ErrorState } from "@/components/crm/error-state";
import { ErrorBanner } from "@/components/crm/error-banner";
import { Card, CardContent, CardHeader } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { apiBaseUrl, apiPost } from "@/lib/api/client";
import { useCurrentUser } from "@/lib/api/hooks";

export default function EinstellungenPage() {
  const { data, isLoading, error, mutate: retry } = useCurrentUser();
  const user = data?.data;
  const [copied, setCopied] = useState(false);
  const [rotating, setRotating] = useState(false);
  const [rotateError, setRotateError] = useState<string | null>(null);

  const feedUrl =
    user?.calendar_feed_token && apiBaseUrl
      ? `${apiBaseUrl}/calendar/feed/${user.calendar_feed_token}.ics`
      : null;

  async function handleCopy() {
    if (!feedUrl) return;
    await navigator.clipboard.writeText(feedUrl);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  }

  async function handleRotate() {
    if (!user) return;
    setRotating(true);
    setRotateError(null);
    try {
      await apiPost(`/users/${user.id}/rotate-calendar-feed-token`, {});
      await Promise.all([retry(), mutate("/auth/me")]);
    } catch (exception) {
      setRotateError(
        exception instanceof Error ? exception.message : "Feed-Token konnte nicht erneuert werden.",
      );
    } finally {
      setRotating(false);
    }
  }

  if (error) {
    return <ErrorState onRetry={() => void retry()} />;
  }

  if (isLoading || !user) {
    return (
      <div className="space-y-2">
        {Array.from({ length: 4 }).map((_, index) => (
          <div key={index} className="h-16 animate-pulse rounded-lg bg-[#0D1B2E]" />
        ))}
      </div>
    );
  }

  return (
    <>
      <PageHeader eyebrow="Hermes" title="Einstellungen" />

      <div className="space-y-5">
        <Card>
          <CardHeader>
            <div>
              <h2 className="font-semibold">Kalender mit Outlook synchronisieren</h2>
              <p className="mt-1 text-xs text-[#94A3B8]">
                Persönlicher, schreibgeschützter Kalender-Feed - zeigt nur deine eigenen Termine
                aus Hermes CRM (Interviews, Quali Calls, sonstige Termine).
              </p>
            </div>
          </CardHeader>
          <CardContent className="space-y-4">
            <div>
              <label className="mb-1 block text-xs text-[#94A3B8]">Deine persönliche Feed-URL</label>
              <div className="flex gap-2">
                <input
                  readOnly
                  value={feedUrl ?? ""}
                  onFocus={(e) => e.target.select()}
                  className="h-10 w-full flex-1 rounded-md border border-white/10 bg-[#0D1B2E] px-3 text-xs text-[#F8FAFC] outline-none focus:border-[#1F5FA8]"
                />
                <Button variant="outline" onClick={handleCopy} disabled={!feedUrl}>
                  {copied ? <Check size={14} /> : <Copy size={14} />}
                  {copied ? "Kopiert" : "Kopieren"}
                </Button>
              </div>
              <p className="mt-2 text-[11px] text-[#747C89]">
                Diese URL ist geheim (wie ein Passwort) - nicht weitergeben. Falls sie versehentlich
                geteilt wurde, hier neu generieren:
              </p>
              <Button size="sm" variant="outline" className="mt-2" onClick={handleRotate} disabled={rotating}>
                <RefreshCw size={13} />{rotating ? "Wird erneuert…" : "Feed-URL neu generieren"}
              </Button>
              <ErrorBanner message={rotateError} className="mt-2" />
            </div>

            <div className="rounded-lg border border-white/10 bg-[#071426] p-4">
              <p className="mb-2 text-xs font-semibold text-[#D8DADF]">So abonnierst du diesen Kalender</p>
              <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
                <div>
                  <p className="mb-1 text-[11px] font-semibold uppercase tracking-wider text-[#69A7EA]">
                    Outlook (Desktop)
                  </p>
                  <ol className="list-decimal space-y-1 pl-4 text-xs text-[#CBD5E1]">
                    <li>Kalender öffnen → &quot;Kalender hinzufügen&quot; → &quot;Aus dem Internet abonnieren&quot;</li>
                    <li>Die obige Feed-URL einfügen und bestätigen</li>
                    <li>Termine erscheinen automatisch (inkl. Erinnerung)</li>
                  </ol>
                </div>
                <div>
                  <p className="mb-1 text-[11px] font-semibold uppercase tracking-wider text-[#69A7EA]">
                    Outlook im Web
                  </p>
                  <ol className="list-decimal space-y-1 pl-4 text-xs text-[#CBD5E1]">
                    <li>Kalender öffnen → &quot;Kalender hinzufügen&quot; → &quot;Aus dem Web&quot;</li>
                    <li>Die obige Feed-URL einfügen, Namen vergeben und &quot;Importieren&quot; wählen</li>
                  </ol>
                </div>
              </div>
            </div>
          </CardContent>
        </Card>

        {user.is_admin && (
          <Card>
            <CardHeader>
              <div>
                <h2 className="flex items-center gap-2 font-semibold"><Users size={16} />Administration</h2>
                <p className="mt-1 text-xs text-[#94A3B8]">Nutzer verwalten (Admin-Recht, Aktivierung).</p>
              </div>
            </CardHeader>
            <CardContent className="flex flex-wrap gap-2">
              <Link href="/einstellungen/nutzer">
                <Button size="sm" variant="outline">Nutzerverwaltung öffnen</Button>
              </Link>
              <Link href="/einstellungen/audit-log">
                <Button size="sm" variant="outline">Audit-Log öffnen</Button>
              </Link>
            </CardContent>
          </Card>
        )}
      </div>
    </>
  );
}
