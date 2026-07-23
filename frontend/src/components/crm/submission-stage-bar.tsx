"use client";

import { Check, X } from "lucide-react";
import { cn } from "@/lib/utils";
import type { SubmissionStatus } from "@/lib/api/types";

// Stufen orientieren sich am bestehenden SubmissionStatus-Enum (Backend:
// cc_crm.models.enums.SubmissionStatus) - keine neuen Stufen erfunden.
// "cancelled" ist kein Fortschritts-Schritt, sondern ein Abbruch und wird
// separat als roter Endzustand markiert (siehe STAGE_ORDER/isCancelled).
export const STAGE_ORDER: { status: SubmissionStatus; label: string }[] = [
  { status: "qualification_call", label: "Quali Call" },
  { status: "cv_in", label: "Shortlist" },
  { status: "cv_out", label: "CV Sent" },
  { status: "interview", label: "Interview" },
  { status: "offer", label: "Offer" },
  { status: "placement", label: "Placement" },
];

/** Anzeigename je Stufe - auch von stage-edit-modal.tsx als Panel-Titel
 * genutzt, damit Kanban/Stage-Bar/Bearbeitungs-Panel immer denselben
 * Wortlaut zeigen. */
export const STAGE_LABELS: Record<SubmissionStatus, string> = {
  qualification_call: "Quali Call",
  cv_in: "Shortlist",
  cv_out: "CV Sent",
  interview: "Interview",
  offer: "Offer",
  placement: "Placement",
  cancelled: "Abgebrochen",
};

export function SubmissionStageBar({
  status,
  label,
  submissionId,
  onStageClick,
}: {
  status: SubmissionStatus;
  label?: string;
  /** Wird von der Bar selbst nicht angezeigt, sondern nur an onStageClick
   * durchgereicht - der Aufrufer weiss so, fuer welchen Prozess das
   * Bearbeitungs-Panel (stage-edit-modal.tsx) geoeffnet werden soll, ohne
   * dass onStageClick selbst die ID kennen muesste. */
  submissionId: string;
  /** Oeffnet das Stufen-Bearbeitungs-Panel fuer die angeklickte Stufe -
   * unabhaengig davon, ob sie bereits erreicht, aktuell oder noch
   * zukuenftig ist: auch abgeschlossene Stufen sollen nachtraeglich
   * Datum/Notiz bearbeitbar bleiben. Nur der Status-Wechsel selbst bleibt im
   * Panel vorwaerts-only (siehe lib/submission-transitions.ts). */
  onStageClick: (stage: SubmissionStatus) => void;
}) {
  const isCancelled = status === "cancelled";
  const reachedIndex = isCancelled
    ? -1
    : STAGE_ORDER.findIndex((stage) => stage.status === status);

  return (
    <div data-submission-id={submissionId}>
      {label && <p className="mb-2 text-xs font-semibold text-[#D8DADF]">{label}</p>}
      {/* Auf schmalen Viewports quetschen sich 6 Stufen + Verbindungslinien
       * sonst zusammen bis zur Unlesbarkeit - overflow-x-auto + min-w-max
       * lassen die Leiste stattdessen horizontal scrollen, statt zu
       * schrumpfen. */}
      <div className="scrollbar-subtle -mx-1 overflow-x-auto px-1">
        <div className="flex min-w-max items-center sm:min-w-0">
        {STAGE_ORDER.map((stage, index) => {
          const reached = !isCancelled && index <= reachedIndex;
          const isCurrent = !isCancelled && index === reachedIndex;
          return (
            <div key={stage.status} className="flex items-center last:flex-none sm:flex-1">
              <button
                type="button"
                onClick={() => onStageClick(stage.status)}
                title={`${stage.label} bearbeiten`}
                className="group flex cursor-pointer flex-col items-center gap-1.5 rounded-md p-1 transition-colors hover:bg-white/5"
              >
                <div
                  className={cn(
                    "grid size-6 shrink-0 place-items-center rounded-full border text-[10px] transition-colors group-hover:border-[#1F5FA8]",
                    reached
                      ? "border-[#1F5FA8] bg-[#1F5FA8] text-white"
                      : "border-white/15 bg-transparent text-[#5b6167]",
                    isCurrent && "ring-2 ring-[#1F5FA8]/40",
                  )}
                >
                  {reached ? <Check size={12} /> : index + 1}
                </div>
                <span className={cn("whitespace-nowrap text-[10px] group-hover:text-white", reached ? "text-[#D8DADF]" : "text-[#5b6167]")}>
                  {stage.label}
                </span>
              </button>
              {index < STAGE_ORDER.length - 1 && (
                <div className={cn("mx-1.5 h-px flex-1", reached && index < reachedIndex ? "bg-[#1F5FA8]" : "bg-white/10")} />
              )}
            </div>
          );
        })}
        {isCancelled && (
          <div className="ml-3 flex shrink-0 items-center gap-1.5 rounded-full border border-red-400/30 bg-red-950/30 px-2.5 py-1 text-[10px] text-red-200">
            <X size={11} />Abgebrochen
          </div>
        )}
        </div>
      </div>
    </div>
  );
}
