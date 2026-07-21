"use client";

import type { Dispatch, SetStateAction } from "react";
import { createInterview, deleteInterview, updateInterview } from "@/lib/api/queries";
import type { Interview, InterviewCreate, InterviewUpdate } from "@/lib/api/types";

/** Optimistic-UI-Mutationen fuer Interview-Runden - gemeinsam genutzt von
 * der Prozesse-Kanban-Karte (submission-views.tsx, dort verwaltet der
 * State ALLE Interviews aller Prozesse auf einmal) und dem Interview-Panel
 * der Stufen-Bearbeitung auf der Kandidat-Detailseite
 * (interview-rounds-panel.tsx, dort nur die Interviews EINES Prozesses) -
 * beide Aufrufer bringen ihren eigenen `interviews`-State mit, hier steckt
 * nur die (vorher in submission-views.tsx duplizierte) Mutations-Logik:
 * sofort im lokalen State aendern, bei Fehler exakt den vorherigen Zustand
 * wiederherstellen und ueber die uebergebene `setMessage`-Funktion
 * informieren. Der automatische Kalender-Sync eines Interviews passiert
 * serverseitig, hier nichts zu tun. */
export function useInterviewMutations(
  interviews: Interview[],
  setInterviews: Dispatch<SetStateAction<Interview[]>>,
  setMessage: (message: string | null) => void,
) {
  async function createInterviewOptimistic(submissionId: string, payload: InterviewCreate) {
    const tempId = `temp-${Date.now()}`;
    const now = new Date().toISOString();
    const optimistic: Interview = {
      id: tempId,
      created_at: now,
      updated_at: now,
      submission_id: submissionId,
      scheduled_at: payload.scheduled_at,
      interview_type: payload.interview_type,
      location_or_link: payload.location_or_link ?? null,
      participants: payload.participants ?? [],
      status: payload.status ?? "scheduled",
      notes: payload.notes ?? null,
    };
    setInterviews((current) => [...current, optimistic]);
    setMessage(null);
    try {
      const created = await createInterview(submissionId, payload);
      setInterviews((current) => current.map((item) => (item.id === tempId ? created : item)));
    } catch (error) {
      setInterviews((current) => current.filter((item) => item.id !== tempId));
      setMessage(error instanceof Error ? error.message : "Interview konnte nicht angelegt werden.");
    }
  }

  async function updateInterviewOptimistic(interview: Interview, payload: InterviewUpdate) {
    const previous = interviews;
    setInterviews((current) =>
      current.map((item) => (item.id === interview.id ? { ...item, ...payload } : item)),
    );
    setMessage(null);
    try {
      const updated = await updateInterview(interview.submission_id, interview.id, payload);
      setInterviews((current) => current.map((item) => (item.id === interview.id ? updated : item)));
    } catch (error) {
      setInterviews(previous);
      setMessage(error instanceof Error ? error.message : "Interview konnte nicht aktualisiert werden.");
    }
  }

  async function deleteInterviewOptimistic(interview: Interview) {
    const previous = interviews;
    setInterviews((current) => current.filter((item) => item.id !== interview.id));
    setMessage(null);
    try {
      await deleteInterview(interview.submission_id, interview.id);
    } catch (error) {
      setInterviews(previous);
      setMessage(error instanceof Error ? error.message : "Interview konnte nicht gelöscht werden.");
    }
  }

  return { createInterviewOptimistic, updateInterviewOptimistic, deleteInterviewOptimistic };
}
