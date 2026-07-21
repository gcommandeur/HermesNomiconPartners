"use client";

import { useState } from "react";
import { Modal } from "@/components/ui/modal";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import type { Interview, InterviewCreate, InterviewStatus, InterviewUpdate } from "@/lib/api/types";

const labelClass = "mb-1 block text-xs text-[#94A3B8]";
const textareaClass = "min-h-20 w-full rounded-md border border-white/10 bg-[#0D1B2E] p-3 text-sm text-[#F8FAFC] outline-none focus:border-[#1F5FA8]";
const selectClass = "h-10 w-full rounded-md border border-white/10 bg-[#0D1B2E] px-3 text-sm text-[#F8FAFC] outline-none focus:border-[#1F5FA8]";

const INTERVIEW_TYPE_SUGGESTIONS = ["Erstgespräch", "2. Runde", "Finale", "Video-Interview", "Vor-Ort-Termin"];

const STATUS_OPTIONS: { value: InterviewStatus; label: string }[] = [
  { value: "scheduled", label: "Geplant" },
  { value: "completed", label: "Durchgeführt" },
  { value: "cancelled", label: "Abgesagt" },
  { value: "no_show", label: "Nicht erschienen" },
];

/** ISO-Datetime aus dem Backend direkt auf die ersten 16 Zeichen kuerzen statt
 * ueber ein Date-Objekt zu gehen - vermeidet eine Zeitzonen-Reinterpretation
 * durch JS (gleiches Muster wie calendar-event-modal.tsx::toDatetimeLocalValue). */
function toDatetimeLocalValue(iso: string | null | undefined): string {
  if (!iso) return "";
  return iso.slice(0, 16);
}

interface FormState {
  scheduled_at: string;
  interview_type: string;
  location_or_link: string;
  notes: string;
  status: InterviewStatus;
}

function formStateFor(interview: Interview | null, defaultScheduledAt?: string): FormState {
  if (interview) {
    return {
      scheduled_at: toDatetimeLocalValue(interview.scheduled_at),
      interview_type: interview.interview_type,
      location_or_link: interview.location_or_link ?? "",
      notes: interview.notes ?? "",
      status: interview.status,
    };
  }
  return {
    scheduled_at: defaultScheduledAt ?? "",
    interview_type: "",
    location_or_link: "",
    notes: "",
    status: "scheduled",
  };
}

/** Formular zum Anlegen/Bearbeiten einer Interview-Runde eines Prozesses.
 * Rein praesentational - die eigentliche Optimistic-UI-/API-Logik (samt
 * Rollback bei Fehler ueber die bestehende `message`-Fehlerzeile) lebt in
 * submission-views.tsx (gleiches Muster wie applyTransition/updateClient
 * dort), damit ein Fehlschlag nicht blockierend im Modal, sondern konsistent
 * mit den anderen Kanban-Aktionen behandelt wird. */
export function InterviewModal({
  interview,
  defaultScheduledAt,
  onClose,
  onCreate,
  onUpdate,
  onDelete,
}: {
  /** null = neue Runde anlegen, sonst bearbeiten. */
  interview: Interview | null;
  defaultScheduledAt?: string;
  onClose: () => void;
  onCreate: (payload: InterviewCreate) => void;
  onUpdate: (interview: Interview, payload: InterviewUpdate) => void;
  onDelete: (interview: Interview) => void;
}) {
  const [form, setForm] = useState<FormState>(() => formStateFor(interview, defaultScheduledAt));
  const [formError, setFormError] = useState<string | null>(null);

  function set<K extends keyof FormState>(key: K, value: FormState[K]) {
    setForm((current) => ({ ...current, [key]: value }));
  }

  function handleSubmit(event: React.FormEvent) {
    event.preventDefault();
    if (!form.scheduled_at) {
      setFormError("Bitte einen Termin angeben.");
      return;
    }
    if (!form.interview_type.trim()) {
      setFormError("Bitte eine Interview-Art angeben.");
      return;
    }
    const shared = {
      scheduled_at: form.scheduled_at,
      interview_type: form.interview_type.trim(),
      location_or_link: form.location_or_link.trim() || null,
      notes: form.notes.trim() || null,
    };
    if (interview) {
      onUpdate(interview, { ...shared, status: form.status });
    } else {
      onCreate(shared);
    }
    onClose();
  }

  function handleDelete() {
    if (!interview) return;
    onDelete(interview);
    onClose();
  }

  return (
    <Modal
      title={interview ? "Interview bearbeiten" : "Interview planen"}
      eyebrow="Prozesse"
      onClose={onClose}
    >
      <form className="space-y-4" onSubmit={handleSubmit}>
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
          <div>
            <label className={labelClass}>Termin *</label>
            <Input
              type="datetime-local"
              required
              value={form.scheduled_at}
              onChange={(e) => set("scheduled_at", e.target.value)}
            />
          </div>
          <div>
            <label className={labelClass}>Interview-Art *</label>
            <Input
              required
              list="interview-type-suggestions"
              placeholder="z.B. Erstgespräch"
              value={form.interview_type}
              onChange={(e) => set("interview_type", e.target.value)}
            />
            <datalist id="interview-type-suggestions">
              {INTERVIEW_TYPE_SUGGESTIONS.map((suggestion) => (
                <option key={suggestion} value={suggestion} />
              ))}
            </datalist>
          </div>
        </div>
        <div>
          <label className={labelClass}>Ort / Link (optional)</label>
          <Input
            placeholder="z.B. Video-Call-Link oder Adresse"
            value={form.location_or_link}
            onChange={(e) => set("location_or_link", e.target.value)}
          />
        </div>
        {interview && (
          <div>
            <label className={labelClass}>Status</label>
            <select
              className={selectClass}
              value={form.status}
              onChange={(e) => set("status", e.target.value as InterviewStatus)}
            >
              {STATUS_OPTIONS.map((option) => (
                <option key={option.value} value={option.value}>{option.label}</option>
              ))}
            </select>
          </div>
        )}
        <div>
          <label className={labelClass}>Notiz (optional)</label>
          <textarea className={textareaClass} value={form.notes} onChange={(e) => set("notes", e.target.value)} />
        </div>

        {formError && (
          <div className="rounded-lg border border-red-400/25 bg-red-950/30 p-3 text-xs text-red-200">
            {formError}
          </div>
        )}

        <div className="flex items-center justify-between gap-2">
          {interview ? (
            <Button type="button" variant="outline" onClick={handleDelete}>
              Löschen
            </Button>
          ) : <span />}
          <div className="flex gap-2">
            <Button type="button" variant="outline" onClick={onClose}>Abbrechen</Button>
            <Button type="submit">Speichern</Button>
          </div>
        </div>
      </form>
    </Modal>
  );
}
