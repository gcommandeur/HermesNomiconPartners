"use client";

import { Modal } from "@/components/ui/modal";
import { InterviewRoundsPanel } from "@/components/crm/interview-rounds-panel";
import { FeedbackPanel } from "@/components/crm/feedback-panel";
import { OfferPanel } from "@/components/crm/offer-panel";
import { PlacementPanel } from "@/components/crm/placement-panel";
import { STAGE_LABELS } from "@/components/crm/submission-stage-bar";
import type { CandidateSubmission, SubmissionStatus } from "@/lib/api/types";

/** Zentrales Bearbeitungs-Panel fuer eine einzelne Stufe eines Prozesses -
 * geoeffnet per Klick auf die SubmissionStageBar der Kandidat-Detailseite.
 * Zeigt je nach Stufe unterschiedlichen Inhalt (Interview-Runden/Feedback/
 * Angebot/Placement). Der Statuswechsel selbst laeuft fuer die
 * Notiz-gestuetzten Stufen (Quali-Call/Shortlist/CV-Sent) komplett
 * ueber das Status-Feld im FeedbackPanel-Formular (Bullhorn-artiges
 * "Action"-Feld) - kein separater "Status setzen"-Button hier mehr, damit es
 * nicht zwei konkurrierende Wege gibt. */
export function StageEditModal({
  submissionId,
  stage,
  currentStatus,
  onClose,
  onTransitioned,
}: {
  submissionId: string;
  stage: SubmissionStatus;
  currentStatus: SubmissionStatus;
  onClose: () => void;
  onTransitioned: (updated: CandidateSubmission) => void;
}) {
  return (
    <Modal title={STAGE_LABELS[stage]} eyebrow="Prozess-Stufe" onClose={onClose} variant="panel">
      <div className="space-y-4">
        {stage === "interview" && (
          <InterviewRoundsPanel submissionId={submissionId} canPlanNew={currentStatus === "interview"} />
        )}
        {(stage === "qualification_call" || stage === "cv_in" || stage === "cv_out") && (
          <FeedbackPanel
            submissionId={submissionId}
            stage={stage}
            currentStatus={currentStatus}
            onTransitioned={onTransitioned}
          />
        )}
        {stage === "offer" && <OfferPanel submissionId={submissionId} />}
        {stage === "placement" && <PlacementPanel submissionId={submissionId} />}
      </div>
    </Modal>
  );
}
