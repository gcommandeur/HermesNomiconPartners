"use client";

import { useEffect, useState } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { ErrorBanner } from "@/components/crm/error-banner";
import { createPlacement, deletePlacement, getPlacement, updatePlacement } from "@/lib/api/queries";
import type { Placement, PlacementStatus } from "@/lib/api/types";

const labelClass = "mb-1 block text-xs text-[#94A3B8]";
const selectClass = "h-10 w-full rounded-md border border-white/10 bg-[#0D1B2E] px-3 text-sm text-[#F8FAFC] outline-none focus:border-[#1F5FA8]";

const STATUS_OPTIONS: { value: PlacementStatus; label: string }[] = [
  { value: "planned", label: "Geplant" },
  { value: "started", label: "Gestartet" },
  { value: "completed", label: "Abgeschlossen" },
  { value: "cancelled", label: "Storniert" },
];

interface FormState {
  start_date: string;
  final_salary: string;
  fee_percentage: string;
  guarantee_period_months: string;
  status: PlacementStatus;
}

function emptyForm(): FormState {
  return { start_date: "", final_salary: "", fee_percentage: "", guarantee_period_months: "6", status: "planned" };
}

function formFromPlacement(placement: Placement): FormState {
  return {
    start_date: placement.start_date,
    final_salary: String(placement.final_salary),
    fee_percentage: String(placement.fee_percentage),
    guarantee_period_months: String(placement.guarantee_period_months),
    status: placement.status,
  };
}

/** Placement-Formular fuer die Stufe "placement" - singulaer (ein Placement
 * pro Prozess, siehe Backend: kein :id-Segment im Pfad). fee_percentage
 * bleibt leer/optional beim Anlegen -> Backend uebernimmt dann den
 * Kanzlei-Standardsatz (siehe services/recruiting.py::_resolve_fee_percentage). */
export function PlacementPanel({ submissionId }: { submissionId: string }) {
  const [placement, setPlacement] = useState<Placement | null>(null);
  const [loading, setLoading] = useState(true);
  const [message, setMessage] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [form, setForm] = useState<FormState>(emptyForm());

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    getPlacement(submissionId).then((data) => {
      if (cancelled) return;
      setPlacement(data);
      setForm(data ? formFromPlacement(data) : emptyForm());
      setLoading(false);
    });
    return () => {
      cancelled = true;
    };
  }, [submissionId]);

  function set<K extends keyof FormState>(key: K, value: FormState[K]) {
    setForm((state) => ({ ...state, [key]: value }));
  }

  async function handleSubmit(event: React.FormEvent) {
    event.preventDefault();
    const finalSalary = Number(form.final_salary);
    if (!form.start_date) {
      setMessage("Bitte ein Startdatum angeben.");
      return;
    }
    if (!form.final_salary || Number.isNaN(finalSalary) || finalSalary <= 0) {
      setMessage("Bitte ein gültiges finales Gehalt angeben.");
      return;
    }
    setBusy(true);
    setMessage(null);
    try {
      if (placement) {
        const updated = await updatePlacement(submissionId, {
          start_date: form.start_date,
          final_salary: finalSalary,
          fee_percentage: form.fee_percentage.trim() ? Number(form.fee_percentage) : undefined,
          guarantee_period_months: Number(form.guarantee_period_months) || 0,
          status: form.status,
        });
        setPlacement(updated);
        setForm(formFromPlacement(updated));
      } else {
        const created = await createPlacement(submissionId, {
          start_date: form.start_date,
          final_salary: finalSalary,
          fee_percentage: form.fee_percentage.trim() ? Number(form.fee_percentage) : null,
          guarantee_period_months: Number(form.guarantee_period_months) || 0,
          status: form.status,
        });
        setPlacement(created);
        setForm(formFromPlacement(created));
      }
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Placement konnte nicht gespeichert werden.");
    } finally {
      setBusy(false);
    }
  }

  async function handleDelete() {
    if (!placement) return;
    setBusy(true);
    setMessage(null);
    try {
      await deletePlacement(submissionId);
      setPlacement(null);
      setForm(emptyForm());
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Placement konnte nicht gelöscht werden.");
    } finally {
      setBusy(false);
    }
  }

  if (loading) {
    return (
      <div className="space-y-2">
        {Array.from({ length: 2 }).map((_, index) => (
          <div key={index} className="h-14 animate-pulse rounded-lg bg-[#0D1B2E]" />
        ))}
      </div>
    );
  }

  return (
    <div>
      <p className="mb-3 text-xs font-semibold uppercase tracking-wider text-[#94A3B8]">Placement</p>
      <ErrorBanner message={message} className="mb-3" />
      <form className="space-y-3" onSubmit={handleSubmit}>
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
          <div>
            <label className={labelClass}>Startdatum *</label>
            <Input type="date" required value={form.start_date} onChange={(e) => set("start_date", e.target.value)} />
          </div>
          <div>
            <label className={labelClass}>Finales Gehalt *</label>
            <Input
              type="number"
              min={0}
              step="0.01"
              required
              value={form.final_salary}
              onChange={(e) => set("final_salary", e.target.value)}
            />
          </div>
        </div>
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
          <div>
            <label className={labelClass}>Honorarsatz % (leer = Kanzlei-Standard)</label>
            <Input
              type="number"
              min={0}
              max={100}
              step="0.01"
              value={form.fee_percentage}
              onChange={(e) => set("fee_percentage", e.target.value)}
            />
          </div>
          <div>
            <label className={labelClass}>Gewährleistung (Monate)</label>
            <Input
              type="number"
              min={0}
              value={form.guarantee_period_months}
              onChange={(e) => set("guarantee_period_months", e.target.value)}
            />
          </div>
        </div>
        <div>
          <label className={labelClass}>Status</label>
          <select
            className={selectClass}
            value={form.status}
            onChange={(e) => set("status", e.target.value as PlacementStatus)}
          >
            {STATUS_OPTIONS.map((option) => (
              <option key={option.value} value={option.value}>{option.label}</option>
            ))}
          </select>
        </div>
        {placement && (
          <p className="text-xs text-[#747C89]">
            Berechnete Fee: {placement.calculated_fee.toLocaleString("de-DE")} € · Gewährleistung bis{" "}
            {placement.warranty_end_date}
          </p>
        )}
        <div className="flex items-center justify-between gap-2">
          {placement ? (
            <Button type="button" variant="outline" disabled={busy} onClick={handleDelete}>
              Löschen
            </Button>
          ) : <span />}
          <Button type="submit" disabled={busy}>
            {busy ? "Speichern…" : placement ? "Änderungen speichern" : "Placement anlegen"}
          </Button>
        </div>
      </form>
    </div>
  );
}
