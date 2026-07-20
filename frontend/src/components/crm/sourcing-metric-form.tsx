"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { Plus } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Modal } from "@/components/ui/modal";
import { apiPost } from "@/lib/api/client";
import { ErrorBanner } from "@/components/crm/error-banner";
import type { SourcingMetric } from "@/lib/api/types";

const labelClass = "mb-1 block text-xs text-[#94A3B8]";

function isoToday(): string {
  return new Date().toISOString().slice(0, 10);
}

const emptyForm = {
  period_start: isoToday(),
  period_end: isoToday(),
  source: "LinkedIn",
  campaign: "",
  pitches: "0",
  responses: "0",
  positive_responses: "0",
  qualification_calls: "0",
  notes: "",
};

export function SourcingMetricForm() {
  const router = useRouter();
  const [open, setOpen] = useState(false);
  const [form, setForm] = useState(emptyForm);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  function set<K extends keyof typeof form>(key: K, value: string) {
    setForm((current) => ({ ...current, [key]: value }));
  }

  async function handleSubmit(event: React.FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await apiPost<SourcingMetric>("/sourcing-metrics", {
        period_start: form.period_start,
        period_end: form.period_end,
        source: form.source,
        campaign: form.campaign.trim() === "" ? null : form.campaign,
        pitches: Number(form.pitches) || 0,
        responses: Number(form.responses) || 0,
        positive_responses: Number(form.positive_responses) || 0,
        qualification_calls: Number(form.qualification_calls) || 0,
        notes: form.notes.trim() === "" ? null : form.notes,
      });
      setForm(emptyForm);
      setOpen(false);
      router.refresh();
    } catch (exception) {
      setError(exception instanceof Error ? exception.message : "Erfassung fehlgeschlagen.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      <Button size="sm" onClick={() => setOpen(true)}><Plus size={14} />Sourcing-Daten erfassen</Button>
      {open && (
        <Modal title="Sourcing-Daten erfassen" eyebrow="Täglich / wöchentlich" onClose={() => setOpen(false)}>
          <form className="space-y-4" onSubmit={handleSubmit}>
            <div className="grid grid-cols-2 gap-3">
              <div><label className={labelClass}>Zeitraum von</label><Input type="date" required value={form.period_start} onChange={(e) => set("period_start", e.target.value)} /></div>
              <div><label className={labelClass}>Zeitraum bis</label><Input type="date" required value={form.period_end} onChange={(e) => set("period_end", e.target.value)} /></div>
            </div>
            <div className="grid grid-cols-2 gap-3">
              <div><label className={labelClass}>Quelle</label><Input value={form.source} onChange={(e) => set("source", e.target.value)} /></div>
              <div><label className={labelClass}>Kampagne (optional)</label><Input value={form.campaign} onChange={(e) => set("campaign", e.target.value)} /></div>
            </div>
            <div className="grid grid-cols-3 gap-3">
              <div><label className={labelClass}>Versendete Nachrichten</label><Input type="number" min={0} value={form.pitches} onChange={(e) => set("pitches", e.target.value)} /></div>
              <div><label className={labelClass}>Antworten</label><Input type="number" min={0} value={form.responses} onChange={(e) => set("responses", e.target.value)} /></div>
              <div><label className={labelClass}>Positive Antworten</label><Input type="number" min={0} value={form.positive_responses} onChange={(e) => set("positive_responses", e.target.value)} /></div>
            </div>
            <div><label className={labelClass}>Vereinbarte Quali-Calls</label><Input type="number" min={0} value={form.qualification_calls} onChange={(e) => set("qualification_calls", e.target.value)} /></div>
            <div><label className={labelClass}>Notizen</label><Input value={form.notes} onChange={(e) => set("notes", e.target.value)} /></div>
            <ErrorBanner message={error} />
            <div className="flex justify-end">
              <Button type="submit" disabled={busy}>{busy ? "Speichern…" : "Erfassen"}</Button>
            </div>
          </form>
        </Modal>
      )}
    </>
  );
}
