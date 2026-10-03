"use client";

import { useCallback, useEffect, useState } from "react";
import { ShieldOff } from "lucide-react";
import { PageHeader } from "@/components/crm/page-header";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { useCurrentUser } from "@/lib/api/hooks";
import {
  createWebhook,
  deleteWebhook,
  getWebhookDeliveries,
  getWebhooks,
  retryWebhookDelivery,
  rotateWebhookSecret,
  sendWebhookTest,
  updateWebhook,
} from "@/lib/api/queries";
import type { WebhookDelivery, WebhookEndpoint } from "@/lib/api/types";

const STATUS_LABELS: Record<WebhookDelivery["status"], string> = {
  pending: "wartet",
  retrying: "wird wiederholt",
  delivered: "zugestellt",
  dead: "aufgegeben",
};

export default function WebhooksPage() {
  const { data: meData, isLoading: meLoading } = useCurrentUser();
  const isAdmin = meData?.data.is_admin ?? false;
  const [hooks, setHooks] = useState<WebhookEndpoint[]>([]);
  const [name, setName] = useState("");
  const [url, setUrl] = useState("");
  const [events, setEvents] = useState("*");
  const [message, setMessage] = useState<string | null>(null);
  const [secret, setSecret] = useState<{ name: string; value: string } | null>(null);
  const [openId, setOpenId] = useState<string | null>(null);
  const [deliveries, setDeliveries] = useState<WebhookDelivery[]>([]);

  const load = useCallback(async () => {
    const result = await getWebhooks();
    setHooks(result.data);
  }, []);

  useEffect(() => {
    if (!isAdmin) return;
    void load();
  }, [isAdmin, load]);

  async function run(action: () => Promise<void>) {
    setMessage(null);
    try {
      await action();
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Aktion fehlgeschlagen.");
    }
  }

  async function showDeliveries(id: string) {
    setOpenId(id);
    const result = await getWebhookDeliveries(id);
    setDeliveries(result.data);
  }

  if (meLoading) {
    return <div className="h-16 animate-pulse rounded-lg bg-[#0D1B2E]" />;
  }

  if (!isAdmin) {
    return (
      <>
        <PageHeader eyebrow="Einstellungen" title="Webhooks" />
        <Card>
          <CardContent className="flex items-center gap-3 text-sm text-[#94A3B8]">
            <ShieldOff size={18} /> Nur für Admins zugänglich.
          </CardContent>
        </Card>
      </>
    );
  }

  return (
    <>
      <PageHeader eyebrow="Einstellungen" title="Webhooks" />
      <p className="mb-5 max-w-3xl text-sm text-[#94A3B8]">
        Meldet Ereignisse (z. B. <code>candidate_submission.status_changed</code>) signiert an eine https-Adresse. Die
        Nachricht enthält nur Ereignisart und IDs, keine Personendaten – Details holt der Empfänger per API-Key. Muster:
        <code> *</code> für alles oder <code>candidate.*</code> für eine Gruppe. Adressen im internen Netz sind nicht
        erlaubt.
      </p>

      {secret && (
        <Card className="mb-4">
          <CardContent className="text-sm">
            <p className="font-medium">Geheimnis für „{secret.name}“ – wird nur jetzt angezeigt:</p>
            <p className="mt-1 break-all font-mono text-[#F8FAFC]">{secret.value}</p>
            <Button size="sm" variant="outline" className="mt-2" onClick={() => setSecret(null)}>
              Gespeichert, ausblenden
            </Button>
          </CardContent>
        </Card>
      )}
      {message && <p className="mb-3 text-sm text-red-300">{message}</p>}

      <Card className="mb-5">
        <CardContent className="grid gap-3 md:grid-cols-4">
          <Input placeholder="Name" value={name} onChange={(event) => setName(event.target.value)} />
          <Input placeholder="https://…" value={url} onChange={(event) => setUrl(event.target.value)} />
          <Input
            placeholder="Ereignisse, kommagetrennt"
            value={events}
            onChange={(event) => setEvents(event.target.value)}
          />
          <Button
            disabled={!name.trim() || !url.trim()}
            onClick={() =>
              void run(async () => {
                const created = await createWebhook({
                  name,
                  url,
                  event_types: events.split(",").map((item) => item.trim()).filter(Boolean),
                });
                setSecret({ name: created.name, value: created.secret });
                setName("");
                setUrl("");
                await load();
              })
            }
          >
            Webhook anlegen
          </Button>
        </CardContent>
      </Card>

      <div className="space-y-3">
        {hooks.length === 0 && <p className="text-sm text-[#94A3B8]">Noch keine Webhooks angelegt.</p>}
        {hooks.map((hook) => (
          <Card key={hook.id}>
            <CardContent className="space-y-3">
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div className="min-w-0">
                  <p className="font-medium">
                    {hook.name}
                    {!hook.is_active && <span className="ml-2 text-xs text-[#94A3B8]">(deaktiviert)</span>}
                  </p>
                  <p className="break-all text-xs text-[#94A3B8]">{hook.url}</p>
                  <p className="text-xs text-[#94A3B8]">Ereignisse: {hook.event_types.join(", ")}</p>
                </div>
                <div className="flex flex-wrap gap-2">
                  <Button size="sm" variant="outline" onClick={() => void run(async () => { await sendWebhookTest(hook.id); await showDeliveries(hook.id); })}>
                    Test senden
                  </Button>
                  <Button size="sm" variant="outline" onClick={() => void showDeliveries(hook.id)}>
                    Zustellungen
                  </Button>
                  <Button
                    size="sm"
                    variant="outline"
                    onClick={() =>
                      void run(async () => {
                        const updated = await updateWebhook(hook.id, { is_active: !hook.is_active });
                        setHooks((list) => list.map((item) => (item.id === updated.id ? updated : item)));
                      })
                    }
                  >
                    {hook.is_active ? "Deaktivieren" : "Aktivieren"}
                  </Button>
                  <Button
                    size="sm"
                    variant="outline"
                    onClick={() =>
                      void run(async () => {
                        const rotated = await rotateWebhookSecret(hook.id);
                        setSecret({ name: rotated.name, value: rotated.secret });
                      })
                    }
                  >
                    Neues Geheimnis
                  </Button>
                  <Button
                    size="sm"
                    variant="outline"
                    onClick={() =>
                      void run(async () => {
                        if (!window.confirm(`Webhook „${hook.name}“ löschen?`)) return;
                        await deleteWebhook(hook.id);
                        await load();
                      })
                    }
                  >
                    Löschen
                  </Button>
                </div>
              </div>
              {openId === hook.id && (
                <div className="space-y-1 border-t border-white/10 pt-3 text-xs">
                  {deliveries.length === 0 && <p className="text-[#94A3B8]">Noch keine Zustellungen.</p>}
                  {deliveries.map((delivery) => (
                    <div key={delivery.id} className="flex flex-wrap items-center justify-between gap-2">
                      <span>
                        {new Date(delivery.created_at).toLocaleString("de-DE")} · {delivery.event_type} ·{" "}
                        {STATUS_LABELS[delivery.status]} · Versuch {delivery.attempts}
                        {delivery.response_status ? ` · HTTP ${delivery.response_status}` : ""}
                        {delivery.last_error && <span className="text-red-300"> · {delivery.last_error}</span>}
                      </span>
                      {delivery.status === "dead" && (
                        <Button
                          size="sm"
                          variant="outline"
                          onClick={() =>
                            void run(async () => {
                              await retryWebhookDelivery(delivery.id);
                              await showDeliveries(hook.id);
                            })
                          }
                        >
                          Neu senden
                        </Button>
                      )}
                    </div>
                  ))}
                </div>
              )}
            </CardContent>
          </Card>
        ))}
      </div>
    </>
  );
}
