"use client";

import useSWR, { type SWRConfiguration } from "swr";
import { mutate } from "swr";
import {
  getCandidates,
  getClients,
  getContacts,
  getMailingGroups,
  getReactivationCandidates,
} from "./queries";
import type { Candidate, ClientCompany, Contact, DataResult, MailingGroup } from "./types";

/** Genuine client-side Caching fuer wiederholt besuchte Listen-Seiten: SWRs
 * Cache lebt im Client-Bundle und ueberlebt Next.js App-Router-Navigation
 * (kein Full-Page-Reload) - ein erneuter Besuch von /kandidaten zeigt die
 * zuletzt geladenen Daten sofort an, statt komplett neu vom Server zu holen.
 * `fallbackData` ist die serverseitig vorgerenderte erste Ladung (schneller
 * erster Paint, kein Client-Waterfall). Mutation-Hooks (siehe unten) rufen
 * `mutate()` gezielt auf, damit Aenderungen sofort sichtbar sind - anders als
 * ein pauschales Next.js-Fetch-Cache-Revalidate-Fenster, das nach einer
 * Bearbeitung fuer bis zu 30s veraltete Daten zeigen wuerde. */
const swrConfig: SWRConfiguration = {
  revalidateOnFocus: false,
  revalidateIfStale: false,
  dedupingInterval: 30_000,
};

/** Ohne fallbackData: der erste Besuch in der Session zeigt ein Skeleton
 * waehrend des Client-Fetches, jeder weitere Besuch (Client-Navigation via
 * next/link) liest aus SWRs Cache - echt sofort, ohne erneuten Server-
 * Roundtrip. Ein serverseitiger Server-Component-Fetch in page.tsx wuerde
 * hier NICHT helfen: Next.js fuehrt Server Components bei jeder Navigation
 * neu aus, das haette also weiterhin bei jedem Seitenbesuch alle ~2900
 * Kandidaten neu vom Backend geholt - genau das Problem, das dieser Hook
 * loest, indem der Datenzugriff komplett auf den Client verlagert wird. */
export function useCandidatesCache() {
  return useSWR<DataResult<Candidate[]>>("/candidates", getCandidates, swrConfig);
}

/** Nach Anlegen/Bearbeiten/Loeschen eines Kandidaten aufrufen, damit die
 * SWR-gecachte Kandidatenliste die Aenderung sofort zeigt, statt bis zu
 * dedupingInterval (30s) veraltete Daten zu behalten. */
export function invalidateCandidatesCache() {
  return mutate("/candidates");
}

/** Reaktivierungsliste (bereits bestehender Endpoint aus Phase A) fuer den
 * "Erneut kontaktieren"-Filter auf /kandidaten - laedt nur bei aktivem
 * Filter (SWR ist lazy per Key: `null` als Key ueberspringt den Fetch). */
export function useReactivationCandidatesCache(enabled: boolean) {
  return useSWR<DataResult<Candidate[]>>(
    enabled ? "/candidates/reactivation-list" : null,
    () => getReactivationCandidates(),
    swrConfig,
  );
}

/** Gleiches Client-Cache-Muster wie useCandidatesCache, fuer /kanzleien. */
export function useClientsCache() {
  return useSWR<DataResult<ClientCompany[]>>("/clients", getClients, swrConfig);
}

export function invalidateClientsCache() {
  return mutate("/clients");
}

/** Gleiches Client-Cache-Muster wie useCandidatesCache, fuer /kontakte. */
export function useContactsCache() {
  return useSWR<DataResult<Contact[]>>("/contacts", getContacts, swrConfig);
}

export function invalidateContactsCache() {
  return mutate("/contacts");
}

/** Gleiches Client-Cache-Muster wie useCandidatesCache, fuer Mailing-Gruppen
 * (Punkt 6/7: Geo-Mapping-Auswahl, "Fuer Mailing nutzen", Mailing-Seite). */
export function useMailingGroupsCache() {
  return useSWR<DataResult<MailingGroup[]>>(
    "/mailing-groups",
    () => getMailingGroups(),
    swrConfig,
  );
}

export function invalidateMailingGroupsCache() {
  return mutate("/mailing-groups");
}
