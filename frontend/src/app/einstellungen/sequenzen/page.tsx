"use client";

import { useEffect, useState } from "react";
import { ShieldOff } from "lucide-react";
import { PageHeader } from "@/components/crm/page-header";
import { ErrorBanner } from "@/components/crm/error-banner";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { useCurrentUser } from "@/lib/api/hooks";
import { createSequence, getSequences, updateSequence } from "@/lib/api/queries";
import type { OutreachSequence, SequenceChannel, SequenceStepInput } from "@/lib/api/types";

const selectClass = "h-10 w-full rounded-md border border-white/10 bg-[#0D1B2E] px-3 text-sm text-[#F8FAFC] outline-none focus:border-[#1F5FA8]";
const textareaClass = "min-h-20 w-full rounded-md border border-white/10 bg-[#0D1B2E] p-3 text-sm text-[#F8FAFC] outline-none focus:border-[#1F5FA8]";
const labelClass = "mb-1 block text-xs text-[#94A3B8]";

const CHANNEL_OPTIONS: { value: SequenceChannel; label: string }[] = [
  { value: "email", label: "E-Mail (automatisch versendet)" },
  { value: "linkedin", label: "LinkedIn (erzeugt eine Aufgabe)" },
  { value: "phone", label: "Telefon (erzeugt eine Aufgabe)" },
  { value: "other", label: "Sonstiges (erzeugt eine Aufgabe)" },
];

const PLACEHOLDER_HINT = "Platzhalter: {first_name}, {last_name}, {full_name}, {sender_name}";

function emptyStep(previousOffset = 0): SequenceStepInput {
  return { day_offset: previousOffset, channel: "email", subject: "", body_template: "" };
}

interface Draft {
  id: string | null;
  name: string;
  is_active: boolean;
  steps: SequenceStepInput[];
}

function newDraft(): Draft {
  return { id: null, name: "", is_active: true, steps: [emptyStep(0)] };
}

function draftFrom(sequence: OutreachSequence): Draft {
  return {
    id: sequence.id,
    name: sequence.name,
    is_active: sequence.is_active,
    steps: sequence.steps.map(({ day_offset, channel, subject, body_template }) => ({
      day_offset,
      channel,
      subject,
      body_template: body_template ?? "",
    })),
  };
}

