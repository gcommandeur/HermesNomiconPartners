"use client";

import { useCallback, useEffect, useState } from "react";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { useAiProposalSummary } from "@/lib/api/hooks";
import { getClaudeConnections, revokeClaudeConnection } from "@/lib/api/queries";
import type { ClaudeConnection } from "@/lib/api/types";

/** Einstellungen → „Claude-Verbindung“: wo Claude mit diesem Hermes-Konto verbunden ist.
 * Verbunden wird in Claude (Team-Konto: Connector mit der Hermes-MCP-Adresse), die
 * Zustimmung gibst du hier in Hermes. Nur sichtbar, wenn die Schnittstelle eingeschaltet ist. */
export function ClaudeConnectionCard() {
  const ai = useAiProposalSummary();
  const [items, setItems] = useState<ClaudeConnection[]>([]);
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    const result = await getClaudeConnections();
    setItems(result.data);
  }, []);

  useEffect(() => {
    if (ai.enabled) void load();
  }, [ai.enabled, load]);

  if (!ai.enabled) return null;

  return (
    <Card className="mb-5">
      <CardContent className="space-y-3">
        <div>
          <p className="font-semibold">Claude-Verbindung</p>
          <p className="mt-1 max-w-2xl text-xs text-brand-muted">
            Claude kann mit deinem Konto lesen und Vorschläge machen (Notizen, Aufgaben, Mail-Entwürfe) –
            angelegt oder gesendet wird nichts ohne deine Freigabe. Verbinden: in Claude den Hermes-Connector
            hinzufügen und hier zustimmen.
          </p>
        </div>
        {items.length === 0 && <p className="text-xs text-brand-muted">Aktuell ist keine Claude-Verbindung aktiv.</p>}
        {items.map((item) => (
          <div key={item.id} className="flex flex-wrap items-center justify-between gap-2 rounded-lg border border-white/10 p-3">
            <div>
              <p className="text-sm font-medium">{item.client_name}</p>
              <p className="text-xs text-brand-muted">
                verbunden {new Date(item.created_at).toLocaleDateString("de-DE")}
                {item.last_used_at && ` · zuletzt genutzt ${new Date(item.last_used_at).toLocaleString("de-DE")}`}
              </p>
            </div>
            <Button
              size="sm"
              variant="outline"
              disabled={busy}
              onClick={async () => {
                setBusy(true);
                try {
                  await revokeClaudeConnection(item.id);
                  await load();
                } finally {
                  setBusy(false);
                }
              }}
            >
              Trennen
            </Button>
          </div>
        ))}
      </CardContent>
    </Card>
  );
}
