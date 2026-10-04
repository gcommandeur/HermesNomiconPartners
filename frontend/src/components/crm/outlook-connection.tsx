"use client";

import { useEffect, useState } from "react";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { disconnectOutlook, getOutlookStatus } from "@/lib/api/queries";
import type { OutlookStatus } from "@/lib/api/types";

const DEMO_MODE = process.env.NEXT_PUBLIC_CC_CRM_DEMO_MODE === "true";
const CONNECT_URL = "/api/v1/auth/microsoft/login";

function useOutlookStatus() {
  const [status, setStatus] = useState<OutlookStatus | null>(null);
  useEffect(() => {
    if (DEMO_MODE) return;
    let cancelled = false;
    getOutlookStatus().then((result) => {
      if (!cancelled) setStatus(result.data);
    });
    return () => {
      cancelled = true;
    };
  }, []);
  return { status, setStatus };
}

/** Schmaler Hinweis oben im Inhalt, solange Outlook nicht (mehr) verbunden ist.
 * Verbunden wird mit „Mit Microsoft anmelden“ – ein Klick, danach laufen Mail-Versand,
 * Kalender und Teams-Einladungen über das eigene Konto. Pro Sitzung ausblendbar. */
export function OutlookBanner() {
  const { status } = useOutlookStatus();
  const [hidden, setHidden] = useState(false);
  useEffect(() => {
    try {
      setHidden(window.sessionStorage.getItem("outlook-banner-hidden") === "1");
    } catch {
      // Storage nicht verfügbar – Banner einfach anzeigen.
    }
  }, []);
  if (!status || status.state === "connected" || hidden) return null;
  return (
    <div className="mb-5 flex flex-wrap items-center justify-between gap-3 rounded-lg border border-brand-accent/40 bg-brand-surface px-4 py-3 text-sm">
      <span className="text-brand-soft">
        {status.state === "needs_reconnect"
          ? "Deine Outlook-Verbindung ist abgelaufen. Bitte neu anmelden, damit Mails, Termine und Teams-Einladungen weiter funktionieren."
          : "Outlook ist nicht verbunden. Einmal mit Microsoft anmelden – dann gehen Mails aus deinem Postfach raus und Termine landen mit Teams-Link im Kalender."}
      </span>
      <span className="flex gap-2">
        <a href={CONNECT_URL}>
          <Button size="sm">Mit Microsoft verbinden</Button>
        </a>
        <Button
          size="sm"
          variant="outline"
          onClick={() => {
            setHidden(true);
            try {
              window.sessionStorage.setItem("outlook-banner-hidden", "1");
            } catch {
              // egal
            }
          }}
        >
          Später
        </Button>
      </span>
    </div>
  );
}

/** Karte in den Einstellungen: Status der eigenen Verbindung, neu verbinden oder trennen. */
export function OutlookConnectionCard() {
  const { status, setStatus } = useOutlookStatus();
  const [busy, setBusy] = useState(false);
  if (DEMO_MODE || !status) return null;
  const connected = status.state === "connected";
  return (
    <Card className="mb-5">
      <CardContent className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <p className="font-semibold">Outlook &amp; Teams</p>
          <p className="mt-1 text-xs text-brand-muted">
            {connected
              ? `Verbunden als ${status.address}. Mails, Kalender und Teams-Einladungen laufen über dein Konto.`
              : status.state === "needs_reconnect"
                ? "Die Verbindung ist abgelaufen – bitte neu verbinden."
                : "Nicht verbunden."}
          </p>
        </div>
        <div className="flex gap-2">
          <a href={CONNECT_URL}>
            <Button size="sm" variant="outline">{connected ? "Neu verbinden" : "Mit Microsoft verbinden"}</Button>
          </a>
          {status.state !== "not_connected" && (
            <Button
              size="sm"
              variant="outline"
              disabled={busy}
              onClick={async () => {
                setBusy(true);
                try {
                  await disconnectOutlook();
                  setStatus({ state: "not_connected", address: null });
                } finally {
                  setBusy(false);
                }
              }}
            >
              Trennen
            </Button>
          )}
        </div>
      </CardContent>
    </Card>
  );
}
