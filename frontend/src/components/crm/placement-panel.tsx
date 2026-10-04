"use client";

import { useEffect, useMemo, useState } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { ErrorBanner } from "@/components/crm/error-banner";
import { createPlacement, deletePlacement, getPlacement, updatePlacement } from "@/lib/api/queries";
import { InvoiceSection } from "@/components/crm/invoice-section";
import type { Placement, PlacementStatus } from "@/lib/api/types";

const labelClass = "mb-1 block text-xs text-brand-muted";
const selectClass = "h-10 w-full rounded-md border border-white/10 bg-brand-surface px-3 text-sm text-brand-text outline-none focus:border-brand-accent";

const STATUS_OPTIONS: { value: PlacementStatus; label: string }[] = [
  { value: "planned", label: "Geplant" },
  { value: "started", label: "Gestartet" },
  { value: "completed", label: "Abgeschlossen" },
  { value: "cancelled", label: "Storniert" },
];

/** "berechnet" = final_salary * fee_percentage/100 * (1 - rabatt_percentage/100),
 * "fix" = fee_fix wird 1:1 uebernommen. Server rechnet dieselbe Formel
 * autoritativ nach (siehe services/recruiting.py::_calculate_fee) - die
 * Live-Anzeige hier ist nur eine Vorschau, keine Quelle der Wahrheit. */
type FeeMode = "berechnet" | "fix";

interface FormState {
  start_date: string;
  final_salary: string;
  fee_percentage: string;
  rabatt_percentage: string;
  fee_fix: string;
  fee_mode: FeeMode;
  guarantee_period_months: string;
  status: PlacementStatus;
}

function emptyForm(): FormState {
  return {
    start_date: "",
    final_salary: "",
    fee_percentage: "",
    rabatt_percentage: "0",
    fee_fix: "",
    fee_mode: "berechnet",
    guarantee_period_months: "6",
    status: "planned",
  };
}

function formFromPlacement(placement: Placement): FormState {
  return {
    start_date: placement.start_date,
    final_salary: String(placement.final_salary),
    fee_percentage: String(placement.fee_percentage),
    rabatt_percentage: String(placement.rabatt_percentage ?? 0),
    fee_fix: placement.fee_fix != null ? String(placement.fee_fix) : "",
    fee_mode: placement.fee_fix != null ? "fix" : "berechnet",
    guarantee_period_months: String(placement.guarantee_period_months),
    status: placement.status,
  };
}

/** Live-Vorschau der Fee waehrend der Eingabe - rein clientseitig, keine
 * Server-Rundtrip. `null` wenn die Eingaben (noch) keine Berechnung
 * zulassen (z.B. Honorarsatz leer im Berechnet-Modus, da der Kanzlei-
 * Standardsatz erst serverseitig aufgeloest wird). */
