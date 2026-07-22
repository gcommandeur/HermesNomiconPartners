"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { Plus } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { ErrorBanner } from "@/components/crm/error-banner";
import { getStageSummary, quickLogCandidateStage } from "@/lib/api/queries";
import type { CandidateStageSummary, FeedbackType } from "@/lib/api/types";

const labelClass = "mb-1 block text-xs text-[#94A3B8]";
const textareaClass = "min-h-16 w-full rounded-md border border-white/10 bg-[#0D1B2E] p-3 text-sm text-[#F8FAFC] outline-none focus:border-[#1F5FA8]";
const selectClass = "h-10 w-full rounded-md border border-white/10 bg-[#0D1B2E] px-3 text-sm text-[#F8FAFC] outline-none focus:border-[#1F5FA8]";

const TYPE_OPTIONS: { value: FeedbackType; label: string }[] = [
  { value: "internal", label: "Intern" },
  { value: "client", label: "Von Kanzlei" },
  { value: "candidate", label: "Von Kandidat/in" },
];

// Gleiche Vorlage wie feedback-panel.tsx::QUALIFICATION_CALL_TEMPLATE - hier
// dupliziert statt importiert, da die beiden Formulare (Quick-Log ohne
// bestehende Submission vs. FeedbackPanel innerhalb eines bereits offenen
// Prozesses) unabhaengig voneinander bedienbar bleiben sollen.
const QUALIFICATION_CALL_TEMPLATE =
  "Aktuelle Stelle: \nQualifikationen: \nGehalt: \nKündigungsfrist: \n\nAufgabenbereich: \n\nWechselgrund: \n\nWeitere Notizen: ";

const STAGE_TILES: { key: keyof CandidateStageSummary; label: string }[] = [
  { key: "pitch", label: "Pitch" },
  { key: "qualification_call", label: "Quali Call" },
  { key: "cv_in", label: "Shortlist" },
  { key: "cv_out", label: "CV Sent" },
  { key: "interview", label: "Interview" },
  { key: "offer", label: "Offer" },
  { key: "placement", label: "Placement" },
];

function toDatetimeLocalValue(iso: string): string {
  return iso.slice(0, 16);
}

interface FormState {
  stage: "pitch" | "qualification_call";
  feedback_type: FeedbackType;
  feedback_text: string;
  received_at: string;
  next_step: string;
}

function emptyForm(stage: "pitch" | "qualification_call"): FormState {
  return {
    stage,
    feedback_type: "internal",
    feedback_text: stage === "qualification_call" ? QUALIFICATION_CALL_TEMPLATE : "",
    received_at: toDatetimeLocalValue(new Date().toISOString()),
    next_step: "",
  };
}

/** Immer sichtbare Prozess-Timeline auf der Kandidat-Detailseite - anders als
 * die bestehende SubmissionStageBar-Sektion (siehe candidate-submission-
 * stages.tsx) NICHT an "mindestens ein Prozess existiert bereits" gebunden:
 * ohne dieses Panel gab es fuer einen frisch angelegten Kandidaten ohne
 * Prozess keine Moeglichkeit, ueberhaupt eine erste Quali-Call-/Pitch-Notiz
 * zu erfassen (Nutzer-Feedback). Eine neue Notiz startet dabei automatisch
 * einen Prozess (siehe queries.ts::quickLogCandidateStage), keine separate
 * "Prozess erstellen"-Aktion noetig. */
export function CandidateProcessLog({ candidateId }: { candidateId: string }) {
  const router = useRouter();
  const [summary, setSummary] = useState<CandidateStageSummary | null>(null);
  const [form, setForm] = useState<FormState | null>(null);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<string | null>(null);

  async function reloadSummary() {
    const result = await getStageSummary(candidateId);
    setSummary(result.data);
  }

  useEffect(() => {
    void reloadSummary();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [candidateId]);

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
      await quickLogCandidateStage(candidateId, {
        stage: form.stage,
        feedback_type: form.feedback_type,
        feedback_text: form.feedback_text.trim(),
        received_at: form.received_at,
        next_step: form.next_step.trim() || null,
      });
      setForm(null);
      await reloadSummary();
      // Falls die Seite bisher keine Submissions kannte, war die gesamte
      // SubmissionStageBar-Sektion serverseitig ausgeblendet (siehe
      // kandidaten/[id]/page.tsx) - ein Refresh laedt die Server Component
      // mit den jetzt vorhandenen Daten neu, ohne einen client-seitigen
      // Zwischenzustand nachbauen zu muessen.
      router.refresh();
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Eintrag konnte nicht gespeichert werden.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="mb-6 space-y-4 border-b border-white/10 pb-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <p className="text-xs font-semibold uppercase tracking-wider text-[#94A3B8]">Prozess-Timeline</p>
        {!form && (
          <div className="flex gap-2">
            <Button size="sm" variant="outline" onClick={() => setForm(emptyForm("pitch"))}>
              <Plus size={13} />Pitch-Notiz
            </Button>
            <Button size="sm" variant="outline" onClick={() => setForm(emptyForm("qualification_call"))}>
              <Plus size={13} />Quali-Call-Notiz
            </Button>
          </div>
        )}
      </div>

      <div className="flex gap-2 overflow-x-auto pb-1">
        {STAGE_TILES.map((tile) => (
          <div
            key={tile.key}
            className="flex shrink-0 items-center gap-2 rounded-full border border-white/10 bg-[#0D1B2E]/75 px-3 py-1.5 text-[11px] text-[#CBD5E1]"
          >
            <span>{tile.label}</span>
            <span className="grid size-5 place-items-center rounded-full bg-[#12243A] text-[10px] font-semibold text-[#D8DADF]">
              {summary ? summary[tile.key] : "…"}
            </span>
          </div>
        ))}
      </div>

      <ErrorBanner message={message} />

      {form && (
        <form className="space-y-3 rounded-lg border border-white/10 bg-[#0D1B2E] p-3" onSubmit={handleSubmit}>
          <p className="text-xs font-semibold text-[#D8DADF]">
            Neue {form.stage === "pitch" ? "Pitch" : "Quali-Call"}-Notiz
          </p>
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
          <div className="flex justify-end gap-2">
            <Button type="button" variant="outline" onClick={() => setForm(null)}>Abbrechen</Button>
            <Button type="submit" disabled={busy}>{busy ? "Speichern…" : "Speichern"}</Button>
          </div>
        </form>
      )}
    </div>
  );
}
