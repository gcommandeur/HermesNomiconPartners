"use client";

// NOMICON: Block "Verfügbarkeit" am Kandidaten - offen für Direct / Überlassung (bearbeitbar) und
// Zeitlinie aller Prozesse und Einsätze, soweit für den Nutzer sichtbar.
import { useState } from "react";
import { Card, CardContent } from "@/components/ui/card";
import { ErrorBanner } from "@/components/crm/error-banner";
import { EngagementBadge, itemDetail } from "@/components/crm/engagement-badge";
import { OPENNESS_LABELS, updateEngagementPrefs, type Openness } from "@/lib/api/engagement";
import { refreshEngagement, useEngagement } from "@/lib/api/engagement-hooks";

const selectClass =
  "h-9 rounded-md border border-white/15 bg-brand-surface px-2 text-sm text-brand-platinum focus:outline-none focus:ring-2 focus:ring-brand-accent/30 disabled:opacity-50";
const OPTIONS: Openness[] = ["unknown", "yes", "no"];

export function EngagementPanel({ candidateId }: { candidateId: string }) {
  const { data, error, mutate } = useEngagement(candidateId);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const summary = data?.data;

  async function change(body: { open_for_direct?: Openness; open_for_staffing?: Openness }) {
    setBusy(true);
    setMessage(null);
    try {
      await updateEngagementPrefs(candidateId, body);
      await Promise.all([mutate(), refreshEngagement(candidateId)]);
    } catch (exception) {
      setMessage(exception instanceof Error ? exception.message : "Speichern fehlgeschlagen.");
    } finally {
      setBusy(false);
    }
  }

  if (error) return <ErrorBanner message="Der Austausch-Status konnte nicht geladen werden." className="mb-6" />;
  if (!summary) return <div className="mb-6 h-24 animate-pulse rounded-lg bg-brand-surface" />;

  return (
    <Card className="mb-6">
      <CardContent>
        <div className="flex flex-wrap items-center justify-between gap-3">
          <h2 className="font-semibold">Verfügbarkeit &amp; Austausch</h2>
          <EngagementBadge summary={summary} />
        </div>
        <div className="mt-4 grid grid-cols-1 gap-4 sm:grid-cols-2">
          <label className="text-xs text-brand-muted">
            Offen für Direct (Vermittlung)
            <select className={`${selectClass} mt-1 block w-full`} value={summary.open_for_direct} disabled={busy} onChange={(event) => void change({ open_for_direct: event.target.value as Openness })}>
              {OPTIONS.map((value) => <option key={value} value={value}>{OPENNESS_LABELS[value]}</option>)}
            </select>
          </label>
          <label className="text-xs text-brand-muted">
            Offen für Überlassung (AÜ)
            <select className={`${selectClass} mt-1 block w-full`} value={summary.open_for_staffing} disabled={busy} onChange={(event) => void change({ open_for_staffing: event.target.value as Openness })}>
              {OPTIONS.map((value) => <option key={value} value={value}>{OPENNESS_LABELS[value]}</option>)}
            </select>
          </label>
        </div>
        <ErrorBanner message={message} className="mt-3" />
        <ul className="mt-4 space-y-1.5 border-t border-white/10 pt-3 text-sm text-brand-soft">
          {summary.items.length === 0 && <li className="text-brand-muted">Aktuell in keinem Prozess und keinem Einsatz.</li>}
          {summary.items.map((item, index) => (
            <li key={`${item.channel}-${item.entity_id ?? index}`}>
              {itemDetail(item)}
              {!item.details_visible && <span className="ml-2 text-[10.45px] text-brand-muted">(Details nur für Betreuer und Admins)</span>}
            </li>
          ))}
        </ul>
        <p className="mt-3 text-[10.45px] text-brand-muted">
          Für Überlassung kann eine eigene Einwilligung des Kandidaten nötig sein (Zweck der Verarbeitung) – offene Rechtsfrage, bitte klären.
        </p>
      </CardContent>
    </Card>
  );
}
