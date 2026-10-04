"use client";

import { Check, X } from "lucide-react";
import { cn } from "@/lib/utils";
import type { SubmissionStatus } from "@/lib/api/types";

// STAGE_ORDER/STAGE_LABELS leben jetzt in lib/stage-labels.ts (plain Modul
// ohne "use client") - re-exportiert hier, damit bestehende Importstellen
// unveraendert bleiben. Siehe dort fuer die Begruendung (Server Components
// wie app/analytics/page.tsx bekamen aus diesem "use client"-Modul sonst nur
// "undefined" statt der echten Werte).
import { STAGE_LABELS, STAGE_ORDER } from "@/lib/stage-labels";
export { STAGE_LABELS, STAGE_ORDER };

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
      {label && <p className="mb-2 text-xs font-semibold text-brand-platinum">{label}</p>}
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
                    "grid size-6 shrink-0 place-items-center rounded-full border text-[9.5px] transition-colors group-hover:border-brand-accent",
                    reached
                      ? "border-brand-accent bg-brand-accent text-white"
                      : "border-white/15 bg-transparent text-brand-gray-dark",
                    isCurrent && "ring-2 ring-brand-accent/40",
                  )}
                >
                  {reached ? <Check size={12} /> : index + 1}
                </div>
                <span className={cn("whitespace-nowrap text-[9.5px] group-hover:text-white", reached ? "text-brand-platinum" : "text-brand-gray-dark")}>
                  {stage.label}
                </span>
              </button>
              {index < STAGE_ORDER.length - 1 && (
                <div className={cn("mx-1.5 h-px flex-1", reached && index < reachedIndex ? "bg-brand-accent" : "bg-white/10")} />
              )}
            </div>
          );
        })}
        {isCancelled && (
          <div className="ml-3 flex shrink-0 items-center gap-1.5 rounded-full border border-red-400/30 bg-red-950/30 px-2.5 py-1 text-[9.5px] text-red-200">
            <X size={11} />Abgebrochen
          </div>
        )}
        </div>
      </div>
    </div>
  );
}
