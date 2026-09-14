"use client";

import useSWR, { type SWRConfiguration } from "swr";
import { mutate } from "swr";
import {
  getAdminUsers,
  getAssignableUsers,
  getAuditLogs,
  getCalendarEvents,
  getClients,
  getCockpit,
  getCurrentUser,
  getEmailTemplates,
  getMailAccounts,
  getMailingGroups,
  getReactivationCandidates,
  type CalendarEventQuery,
} from "./queries";
import type {
  AdminUser,
  AuditLogEntry,
  Candidate,
  CalendarEvent,
  ClientCompany,
  Cockpit,
  CurrentUserInfo,
  DataResult,
  EmailTemplate,
  MailAccount,
  MailingGroup,
  UserBrief,
} from "./types";

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

/** Nach Anlegen/Bearbeiten/Loeschen eines Kandidaten aufrufen, damit die
 * SWR-gecachte Kandidatenliste die Aenderung sofort zeigt, statt bis zu
 * dedupingInterval (30s) veraltete Daten zu behalten. Invalidiert per
 * Praefix-Match sowohl den alten statischen "/candidates"-Key als auch die
 * neuen serverseitigen Such-/Pagination-Keys aus useServerSearchList (z.B.
 * "/candidates?search=...&status=...&limit=...&offset=..."). */
export function invalidateCandidatesCache() {
  return mutate((key) => typeof key === "string" && key.startsWith("/candidates"));
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

/** Client-seitiges SWR-Caching des kompletten Kanzlei-Bestands - genutzt fuer
 * kleinere Auswahl-Dropdowns (z.B. contact-create-modal.tsx), NICHT mehr fuer
 * die Kanzleien-Liste selbst (die nutzt seit der Server-Side-Suche
 * useServerSearchList, siehe lib/api/use-server-search.ts). */
export function useClientsCache() {
  return useSWR<DataResult<ClientCompany[]>>("/clients", getClients, swrConfig);
}

export function invalidateClientsCache() {
  return mutate((key) => typeof key === "string" && key.startsWith("/clients"));
}

export function invalidateContactsCache() {
  return mutate((key) => typeof key === "string" && key.startsWith("/contacts"));
}

/** Gleiches Client-Cache-Muster wie useClientsCache, fuer Mailing-Gruppen
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

/** Mail-Vorlagen sind seit "Mailvorlagen editierbar machen" ueber die
 * Verwaltungsansicht auf der Mailing-Seite bearbeitbar (PATCH /email-
 * templates/{key}) - deshalb jetzt client-seitig gecached statt als
 * statischer, einmalig serverseitig gefetchter Prop (vorher: praktisch
 * unveraenderlich, kein Cache noetig). */
export function useEmailTemplatesCache() {
  return useSWR<DataResult<EmailTemplate[]>>(
    "/email-templates",
    () => getEmailTemplates(),
    swrConfig,
  );
}

export function invalidateEmailTemplatesCache() {
  return mutate("/email-templates");
}

/** Der eingeloggte Nutzer (fuer is_admin-Weichen im Kalender/in der
 * Nutzerverwaltung sowie den persoenlichen ICS-Feed-Token in den
 * Einstellungen). `revalidateOnFocus`/`revalidateIfStale` bewusst wie beim
 * Standard-swrConfig aus - aendert sich waehrend einer Session praktisch nie. */
export function useCurrentUser() {
  return useSWR<DataResult<CurrentUserInfo>>("/auth/me", getCurrentUser, swrConfig);
}

/** Kalender-Termine fuer einen Zeitraum (Monats-/Wochenansicht) - der
 * Cache-Key enthaelt den kompletten Query-Range, damit Monats-/Wochenwechsel
 * und Admin-Filter (owner_user_id) jeweils eigene Cache-Eintraege bekommen,
 * statt sich gegenseitig zu ueberschreiben. */
export function useCalendarEventsCache(query: CalendarEventQuery) {
  const key = `/calendar-events?${JSON.stringify(query)}`;
  return useSWR<DataResult<CalendarEvent[]>>(key, () => getCalendarEvents(query), swrConfig);
}

export function invalidateCalendarEventsCache() {
  return mutate((key) => typeof key === "string" && key.startsWith("/calendar-events"));
}

/** Nur fuer Admins (siehe /einstellungen/nutzer) - vollstaendige Nutzerliste
 * fuer die Admin-Nutzerverwaltung. */
export function useAdminUsersCache(enabled: boolean) {
  return useSWR<DataResult<AdminUser[]>>(enabled ? "/users" : null, getAdminUsers, swrConfig);
}

/** Nur fuer Admins - verbundene Postfaecher (siehe
 * /einstellungen/postfaecher). */
export function useMailAccountsCache(enabled: boolean) {
  return useSWR<DataResult<MailAccount[]>>(enabled ? "/mail-accounts" : null, getMailAccounts, swrConfig);
}

export function invalidateMailAccountsCache() {
  return mutate("/mail-accounts");
}

export function invalidateAdminUsersCache() {
  return mutate("/users");
}

/** Fuer JEDEN eingeloggten Nutzer zugaenglich (anders als useAdminUsersCache/
 * GET /users, admin-only) - kleine, selten wechselnde Liste fuer die
 * Owner-Auswahl (owner_user_id) beim Anlegen von Kandidat/Kanzlei/Prozess/
 * Aufgabe (siehe candidate-/client-/submission-create-modal.tsx). */
export function useAssignableUsersCache() {
  return useSWR<DataResult<UserBrief[]>>("/users/assignable", getAssignableUsers, swrConfig);
}

/** Analytics-Seite mit neuem Mehrfach-Nutzerfilter (Nutzer-Vorgabe:
 * "standardauswahl sind alle user... Mehrfachauswahl moeglich") - eigener
 * Cache-Key je Filterauswahl, damit ein Wechsel der ausgewaehlten Nutzer
 * nicht die Ergebnisse eines anderen Filterstands anzeigt. `ownerUserIds`
 * undefined bedeutet "kein Filter" (alle Nutzer, Standardzustand). */
export function useCockpitCache(period: string, ownerUserIds?: string[]) {
  const key = `/cockpit?period=${period}&owner_user_id=${(ownerUserIds ?? []).slice().sort().join(",")}`;
  return useSWR<DataResult<Cockpit>>(key, () => getCockpit(period, ownerUserIds), swrConfig);
}

/** Nur fuer Admins (siehe /einstellungen/audit-log) - chronologisches
 * Audit-Log (Punkt 2 des Auftrags). */
export function useAuditLogsCache(enabled: boolean) {
  return useSWR<DataResult<AuditLogEntry[]>>(
    enabled ? "/audit-logs" : null,
    getAuditLogs,
    swrConfig,
  );
}
