"use client";

import { useEffect, useState } from "react";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { PageHeader } from "@/components/crm/page-header";
import { decideClaudeConsent, getClaudeConsentInfo } from "@/lib/api/queries";
import type { ClaudeConsentInfo } from "@/lib/api/types";

/** Zustimmung zur Verbindung von Claude mit Hermes. Die Anfrage-ID kommt aus
 * /api/v1/oauth/authorize; ohne Hermes-Login führt die Middleware zuerst zur Anmeldung
 * und danach hierher zurück. */
export default function ClaudeZustimmungPage() {
  const [requestId, setRequestId] = useState<string | null>(null);
  const [info, setInfo] = useState<ClaudeConsentInfo | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    const id = new URLSearchParams(window.location.search).get("request");
    setRequestId(id);
    if (!id) {
      setError("Die Anfrage fehlt. Bitte die Verbindung in Claude erneut starten.");
      return;
    }
    getClaudeConsentInfo(id)
      .then((result) => setInfo(result.data))
      .catch((exception) =>
        setError(exception instanceof Error ? exception.message : "Die Anfrage ist abgelaufen."),
      );
  }, []);

  async function decide(approve: boolean) {
    if (!requestId) return;
    setBusy(true);
    setError(null);
    try {
      const result = await decideClaudeConsent(requestId, approve);
      window.location.href = result.redirect_url;
    } catch (exception) {
      setError(exception instanceof Error ? exception.message : "Aktion fehlgeschlagen.");
      setBusy(false);
    }
  }

  return (
    <>
      <PageHeader eyebrow="Hermes" title="Claude verbinden" />
      <Card className="max-w-2xl">
        <CardContent className="space-y-4">
          {info ? (
            <>
              <p className="text-sm text-brand-text">
                <strong>{info.client_name}</strong>{" "}
                <span className="text-xs text-brand-warning">(Name vom Client gemeldet, ungeprüft)</span> möchte sich mit
                deinem Hermes-Konto verbinden (<span className="text-brand-muted">{info.user_email}</span>).
              </p>
              <ul className="list-disc space-y-1 pl-5 text-sm text-brand-soft">
                <li>Claude sieht nur, was du in Hermes sehen darfst – ohne Kontaktdaten und Gehälter.</li>
                <li>Claude kann Notizen, Aufgaben und Mail-Entwürfe nur <strong>vorschlagen</strong>. Angelegt wird
                  erst, wenn du unter „Claude-Vorschläge“ freigibst; Mails sendest du immer selbst.</li>
                <li>Jeder Aufruf steht im Audit-Log. Du kannst die Verbindung jederzeit unter Einstellungen trennen.</li>
              </ul>
              <p className="text-xs text-brand-muted">
                Rückkehr zu: {info.redirect_host}. Nur bestätigen, wenn du die Verbindung gerade selbst in Claude
                gestartet hast.
              </p>
              <div className="flex gap-2">
                <Button disabled={busy} onClick={() => void decide(true)}>
                  Verbinden
                </Button>
                <Button variant="outline" disabled={busy} onClick={() => void decide(false)}>
                  Abbrechen
                </Button>
              </div>
            </>
          ) : (
            !error && <p className="text-sm text-brand-muted">Anfrage wird geladen…</p>
          )}
          {error && <p className="text-sm text-red-300">{error}</p>}
        </CardContent>
      </Card>
    </>
  );
}
