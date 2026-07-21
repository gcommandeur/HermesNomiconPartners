"use client";

import { useEffect, useState } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { ErrorBanner } from "@/components/crm/error-banner";
import { createOffer, deleteOffer, getOffers, updateOffer } from "@/lib/api/queries";
import type { Offer, OfferStatus } from "@/lib/api/types";

const labelClass = "mb-1 block text-xs text-[#94A3B8]";
const textareaClass = "min-h-16 w-full rounded-md border border-white/10 bg-[#0D1B2E] p-3 text-sm text-[#F8FAFC] outline-none focus:border-[#1F5FA8]";
const selectClass = "h-10 w-full rounded-md border border-white/10 bg-[#0D1B2E] px-3 text-sm text-[#F8FAFC] outline-none focus:border-[#1F5FA8]";

const STATUS_OPTIONS: { value: OfferStatus; label: string }[] = [
  { value: "draft", label: "Entwurf" },
  { value: "received", label: "Erhalten" },
  { value: "accepted", label: "Angenommen" },
  { value: "declined", label: "Abgelehnt" },
  { value: "withdrawn", label: "Zurückgezogen" },
];

interface FormState {
  offered_salary: string;
  variable_compensation: string;
  start_date: string;
  offer_status: OfferStatus;
  notes: string;
}

function emptyForm(): FormState {
  return { offered_salary: "", variable_compensation: "", start_date: "", offer_status: "received", notes: "" };
}

function formFromOffer(offer: Offer): FormState {
  return {
    offered_salary: String(offer.offered_salary),
    variable_compensation: offer.variable_compensation != null ? String(offer.variable_compensation) : "",
    start_date: offer.start_date ?? "",
    offer_status: offer.offer_status,
    notes: offer.notes ?? "",
  };
}

/** Offer-Formular fuer die Stufe "offer" - bewusst als ein Objekt behandelt
 * (Create falls noch keins existiert, sonst Edit/Delete des vorhandenen),
 * auch wenn das Backend technisch mehrere Offers pro Prozess erlaubt: fuer
 * die Praxis (ein aktuelles Angebot je Prozess) reicht das; bei mehreren
 * wird hier das zuletzt erstellte angezeigt. */
export function OfferPanel({ submissionId }: { submissionId: string }) {
  const [offers, setOffers] = useState<Offer[]>([]);
  const [loading, setLoading] = useState(true);
  const [message, setMessage] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [form, setForm] = useState<FormState>(emptyForm());

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    getOffers(submissionId).then((result) => {
      if (cancelled) return;
      setOffers(result.data);
      const latest = result.data[result.data.length - 1];
      setForm(latest ? formFromOffer(latest) : emptyForm());
      setLoading(false);
    });
    return () => {
      cancelled = true;
    };
  }, [submissionId]);

  const current = offers[offers.length - 1] ?? null;

  function set<K extends keyof FormState>(key: K, value: FormState[K]) {
    setForm((state) => ({ ...state, [key]: value }));
  }

  async function handleSubmit(event: React.FormEvent) {
    event.preventDefault();
    const salary = Number(form.offered_salary);
    if (!form.offered_salary || Number.isNaN(salary) || salary <= 0) {
      setMessage("Bitte ein gültiges Gehalt angeben.");
      return;
    }
    setBusy(true);
    setMessage(null);
    const payload = {
      offered_salary: salary,
      variable_compensation: form.variable_compensation.trim() ? Number(form.variable_compensation) : null,
      start_date: form.start_date || null,
      offer_status: form.offer_status,
      notes: form.notes.trim() || null,
    };
    try {
      if (current) {
        const updated = await updateOffer(submissionId, current.id, payload);
        setOffers((list) => list.map((item) => (item.id === current.id ? updated : item)));
      } else {
        const created = await createOffer(submissionId, payload);
        setOffers((list) => [...list, created]);
      }
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Angebot konnte nicht gespeichert werden.");
    } finally {
      setBusy(false);
    }
  }

  async function handleDelete() {
    if (!current) return;
    setBusy(true);
    setMessage(null);
    try {
      await deleteOffer(submissionId, current.id);
      setOffers((list) => list.filter((item) => item.id !== current.id));
      setForm(emptyForm());
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Angebot konnte nicht gelöscht werden.");
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
      <p className="mb-3 text-xs font-semibold uppercase tracking-wider text-[#94A3B8]">Angebot</p>
      <ErrorBanner message={message} className="mb-3" />
      <form className="space-y-3" onSubmit={handleSubmit}>
        <div className="grid grid-cols-2 gap-3">
          <div>
            <label className={labelClass}>Angebotenes Gehalt *</label>
            <Input
              type="number"
              min={0}
              step="0.01"
              required
              value={form.offered_salary}
              onChange={(e) => set("offered_salary", e.target.value)}
            />
          </div>
          <div>
            <label className={labelClass}>Variable Vergütung (optional)</label>
            <Input
              type="number"
              min={0}
              step="0.01"
              value={form.variable_compensation}
              onChange={(e) => set("variable_compensation", e.target.value)}
            />
          </div>
        </div>
        <div className="grid grid-cols-2 gap-3">
          <div>
            <label className={labelClass}>Startdatum (optional)</label>
            <Input type="date" value={form.start_date} onChange={(e) => set("start_date", e.target.value)} />
          </div>
          <div>
            <label className={labelClass}>Status</label>
            <select
              className={selectClass}
              value={form.offer_status}
              onChange={(e) => set("offer_status", e.target.value as OfferStatus)}
            >
              {STATUS_OPTIONS.map((option) => (
                <option key={option.value} value={option.value}>{option.label}</option>
              ))}
            </select>
          </div>
        </div>
        <div>
          <label className={labelClass}>Notiz (optional)</label>
          <textarea className={textareaClass} value={form.notes} onChange={(e) => set("notes", e.target.value)} />
        </div>
        <div className="flex items-center justify-between gap-2">
          {current ? (
            <Button type="button" variant="outline" disabled={busy} onClick={handleDelete}>
              Löschen
            </Button>
          ) : <span />}
          <Button type="submit" disabled={busy}>
            {busy ? "Speichern…" : current ? "Änderungen speichern" : "Angebot anlegen"}
          </Button>
        </div>
      </form>
    </div>
  );
}
