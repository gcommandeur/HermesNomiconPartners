"use client";

import { useEffect, useState } from "react";
import { CalendarPlus } from "lucide-react";
import { Button } from "@/components/ui/button";
import { ErrorBanner } from "@/components/crm/error-banner";
import { InterviewModal } from "@/components/crm/interview-modal";
import { getInterviews } from "@/lib/api/queries";
import { useInterviewMutations } from "@/lib/use-interview-mutations";
import { formatDateTime } from "@/lib/utils";
import type { Interview } from "@/lib/api/types";

const STATUS_LABELS: Record<Interview["status"], string> = {
  scheduled: "Geplant",
  completed: "Durchgeführt",
  cancelled: "Abgesagt",
  no_show: "Nicht erschienen",
};

const STATUS_TONE: Record<Interview["status"], string> = {
  scheduled: "border-[#1F5FA8]/40 text-[#69A7EA]",
  completed: "border-emerald-400/40 text-emerald-300",
  cancelled: "border-red-400/40 text-red-300",
  no_show: "border-red-400/40 text-red-300",
};

/** Interview-Runden EINES Prozesses, mit vollem Bearbeiten/Löschen - genutzt
 * im Stufen-Bearbeitungs-Panel der Kandidat-Detailseite (stage-edit-modal.tsx).
 * Laedt seine Interviews selbststaendig (anders als die kompakten Runden-Chips
 * auf der Prozesse-Kanban-Karte in submission-views.tsx, die die einmalig fuer
 * ALLE Prozesse geladene Liste nur clientseitig gruppieren - hier ist bewusst
 * nur ein einzelner Prozess relevant, ein eigener Request ist hier also kein
 * Performance-Problem). Die eigentliche Anlegen/Aendern/Loeschen-Logik kommt
 * aus lib/use-interview-mutations.ts, damit sie nicht dupliziert wird. */
export function InterviewRoundsPanel({
  submissionId,
  canPlanNew,
}: {
  submissionId: string;
  /** Nur true, wenn der Prozess aktuell im Status "interview" ist - das
   * Backend lehnt neue Interviews sonst ohnehin ab (siehe
   * services/recruiting.py::create_interview). */
  canPlanNew: boolean;
}) {
  const [interviews, setInterviews] = useState<Interview[]>([]);
  const [loading, setLoading] = useState(true);
  const [message, setMessage] = useState<string | null>(null);
  const [modalState, setModalState] = useState<{ interview: Interview | null } | null>(null);
  const { createInterviewOptimistic, updateInterviewOptimistic, deleteInterviewOptimistic } =
    useInterviewMutations(interviews, setInterviews, setMessage);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    getInterviews(submissionId).then((result) => {
      if (cancelled) return;
      setInterviews(result.data);
      setLoading(false);
    });
    return () => {
      cancelled = true;
    };
  }, [submissionId]);

  const sorted = [...interviews].sort((a, b) => a.scheduled_at.localeCompare(b.scheduled_at));

  return (
    <div>
      <div className="mb-3 flex items-center justify-between">
        <p className="text-xs font-semibold uppercase tracking-wider text-[#94A3B8]">
          Interview-Runden
        </p>
        {canPlanNew && (
          <Button size="sm" variant="outline" onClick={() => setModalState({ interview: null })}>
            <CalendarPlus size={13} />Interview planen
          </Button>
        )}
      </div>

      <ErrorBanner message={message} className="mb-3" />

      {loading ? (
        <div className="space-y-2">
          {Array.from({ length: 2 }).map((_, index) => (
            <div key={index} className="h-14 animate-pulse rounded-lg bg-[#0D1B2E]" />
          ))}
        </div>
      ) : sorted.length === 0 ? (
        <p className="rounded-lg border border-dashed border-white/10 p-4 text-center text-xs text-[#94A3B8]">
          {canPlanNew
            ? "Noch keine Interview-Runde geplant."
            : "Interviews koennen erst geplant werden, sobald der Prozess im Status „Interview“ ist."}
        </p>
      ) : (
        <div className="space-y-2">
          {sorted.map((interview, index) => (
            <button
              key={interview.id}
              type="button"
              onClick={() => setModalState({ interview })}
              className="flex w-full items-center justify-between gap-3 rounded-lg border border-white/10 bg-[#0D1B2E] p-3 text-left text-xs hover:border-[#1F5FA8]/50"
            >
              <div className="min-w-0">
                <p className="font-semibold text-[#F8FAFC]">
                  Runde {index + 1} · {interview.interview_type}
                </p>
                <p className="mt-1 text-[#94A3B8]">{formatDateTime(interview.scheduled_at)}</p>
                {interview.location_or_link && (
                  <p className="mt-1 truncate text-[#747C89]">{interview.location_or_link}</p>
                )}
              </div>
              <span
                className={`shrink-0 rounded-full border px-2 py-1 text-[10px] ${STATUS_TONE[interview.status]}`}
              >
                {STATUS_LABELS[interview.status]}
              </span>
            </button>
          ))}
        </div>
      )}

      {modalState && (
        <InterviewModal
          interview={modalState.interview}
          onClose={() => setModalState(null)}
          onCreate={(payload) => void createInterviewOptimistic(submissionId, payload)}
          onUpdate={(interview, payload) => void updateInterviewOptimistic(interview, payload)}
          onDelete={(interview) => void deleteInterviewOptimistic(interview)}
        />
      )}
    </div>
  );
}
