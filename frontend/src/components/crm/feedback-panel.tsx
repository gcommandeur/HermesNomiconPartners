"use client";

import { useEffect, useState } from "react";
import { Plus } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { ErrorBanner } from "@/components/crm/error-banner";
import {
  createFeedback,
  deleteFeedback,
  getFeedback,
  updateFeedback,
} from "@/lib/api/queries";
import { formatDateTime } from "@/lib/utils";
import type { Feedback, FeedbackType, SubmissionStatus } from "@/lib/api/types";

const labelClass = "mb-1 block text-xs text-[#94A3B8]";
const textareaClass = "min-h-16 w-full rounded-md border border-white/10 bg-[#0D1B2E] p-3 text-sm text-[#F8FAFC] outline-none focus:border-[#1F5FA8]";
const selectClass = "h-10 w-full rounded-md border border-white/10 bg-[#0D1B2E] px-3 text-sm text-[#F8FAFC] outline-none focus:border-[#1F5FA8]";

const TYPE_OPTIONS: { value: FeedbackType; label: string }[] = [
  { value: "internal", label: "Intern" },
  { value: "client", label: "Von Kanzlei" },
  { value: "candidate", label: "Von Kandidat/in" },
];

/** ISO-Datetime aus dem Backend direkt auf die ersten 16 Zeichen kuerzen -
 * gleiches Muster wie calendar-event-modal.tsx/interview-modal.tsx
 * (toDatetimeLocalValue): vermeidet eine Zeitzonen-Reinterpretation durch
 * new Date(), Termine/Zeitstempel sind naive Europe/Berlin-Wanduhrzeiten. */
function toDatetimeLocalValue(iso: string | null | undefined): string {
  if (!iso) return "";
  return iso.slice(0, 16);
}

interface FormState {
  id: string | null;
  feedback_type: FeedbackType;
  feedback_text: string;
  received_at: string;
  next_step: string;
}

// Vorlage nur fuer NEUE Quali-Call-Eintraege (kein form.id) - macht das
// Ausfuellen der wichtigsten Eckdaten aus dem Gespraech schneller/
// vollstaendiger, statt mit einem leeren Textfeld zu starten. Bei Pitch-
// Notizen bleibt das Feld wie bisher leer.
const QUALIFICATION_CALL_TEMPLATE =
  "Aktuelle Stelle: \nQualifikationen: \nGehalt: \nKündigungsfrist: \n\nAufgabenbereich: \n\nWechselgrund: \n\nWeitere Notizen: ";

function emptyForm(stage: SubmissionStatus): FormState {
  return {
    id: null,
    feedback_type: "internal",
    feedback_text: stage === "qualification_call" ? QUALIFICATION_CALL_TEMPLATE : "",
    received_at: toDatetimeLocalValue(new Date().toISOString()),
    next_step: "",
  };
}

function formFromEntry(entry: Feedback): FormState {
  return {
    id: entry.id,
    feedback_type: entry.feedback_type,
    feedback_text: entry.feedback_text,
    received_at: toDatetimeLocalValue(entry.received_at),
    next_step: entry.next_step ?? "",
  };
}

/** Generisches "Datum + Notiz"-Panel fuer die Stufen qualification_call/
 * cv_in/cv_out - nutzt das bestehende Feedback-Modell wieder statt neuer
 * DB-Spalten pro Stufe anzulegen (siehe Backend models/recruiting.py::
 * SubmissionFeedback). Mehrere Eintraege je Prozess/Stufe moeglich. */
