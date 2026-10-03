"use client";

import { useEffect, useState } from "react";
import { Button } from "@/components/ui/button";
import { ErrorBanner } from "@/components/crm/error-banner";
import {
  enrollCandidate,
  getCandidateEnrollments,
  getSequences,
  stopEnrollment,
} from "@/lib/api/queries";
import { formatDate } from "@/lib/utils";
import type { EnrollmentStatus, OutreachSequence, SequenceChannel, SequenceEnrollment } from "@/lib/api/types";

const selectClass = "h-8 rounded-md border border-white/10 bg-[#0D1B2E] px-2 text-xs text-[#F8FAFC] outline-none focus:border-[#1F5FA8]";

const STATUS_LABEL: Record<EnrollmentStatus, string> = {
  active: "Läuft",
  paused_reply: "Pausiert (Antwort erhalten)",
  completed: "Abgeschlossen",
  stopped: "Gestoppt",
};

const CHANNEL_LABEL: Record<SequenceChannel, string> = {
  email: "E-Mail",
  linkedin: "LinkedIn (Aufgabe)",
  phone: "Telefon (Aufgabe)",
  other: "Sonstiges (Aufgabe)",
};

/** Sequenz-Status am Kandidaten: laufende und beendete Einschreibungen mit
 * aktueller Stufe und naechstem faelligen Schritt, dazu Einschreiben in eine
 * aktive Sequenz und manuelles Stoppen. Den Versand/die Aufgaben erledigt der
 * taegliche Job (scripts/run_outreach_sequences.py), nicht diese Ansicht. */
export function CandidateSequencesPanel({ candidateId }: { candidateId: string }) {
  const [enrollments, setEnrollments] = useState<SequenceEnrollment[]>([]);
  const [sequences, setSequences] = useState<OutreachSequence[]>([]);
  const [selected, setSelected] = useState("");
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    Promise.all([getCandidateEnrollments(candidateId), getSequences()])
      .then(([enrollmentResult, sequenceResult]) => {
        if (cancelled) return;
        setEnrollments(enrollmentResult.data);
        setSequences(sequenceResult.data);
      })
      .catch(() => {
        // Ohne Zugriff/offline bleibt der Bereich einfach leer.
      });
    return () => {
      cancelled = true;
    };
  }, [candidateId]);

  const runningSequenceIds = new Set(
    enrollments.filter((item) => item.status === "active").map((item) => item.sequence_id),
  );
  const available = sequences.filter((sequence) => !runningSequenceIds.has(sequence.id));

  if (sequences.length === 0 && enrollments.length === 0) return null;

  async function handleEnroll() {
    if (!selected) return;
    setBusy(true);
    setMessage(null);
    try {
      const created = await enrollCandidate(selected, candidateId);
      setEnrollments((list) => [created, ...list]);
      setSelected("");
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Einschreiben fehlgeschlagen.");
    } finally {
      setBusy(false);
    }
  }

  async function handleStop(enrollment: SequenceEnrollment) {
    setBusy(true);
    setMessage(null);
    try {
      const updated = await stopEnrollment(enrollment.id);
      setEnrollments((list) => list.map((item) => (item.id === updated.id ? updated : item)));
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Stoppen fehlgeschlagen.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="mb-6 space-y-2 rounded-lg border border-white/10 bg-[#0D1B2E]/60 p-3">
      <p className="text-xs text-[#94A3B8]">Outreach-Sequenzen</p>
      {enrollments.length === 0 && (
        <p className="text-xs text-[#64748B]">In keiner Sequenz eingeschrieben.</p>
      )}
      {enrollments.map((enrollment) => (
        <div
          key={enrollment.id}
          className="flex flex-wrap items-center justify-between gap-2 rounded-md border border-white/10 bg-white/5 px-3 py-2 text-xs text-[#D8DADF]"
        >
          <div>
            <span className="font-medium">{enrollment.sequence_name}</span>
            <span className="ml-2 text-[#94A3B8]">{STATUS_LABEL[enrollment.status]}</span>
            {enrollment.stopped_reason && (
              <span className="ml-2 text-[#94A3B8]">({enrollment.stopped_reason})</span>
            )}
            <div className="mt-0.5 text-[#94A3B8]">
              Schritt {Math.min(enrollment.current_step_index, enrollment.total_steps)} von{" "}
              {enrollment.total_steps} erledigt
              {enrollment.next_step_due_on && enrollment.next_step_channel && (
                <>
                  {" "}
                  · Nächster: {CHANNEL_LABEL[enrollment.next_step_channel]} am{" "}
                  {formatDate(enrollment.next_step_due_on)}
                </>
              )}
            </div>
          </div>
          {(enrollment.status === "active" || enrollment.status === "paused_reply") && (
            <Button type="button" size="sm" variant="ghost" disabled={busy} onClick={() => handleStop(enrollment)}>
              Stoppen
            </Button>
          )}
        </div>
      ))}
      {available.length > 0 && (
        <div className="flex items-center gap-2">
          <select
            className={selectClass}
            value={selected}
            onChange={(event) => setSelected(event.target.value)}
            aria-label="Sequenz auswählen"
          >
            <option value="">Sequenz auswählen…</option>
            {available.map((sequence) => (
              <option key={sequence.id} value={sequence.id}>
                {sequence.name}
              </option>
            ))}
          </select>
          <Button type="button" size="sm" variant="outline" disabled={busy || !selected} onClick={handleEnroll}>
            Einschreiben
          </Button>
        </div>
      )}
      <ErrorBanner message={message} />
    </div>
  );
}
