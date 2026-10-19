"use client";

import { useState } from "react";
import { SubmissionStageBar } from "@/components/crm/submission-stage-bar";
import { SubmissionSharesPanel } from "@/components/crm/submission-shares-panel";
import { StageEditModal } from "@/components/crm/stage-edit-modal";
import type { CandidateSubmission, ClientCompany, SubmissionStatus } from "@/lib/api/types";

/** Client-Wrapper um SubmissionStageBar auf der Kandidat-Detailseite (die
 * Seite selbst ist eine async Server Component und kann daher keinen
 * eigenen State halten) - haelt den lokalen Submissions-Status (fuer ein
 * sofortiges UI-Update nach einem Statuswechsel im Bearbeitungs-Panel) und
 * welches Stufen-Panel gerade offen ist.
 *
 * Nimmt die rohe clients-Liste statt einer clientName-Funktion entgegen:
 * Funktionen koennen nicht von einer Server Component als Prop an eine
 * Client Component durchgereicht werden (RSC-Serialisierungsgrenze). */
export function CandidateSubmissionStages({
  submissions: initialSubmissions,
  clients,
}: {
  submissions: CandidateSubmission[];
  clients: ClientCompany[];
}) {
  const [submissions, setSubmissions] = useState(initialSubmissions);
  const [editing, setEditing] = useState<{ submissionId: string; stage: SubmissionStatus } | null>(null);

  const editingSubmission = editing
    ? submissions.find((submission) => submission.id === editing.submissionId)
    : undefined;

  const clientName = (clientId: string | null) =>
    clientId ? (clients.find((client) => client.id === clientId)?.name ?? "Kunde") : "Kunde offen";

  return (
    <>
      {submissions.map((submission) => (
        <div key={submission.id} className="space-y-2">
          <SubmissionStageBar
            status={submission.status}
            label={submissions.length > 1 ? clientName(submission.client_company_id) : undefined}
            submissionId={submission.id}
            onStageClick={(stage) => setEditing({ submissionId: submission.id, stage })}
          />
          <SubmissionSharesPanel
            submissionId={submission.id}
            ownerUserId={submission.owner_user_id}
          />
        </div>
      ))}

      {editing && editingSubmission && (
        <StageEditModal
          submissionId={editing.submissionId}
          stage={editing.stage}
          currentStatus={editingSubmission.status}
          onClose={() => setEditing(null)}
          onTransitioned={(updated) => {
            setSubmissions((current) =>
              current.map((submission) => (submission.id === updated.id ? updated : submission)),
            );
            setEditing((current) => (current ? { ...current, stage: updated.status } : current));
          }}
        />
      )}
    </>
  );
}