export function FeedbackPanel({ submissionId, stage }: { submissionId: string; stage: SubmissionStatus }) {
  const [entries, setEntries] = useState<Feedback[]>([]);
  const [loading, setLoading] = useState(true);
  const [message, setMessage] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [form, setForm] = useState<FormState | null>(null);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    getFeedback(submissionId).then((result) => {
      if (cancelled) return;
      setEntries(result.data);
      setLoading(false);
    });
    return () => {
      cancelled = true;
    };
  }, [submissionId]);

  const sorted = [...entries].sort((a, b) => b.received_at.localeCompare(a.received_at));

  function set<K extends keyof FormState>(key: K, value: FormState[K]) {
    setForm((current) => (current ? { ...current, [key]: value } : current));
  }

  async function handleSubmit(event: React.FormEvent) {
    event.preventDefault();
    if (!form) return;
    if (!form.feedback_text.trim()) {
      setMessage("Bitte einen Text eingeben.");
      return;
    }
    if (!form.received_at) {
      setMessage("Bitte ein Datum angeben.");
      return;
    }
    setBusy(true);
    setMessage(null);
    try {
      if (form.id) {
        const updated = await updateFeedback(submissionId, form.id, {
          feedback_type: form.feedback_type,
          feedback_text: form.feedback_text.trim(),
          received_at: form.received_at,
          next_step: form.next_step.trim() || null,
        });
        setEntries((current) => current.map((item) => (item.id === form.id ? updated : item)));
      } else {
        const created = await createFeedback(submissionId, {
          feedback_type: form.feedback_type,
          feedback_text: form.feedback_text.trim(),
          received_at: form.received_at,
          next_step: form.next_step.trim() || null,
          stage,
        });
        setEntries((current) => [...current, created]);
      }
      setForm(null);
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Eintrag konnte nicht gespeichert werden.");
    } finally {
      setBusy(false);
    }
  }

  async function handleDelete(entry: Feedback) {
    const previous = entries;
    setEntries((current) => current.filter((item) => item.id !== entry.id));
    setMessage(null);
    try {
      await deleteFeedback(submissionId, entry.id);
      if (form?.id === entry.id) setForm(null);
    } catch (error) {
      setEntries(previous);
      setMessage(error instanceof Error ? error.message : "Eintrag konnte nicht gelöscht werden.");
    }
  }

  return (
    <div>
      <div className="mb-3 flex items-center justify-between">
        <p className="text-xs font-semibold uppercase tracking-wider text-[#94A3B8]">
          Notizen &amp; Feedback
        </p>
        {!form && (
          <Button size="sm" variant="outline" onClick={() => setForm(emptyForm(stage))}>
            <Plus size={13} />Eintrag hinzufügen
          </Button>
        )}
      </div>

      <ErrorBanner message={message} className="mb-3" />

      {form && (
        <form className="mb-4 space-y-3 rounded-lg border border-white/10 bg-[#0D1B2E] p-3" onSubmit={handleSubmit}>
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
            <div>
              <label className={labelClass}>Datum *</label>
              <Input
                type="datetime-local"
                required
                value={form.received_at}
                onChange={(e) => set("received_at", e.target.value)}
              />
            </div>
            <div>
              <label className={labelClass}>Art</label>
              <select
                className={selectClass}
                value={form.feedback_type}
                onChange={(e) => set("feedback_type", e.target.value as FeedbackType)}
              >
                {TYPE_OPTIONS.map((option) => (
                  <option key={option.value} value={option.value}>{option.label}</option>
                ))}
              </select>
            </div>
          </div>
          <div>
            <label className={labelClass}>Notiz *</label>
            <textarea
              className={textareaClass}
              required
              value={form.feedback_text}
              onChange={(e) => set("feedback_text", e.target.value)}
            />
          </div>
          <div>
            <label className={labelClass}>Nächster Schritt (optional)</label>
            <Input value={form.next_step} onChange={(e) => set("next_step", e.target.value)} />
          </div>
          <div className="flex items-center justify-between gap-2">
            {form.id ? (
              <Button
                type="button"
                variant="outline"
                onClick={() => {
                  const entry = entries.find((item) => item.id === form.id);
                  if (entry) void handleDelete(entry);
                }}
              >
                Löschen
              </Button>
            ) : <span />}
            <div className="flex gap-2">
              <Button type="button" variant="outline" onClick={() => setForm(null)}>Abbrechen</Button>
              <Button type="submit" disabled={busy}>{busy ? "Speichern…" : "Speichern"}</Button>
            </div>
          </div>
        </form>
      )}

      {loading ? (
        <div className="space-y-2">
          {Array.from({ length: 2 }).map((_, index) => (
            <div key={index} className="h-14 animate-pulse rounded-lg bg-[#0D1B2E]" />
          ))}
        </div>
      ) : sorted.length === 0 && !form ? (
        <p className="rounded-lg border border-dashed border-white/10 p-4 text-center text-xs text-[#94A3B8]">
          Noch keine Einträge.
        </p>
      ) : (
        <div className="space-y-2">
          {sorted.map((entry) => (
            <button
              key={entry.id}
              type="button"
              onClick={() => setForm(formFromEntry(entry))}
              className="block w-full rounded-lg border border-white/10 bg-[#0D1B2E] p-3 text-left text-xs hover:border-[#1F5FA8]/50"
            >
              <div className="flex items-center justify-between gap-2">
                <span className="font-semibold text-[#F8FAFC]">
                  {TYPE_OPTIONS.find((option) => option.value === entry.feedback_type)?.label}
                </span>
                <span className="text-[#94A3B8]">{formatDateTime(entry.received_at)}</span>
              </div>
              <p className="mt-1 text-[#CBD5E1]">{entry.feedback_text}</p>
              {entry.next_step && (
                <p className="mt-1 text-[#747C89]">Nächster Schritt: {entry.next_step}</p>
              )}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
