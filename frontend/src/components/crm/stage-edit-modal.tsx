"use client";

import { useState } from "react";
import { Modal } from "@/components/ui/modal";
import { Button } from "@/components/ui/button";
import { ErrorBanner } from "@/components/crm/error-banner";
import { InterviewRoundsPanel } from "@/components/crm/interview-rounds-panel";
import { FeedbackPanel } from "@/components/crm/feedback-panel";
import { OfferPanel } from "@/components/crm/offer-panel";
import { PlacementPanel } from "@/components/crm/placement-panel";
import { STAGE_LABELS } from "@/components/crm/submission-stage-bar";
import { apiPatch } from "@/lib/api/client";
import { isAllowedTransition } from "@/lib/submission-transitions";
import type { CandidateSubmission, SubmissionStatus } from "@/lib/api/types";

/** Zentrales Bearbeitungs-Panel fuer eine einzelne Stufe eines Prozesses -
 * geoeffnet per Klick auf die SubmissionStageBar der Kandidat-Detailseite.
 * Zeigt je nach Stufe unterschiedlichen Inhalt (Interview-Runden/Feedback/
 * Angebot/Placement), aber ein gemeinsames Grundgeruest: Titel = Stufenname,
 * optional oben ein "Status setzen"-Button, wenn die angeklickte Stufe laut
 * lib/submission-transitions.ts vom aktuellen Status aus ein gueltiges Ziel
 * ist (gleiche Regeln wie das Kanban-Drag&Drop in submission-views.tsx). */
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
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<string | null>(null);

  const canSetStatus = stage !== currentStatus && isAllowedTransition(currentStatus, stage);

  async function handleSetStatus() {
    setBusy(true);
    setMessage(null);
    try {
      const updated = await apiPatch<CandidateSubmission>(`/submissions/${submissionId}/transition`, {
        status: stage,
      });
      onTransitioned(updated);
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Statuswechsel fehlgeschlagen.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <Modal title={STAGE_LABELS[stage]} eyebrow="Prozess-Stufe" onClose={onClose} maxWidth="max-w-xl">
      <div className="space-y-4">
        {canSetStatus && (
          <div className="flex items-center justify-between rounded-lg border border-[#1F5FA8]/30 bg-[#1F5FA8]/10 p-3 text-xs text-[#c5dcfa]">
            <span>Prozess ist aktuell im Status „{STAGE_LABELS[currentStatus]}“.</span>
            <Button size="sm" disabled={busy} onClick={() => void handleSetStatus()}>
              {busy ? "Wird gesetzt…" : `Status auf „${STAGE_LABELS[stage]}“ setzen`}
            </Button>
          </div>
        )}

        <ErrorBanner message={message} />

        {stage === "interview" && (
          <InterviewRoundsPanel submissionId={submissionId} canPlanNew={currentStatus === "interview"} />
        )}
        {(stage === "pitch" || stage === "qualification_call" || stage === "cv_in" || stage === "cv_out") && (
          <FeedbackPanel submissionId={submissionId} stage={stage} />
        )}
        {stage === "offer" && <OfferPanel submissionId={submissionId} />}
        {stage === "placement" && <PlacementPanel submissionId={submissionId} />}
      </div>
    </Modal>
  );
}