export default function SequenzenPage() {
  const { data: meData, isLoading: meLoading } = useCurrentUser();
  const isAdmin = meData?.data.is_admin ?? false;
  const [sequences, setSequences] = useState<OutreachSequence[]>([]);
  const [draft, setDraft] = useState<Draft | null>(null);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<string | null>(null);

  useEffect(() => {
    if (!isAdmin) return;
    let cancelled = false;
    getSequences(true).then((result) => {
      if (!cancelled) setSequences(result.data);
    });
    return () => {
      cancelled = true;
    };
  }, [isAdmin]);

  if (meLoading) {
    return <div className="h-16 animate-pulse rounded-lg bg-[#0D1B2E]" />;
  }

  if (!isAdmin) {
    return (
      <>
        <PageHeader eyebrow="Einstellungen" title="Outreach-Sequenzen" />
        <Card>
          <CardContent className="flex items-center gap-3 text-sm text-[#94A3B8]">
            <ShieldOff size={18} /> Nur für Admins zugänglich.
          </CardContent>
        </Card>
      </>
    );
  }

  function setStep(index: number, patch: Partial<SequenceStepInput>) {
    setDraft((current) =>
      current
        ? { ...current, steps: current.steps.map((step, i) => (i === index ? { ...step, ...patch } : step)) }
        : current,
    );
  }

  async function handleSave() {
    if (!draft) return;
    setBusy(true);
    setMessage(null);
    const steps = draft.steps.map((step) => ({
      ...step,
      body_template: step.body_template?.trim() ? step.body_template : null,
    }));
    try {
      const saved = draft.id
        ? await updateSequence(draft.id, { name: draft.name, is_active: draft.is_active, steps })
        : await createSequence({ name: draft.name, is_active: draft.is_active, steps });
      setSequences((list) =>
        draft.id ? list.map((item) => (item.id === saved.id ? saved : item)) : [...list, saved],
      );
      setDraft(null);
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Sequenz konnte nicht gespeichert werden.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      <PageHeader eyebrow="Einstellungen" title="Outreach-Sequenzen" />
      <p className="mb-5 max-w-3xl text-sm text-[#94A3B8]">
        Mehrstufige Kontaktfolgen. E-Mail-Schritte gehen automatisch im Namen der zuständigen Person raus; alle
        anderen Kanäle (LinkedIn, Telefon, Sonstiges) erzeugen eine Aufgabe. Antwortet der Kandidat, pausiert die
        Sequenz automatisch. Der tägliche Lauf führt pro Einschreibung höchstens einen Schritt pro Tag aus.
      </p>

      {!draft && (
        <div className="space-y-3">
          {sequences.map((sequence) => (
            <Card key={sequence.id}>
              <CardContent className="flex flex-wrap items-center justify-between gap-3">
                <div>
                  <p className="font-medium">
                    {sequence.name}
                    {!sequence.is_active && <span className="ml-2 text-xs text-[#94A3B8]">(deaktiviert)</span>}
                  </p>
                  <p className="mt-1 text-xs text-[#94A3B8]">
                    {sequence.steps.map((step) => `Tag ${step.day_offset}: ${step.channel}`).join(" · ")}
                  </p>
                </div>
                <Button size="sm" variant="outline" onClick={() => setDraft(draftFrom(sequence))}>
                  Bearbeiten
                </Button>
              </CardContent>
            </Card>
          ))}
          {sequences.length === 0 && <p className="text-sm text-[#94A3B8]">Noch keine Sequenz angelegt.</p>}
          <Button onClick={() => setDraft(newDraft())}>Neue Sequenz</Button>
        </div>
      )}

      {draft && (
        <Card>
          <CardContent className="space-y-4">
            <div className="grid grid-cols-1 gap-4 sm:grid-cols-[1fr_auto]">
              <div>
                <label className={labelClass}>Name</label>
                <Input value={draft.name} onChange={(event) => setDraft({ ...draft, name: event.target.value })} />
              </div>
              <label className="flex items-end gap-2 pb-2 text-sm text-[#D8DADF]">
                <input
                  type="checkbox"
                  checked={draft.is_active}
                  onChange={(event) => setDraft({ ...draft, is_active: event.target.checked })}
                />
                Aktiv
              </label>
            </div>

            <p className="text-xs text-[#94A3B8]">{PLACEHOLDER_HINT}</p>
            {draft.steps.map((step, index) => (
              <div key={index} className="space-y-3 rounded-lg border border-white/10 bg-[#0D1B2E]/60 p-3">
                <div className="grid grid-cols-1 gap-3 sm:grid-cols-[8rem_1fr_auto]">
                  <div>
                    <label className={labelClass}>Tag nach Start</label>
                    <Input
                      type="number"
                      min={0}
                      value={step.day_offset}
                      onChange={(event) => setStep(index, { day_offset: Number(event.target.value) })}
                    />
                  </div>
                  <div>
                    <label className={labelClass}>Kanal</label>
                    <select
                      className={selectClass}
                      value={step.channel}
                      onChange={(event) => setStep(index, { channel: event.target.value as SequenceChannel })}
                    >
                      {CHANNEL_OPTIONS.map((option) => (
                        <option key={option.value} value={option.value}>
                          {option.label}
                        </option>
                      ))}
                    </select>
                  </div>
                  <div className="flex items-end">
                    <Button
                      type="button"
                      size="sm"
                      variant="ghost"
                      disabled={draft.steps.length <= 1}
                      onClick={() => setDraft({ ...draft, steps: draft.steps.filter((_, i) => i !== index) })}
                    >
                      Entfernen
                    </Button>
                  </div>
                </div>
                <div>
                  <label className={labelClass}>{step.channel === "email" ? "Betreff" : "Aufgaben-Titel"}</label>
                  <Input value={step.subject} onChange={(event) => setStep(index, { subject: event.target.value })} />
                </div>
                <div>
                  <label className={labelClass}>
                    {step.channel === "email" ? "Text" : "Beschreibung / Textvorschlag (optional)"}
                  </label>
                  <textarea
                    className={textareaClass}
                    value={step.body_template ?? ""}
                    onChange={(event) => setStep(index, { body_template: event.target.value })}
                  />
                </div>
              </div>
            ))}
            <Button
              type="button"
              size="sm"
              variant="outline"
              onClick={() =>
                setDraft({
                  ...draft,
                  steps: [...draft.steps, emptyStep(draft.steps[draft.steps.length - 1]?.day_offset ?? 0)],
                })
              }
            >
              Schritt hinzufügen
            </Button>

            <ErrorBanner message={message} />
            <div className="flex gap-2">
              <Button disabled={busy || !draft.name.trim()} onClick={handleSave}>
                Speichern
              </Button>
              <Button variant="ghost" disabled={busy} onClick={() => setDraft(null)}>
                Abbrechen
              </Button>
            </div>
          </CardContent>
        </Card>
      )}
    </>
  );
}
