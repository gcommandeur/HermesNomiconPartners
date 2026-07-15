import { Check, X } from "lucide-react";
import { cn } from "@/lib/utils";
import type { SubmissionStatus } from "@/lib/api/types";

// Stufen orientieren sich am bestehenden SubmissionStatus-Enum (Backend:
// cc_crm.models.enums.SubmissionStatus) - keine neuen Stufen erfunden.
// "cancelled" ist kein Fortschritts-Schritt, sondern ein Abbruch und wird
// separat als roter Endzustand markiert (siehe STAGE_ORDER/isCancelled).
const STAGE_ORDER: { status: SubmissionStatus; label: string }[] = [
  { status: "qualification_call", label: "Prescreen" },
  { status: "cv_in", label: "Shortlist" },
  { status: "cv_out", label: "CV Sent" },
  { status: "interview", label: "Interview" },
  { status: "offer", label: "Offer" },
  { status: "placement", label: "Placement" },
];

export function SubmissionStageBar({
  status,
  label,
}: {
  status: SubmissionStatus;
  label?: string;
}) {
  const isCancelled = status === "cancelled";
  const reachedIndex = isCancelled
    ? -1
    : STAGE_ORDER.findIndex((stage) => stage.status === status);

  return (
    <div>
      {label && <p className="mb-2 text-xs font-semibold text-[#D8DADF]">{label}</p>}
      <div className="flex items-center">
        {STAGE_ORDER.map((stage, index) => {
          const reached = !isCancelled && index <= reachedIndex;
          const isCurrent = !isCancelled && index === reachedIndex;
          return (
            <div key={stage.status} className="flex flex-1 items-center last:flex-none">
              <div className="flex flex-col items-center gap-1.5">
                <div
                  className={cn(
                    "grid size-6 shrink-0 place-items-center rounded-full border text-[10px]",
                    reached
                      ? "border-[#1F5FA8] bg-[#1F5FA8] text-white"
                      : "border-white/15 bg-transparent text-[#5b6167]",
                    isCurrent && "ring-2 ring-[#1F5FA8]/40",
                  )}
                  title={stage.label}
                >
                  {reached ? <Check size={12} /> : index + 1}
                </div>
                <span className={cn("whitespace-nowrap text-[10px]", reached ? "text-[#D8DADF]" : "text-[#5b6167]")}>
                  {stage.label}
                </span>
              </div>
              {index < STAGE_ORDER.length - 1 && (
                <div className={cn("mx-1.5 h-px flex-1", reached && index < reachedIndex ? "bg-[#1F5FA8]" : "bg-white/10")} />
              )}
            </div>
          );
        })}
        {isCancelled && (
          <div className="ml-3 flex items-center gap-1.5 rounded-full border border-red-400/30 bg-red-950/30 px-2.5 py-1 text-[10px] text-red-200">
            <X size={11} />Abgebrochen
          </div>
        )}
      </div>
    </div>
  );
}