function previewFee(form: FormState): number | null {
  if (form.fee_mode === "fix") {
    const fix = Number(form.fee_fix);
    return form.fee_fix.trim() && !Number.isNaN(fix) ? fix : null;
  }
  const finalSalary = Number(form.final_salary);
  const feePercentage = Number(form.fee_percentage);
  const rabatt = form.rabatt_percentage.trim() ? Number(form.rabatt_percentage) : 0;
  if (
    !form.final_salary.trim() ||
    Number.isNaN(finalSalary) ||
    !form.fee_percentage.trim() ||
    Number.isNaN(feePercentage) ||
    Number.isNaN(rabatt)
  ) {
    return null;
  }
  return finalSalary * (feePercentage / 100) * (1 - rabatt / 100);
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

  const feePreview = useMemo(() => previewFee(form), [form]);

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
    const isFix = form.fee_mode === "fix";
    if (isFix) {
      const fix = Number(form.fee_fix);
      if (!form.fee_fix.trim() || Number.isNaN(fix) || fix <= 0) {
        setMessage("Bitte eine gültige fixe Fee angeben.");
        return;
      }
    }
    setBusy(true);
    setMessage(null);
    try {
      const rabattPercentage = form.rabatt_percentage.trim() ? Number(form.rabatt_percentage) : 0;
      const feeFix = isFix ? Number(form.fee_fix) : null;
      if (placement) {
        const updated = await updatePlacement(submissionId, {
          start_date: form.start_date,
          final_salary: finalSalary,
          // Leer gelassen = unveraendert (Kanzlei-/Submission-Standardsatz
          // bleibt bestehen) - anders als beim Anlegen wuerde `null` hier
          // serverseitig fee_percentage auf "kein Wert" zuruecksetzen und die
          // Fee-Neuberechnung zum Absturz bringen.
          fee_percentage: form.fee_percentage.trim() ? Number(form.fee_percentage) : undefined,
          rabatt_percentage: rabattPercentage,
          fee_fix: feeFix ?? undefined,
          // Ohne fixe Fee explizit zuruecksetzen (sonst bliebe ein zuvor
          // gesetzter fee_fix-Wert serverseitig stehen, siehe
          // PlacementUpdate.clear_fee_fix).
          clear_fee_fix: !isFix,
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
          rabatt_percentage: rabattPercentage,
          fee_fix: feeFix,
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
          <div key={index} className="h-14 animate-pulse rounded-lg bg-brand-surface" />
        ))}
      </div>
    );
  }

  return (
    <div>
      <p className="mb-3 text-xs font-semibold uppercase tracking-wider text-brand-muted">Placement</p>
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

        <div className="flex gap-1 rounded-md border border-white/10 bg-brand-surface p-1 text-xs">
          <button
            type="button"
            className={`flex-1 rounded px-2 py-1.5 transition ${form.fee_mode === "berechnet" ? "bg-brand-accent text-white" : "text-brand-muted hover:text-brand-text"}`}
            onClick={() => set("fee_mode", "berechnet")}
          >
            Berechnet
          </button>
          <button
            type="button"
            className={`flex-1 rounded px-2 py-1.5 transition ${form.fee_mode === "fix" ? "bg-brand-accent text-white" : "text-brand-muted hover:text-brand-text"}`}
            onClick={() => set("fee_mode", "fix")}
          >
            Fixe Fee eingeben
          </button>
        </div>

        {form.fee_mode === "berechnet" ? (
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
              <label className={labelClass}>Rabatt %</label>
              <Input
                type="number"
                min={0}
                max={100}
                step="0.01"
                value={form.rabatt_percentage}
                onChange={(e) => set("rabatt_percentage", e.target.value)}
              />
            </div>
          </div>
        ) : (
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
            <div>
              <label className={labelClass}>Fixe Fee (€) *</label>
              <Input
                type="number"
                min={0}
                step="0.01"
                required
                value={form.fee_fix}
                onChange={(e) => set("fee_fix", e.target.value)}
              />
            </div>
            <div className="opacity-40">
              <label className={labelClass}>Honorarsatz % / Rabatt % (ausgeblendet bei fixer Fee)</label>
              <div className="flex gap-2">
                <Input type="number" disabled value={form.fee_percentage} onChange={(e) => set("fee_percentage", e.target.value)} />
                <Input type="number" disabled value={form.rabatt_percentage} onChange={(e) => set("rabatt_percentage", e.target.value)} />
              </div>
            </div>
          </div>
        )}

        <p className="text-sm font-medium text-brand-text">
          Fee (Vorschau):{" "}
          {feePreview != null
            ? feePreview.toLocaleString("de-DE", { style: "currency", currency: "EUR" })
            : "—"}
        </p>

        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
          <div>
            <label className={labelClass}>Gewährleistung (Monate)</label>
            <Input
              type="number"
              min={0}
              value={form.guarantee_period_months}
              onChange={(e) => set("guarantee_period_months", e.target.value)}
            />
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
        </div>
        {placement && (
          <p className="text-xs text-brand-dim">
            Gespeicherte Fee: {placement.calculated_fee.toLocaleString("de-DE")} € · Gewährleistung bis{" "}
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
      {placement && <InvoiceSection placement={placement} />}
    </div>
  );
}
