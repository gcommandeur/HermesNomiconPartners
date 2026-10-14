// NOMICON: gemeinsamer Kandidatenstatus - nur in der Nomicon-Kopie.
// Plain-Modul (kein "use client"): aus Server- und Client-Komponenten nutzbar.
import { apiGet, apiPatch, apiPost, apiPut } from "./client";
import type { components } from "./schema";
import type { DataResult } from "./types";

type Schemas = components["schemas"];

export type CandidateEngagement = Schemas["CandidateEngagementRead"];
export type EngagementItem = Schemas["EngagementItemRead"];
export type EngagementStatus = CandidateEngagement["status"];
export type Openness = "yes" | "no" | "unknown";
export type ConflictMode = Schemas["EngagementSettingsRead"]["conflict_mode"];
export type EngagementFilter = "free_direct" | "free_staffing" | "engaged";

export const ENGAGEMENT_STATUS_LABELS: Record<EngagementStatus, string> = {
  frei: "Frei",
  im_direct: "Im Direct-Prozess",
  im_einsatz: "Im AÜ-Einsatz",
  beides: "Direct und AÜ",
  vermittelt: "Vermittelt",
};

export const OPENNESS_LABELS: Record<Openness, string> = {
  yes: "Ja",
  no: "Nein",
  unknown: "Nicht geklärt",
};

export const ENGAGEMENT_FILTER_LABELS: Record<EngagementFilter, string> = {
  free_direct: "Frei für Direct",
  free_staffing: "Frei für AÜ",
  engaged: "Im Austausch",
};

const STAGE_LABELS: Record<string, string> = {
  qualification_call: "Quali Call",
  cv_in: "CV in",
  cv_out: "CV out",
  interview: "Interview",
  offer: "Offer",
  placement: "vermittelt",
  planned: "geplant",
  active: "aktiv",
};

export function stageLabel(stage: string): string {
  return STAGE_LABELS[stage] ?? stage;
}

const DEMO_FREE = (candidateId: string): CandidateEngagement => ({
  candidate_id: candidateId,
  status: "frei",
  open_for_direct: "unknown",
  open_for_staffing: "unknown",
  items: [],
});

export function getEngagement(candidateId: string): Promise<DataResult<CandidateEngagement>> {
  return apiGet<CandidateEngagement>(`/candidates/${candidateId}/engagement`, DEMO_FREE(candidateId));
}

export async function getEngagementSummaries(candidateIds: string[]): Promise<Record<string, CandidateEngagement>> {
  if (candidateIds.length === 0 || process.env.NEXT_PUBLIC_CC_CRM_DEMO_MODE === "true") return {};
  const rows = await apiPost<CandidateEngagement[]>("/engagement/summary", { candidate_ids: candidateIds });
  return Object.fromEntries(rows.map((row) => [row.candidate_id, row]));
}

export function updateEngagementPrefs(
  candidateId: string,
  body: { open_for_direct?: Openness; open_for_staffing?: Openness },
): Promise<CandidateEngagement> {
  return apiPatch<CandidateEngagement>(`/candidates/${candidateId}/engagement-prefs`, body);
}

export function getConflictMode(): Promise<DataResult<{ conflict_mode: ConflictMode }>> {
  return apiGet<{ conflict_mode: ConflictMode }>("/admin/engagement-settings", { conflict_mode: "warn" });
}

export function saveConflictMode(mode: ConflictMode): Promise<{ conflict_mode: ConflictMode }> {
  return apiPut<{ conflict_mode: ConflictMode }>("/admin/engagement-settings", { conflict_mode: mode });
}

/** Meldung des Servers, wenn ein Kandidat beim Anlegen bereits im Austausch ist (HTTP 409). */
export function isEngagementConflict(message: string): boolean {
  return message.startsWith("Dieser Kandidat ist bereits im Austausch");
}
