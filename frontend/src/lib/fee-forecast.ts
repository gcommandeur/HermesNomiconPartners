// NOMICON: Fee-Anzeige und Summen der Ansicht Direct. Plain-Modul (Server und Client nutzbar).
// Grundsatz: nie einen Wert erfinden. Fehlt die erwartete Fee ab Interview, steht "Fee offen";
// gewichtet wird nur, wo eine Abschlusswahrscheinlichkeit (0 bis 1) vorhanden ist.
import type { CandidateSubmission, SubmissionStatus } from "./api/types";

const FEE_REQUIRED_FROM: SubmissionStatus[] = ["interview", "offer", "placement"];
const ACTIVE_STAGES: SubmissionStatus[] = ["qualification_call", "cv_in", "cv_out", "interview", "offer"];

export function feeAmount(item: Pick<CandidateSubmission, "expected_fee">): number | null {
  if (item.expected_fee === null || item.expected_fee === undefined || item.expected_fee === "") return null;
  const value = Number(item.expected_fee);
  return Number.isFinite(value) ? value : null;
}

/** Ab Interview ist die erwartete Fee Pflicht; fehlt sie (Altfälle), zeigt die Oberfläche "Fee offen". */
export function feeIsOpen(item: Pick<CandidateSubmission, "expected_fee" | "status">): boolean {
  return FEE_REQUIRED_FROM.includes(item.status) && feeAmount(item) === null;
}

export function formatEuro(value: number): string {
  return `${Math.round(value).toLocaleString("de-DE")} €`;
}

export type StageSummary = {
  count: number;
  /** Summe der tatsächlich hinterlegten erwarteten Fees. */
  sum: number;
  /** Fee × Abschlusswahrscheinlichkeit, nur für Prozesse mit Wahrscheinlichkeit. */
  weighted: number;
  /** Prozesse mit Fee, aber ohne Wahrscheinlichkeit (fehlen in `weighted`). */
  withoutProbability: number;
  /** Prozesse ab Interview ohne Fee. */
  open: number;
};

export function summarizeItems(items: CandidateSubmission[]): StageSummary {
  const summary: StageSummary = { count: items.length, sum: 0, weighted: 0, withoutProbability: 0, open: 0 };
  for (const item of items) {
    const fee = feeAmount(item);
    if (fee === null) {
      if (feeIsOpen(item)) summary.open += 1;
      continue;
    }
    summary.sum += fee;
    if (item.closing_probability === null || item.closing_probability === undefined) summary.withoutProbability += 1;
    else summary.weighted += fee * item.closing_probability;
  }
  return summary;
}

export function isActiveStage(status: SubmissionStatus): boolean {
  return ACTIVE_STAGES.includes(status);
}

export type PipelineKpis = {
  pipelineValue: number;
  expectedWeighted: number;
  openFees: number;
  overdueFollowUps: number;
};

/** Kennzahlen der Kopfzeile über alle laufenden Prozesse (Quali Call bis Offer, nicht archiviert). */
export function pipelineKpis(items: CandidateSubmission[], now: Date = new Date()): PipelineKpis {
  const active = items.filter((item) => isActiveStage(item.status) && !item.archived_at);
  const total = summarizeItems(active);
  const endOfToday = new Date(now);
  endOfToday.setHours(23, 59, 59, 999);
  return {
    pipelineValue: total.sum,
    expectedWeighted: total.weighted,
    openFees: total.open,
    overdueFollowUps: active.filter((item) => item.follow_up_at && new Date(item.follow_up_at) <= endOfToday).length,
  };
}
