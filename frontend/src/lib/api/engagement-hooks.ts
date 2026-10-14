"use client";

// NOMICON: gemeinsamer Kandidatenstatus - SWR-Hooks.
import useSWR, { mutate } from "swr";
import { getConflictMode, getEngagement, getEngagementSummaries } from "./engagement";

export function useEngagement(candidateId: string) {
  return useSWR(`/candidates/${candidateId}/engagement`, () => getEngagement(candidateId), {
    revalidateOnFocus: true,
    dedupingInterval: 5_000,
  });
}

/** Eine Sammelabfrage für eine ganze Seite (Liste/Suche) statt einer Abfrage je Kandidat. */
export function useEngagementSummaries(candidateIds: string[]) {
  const key = candidateIds.length > 0 ? `/engagement/summary?${candidateIds.join(",")}` : null;
  return useSWR(key, () => getEngagementSummaries(candidateIds), {
    revalidateOnFocus: false,
    dedupingInterval: 10_000,
    keepPreviousData: true,
  });
}

export function useConflictMode(enabled: boolean) {
  return useSWR(enabled ? "/admin/engagement-settings" : null, getConflictMode);
}

export function refreshEngagement(candidateId?: string) {
  return Promise.all([
    candidateId ? mutate(`/candidates/${candidateId}/engagement`) : Promise.resolve(),
    mutate((key) => typeof key === "string" && key.startsWith("/engagement/summary")),
  ]);
}
