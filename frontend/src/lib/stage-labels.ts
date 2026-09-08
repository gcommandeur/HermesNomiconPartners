import type { SubmissionStatus } from "@/lib/api/types";

// Stufen orientieren sich am bestehenden SubmissionStatus-Enum (Backend:
// cc_crm.models.enums.SubmissionStatus) - keine neuen Stufen erfunden.
// "cancelled" ist kein Fortschritts-Schritt, sondern ein Abbruch und wird
// separat als roter Endzustand markiert (siehe STAGE_ORDER/isCancelled in
// submission-stage-bar.tsx).
//
// Bewusst ein PLAIN Modul ohne "use client": Server Components (z.B.
// app/analytics/page.tsx) koennen keine echten Werte aus einem "use
// client"-Modul importieren - dort wird jeder Export in eine Client-
// Referenz umgeschrieben, ein direkter Property-Zugriff serverseitig liefert
// dann "undefined" statt des tatsaechlichen Werts (gefundener Bug: die
// Conversion-Rates-Uebergaenge zeigten "undefined → undefined", als
// STAGE_LABELS noch direkt aus dem "use client"-submission-stage-bar.tsx
// importiert wurde). submission-stage-bar.tsx re-exportiert von hier, damit
// bestehende Importstellen unveraendert bleiben.
// Bewusst NICHT Teil von STAGE_ORDER/STAGE_LABELS oben - Pitch/InMail ist
// keine SubmissionStatus-/Kanban-Stufe (Nutzer-Entscheidung: kein eigener
// Prozess-Status, siehe CandidatePitchLog), wird aber als Stufe 1 der
// konsolidierten 7-Stufen-Pipeline sowohl in der Prozess-Timeline
// (candidate-process-log.tsx) als auch in Analytics (app/analytics/
// page.tsx) angezeigt - ein gemeinsamer Export haelt den Wortlaut konsistent.
export const PITCH_LABEL = "Pitch/InMail";

export const STAGE_ORDER: { status: SubmissionStatus; label: string }[] = [
  { status: "qualification_call", label: "Quali Call" },
  { status: "cv_in", label: "CV In" },
  { status: "cv_out", label: "CV Sent" },
  { status: "interview", label: "Interview" },
  { status: "offer", label: "Offer" },
  { status: "placement", label: "Placement" },
];

/** Anzeigename je Stufe - von Kanban/Stage-Bar/Bearbeitungs-Panel UND der
 * Analytics-Seite genutzt, damit alle Ansichten immer denselben Wortlaut
 * zeigen. */
export const STAGE_LABELS: Record<SubmissionStatus, string> = {
  qualification_call: "Quali Call",
  cv_in: "CV In",
  cv_out: "CV Sent",
  interview: "Interview",
  offer: "Offer",
  placement: "Placement",
  cancelled: "Abgebrochen",
};
