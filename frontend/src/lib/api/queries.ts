import { demoCandidates, demoClients, demoCockpit, demoEmailTemplates, demoSubmissions } from "@/lib/demo-data";
import { demoContacts, demoGeoResults, demoVacancies } from "@/lib/ia-data";
import { apiDelete, apiGet, apiPatch, apiPost } from "./client";
import type { Activity, AdminUser, AuditLogEntry, Candidate, CandidateSubmission, CalendarEvent, CalendarEventType, ClientCompany, ClientDuplicateCandidate, ClientMatch, Cockpit, Contact, CurrentUserInfo, DocumentMeta, EmailTemplate, GeoMappingResult, Interview, InterviewCreate, InterviewUpdate, MailingGroup, PageQuery, Paginated, Placement, Task, UserBrief, Vacancy } from "./types";

// Die Listen-Endpunkte sind serverseitig paginiert (max. 500 Einträge pro
// Seite). Ein einzelner Aufruf mit limit=100 hat bei >100 Datensätzen (z.B.
// 2675 Kandidaten) immer nur den alphabetisch ersten Ausschnitt geliefert -
// alles danach war für die UI unsichtbar, ohne dass irgendwo ein Fehler oder
// Hinweis aufgetaucht wäre ("die neuesten Profile fehlen"-Bug). Diese
// Hilfsfunktion holt stattdessen so lange weitere Seiten nach, bis wirklich
// alle Datensätze (laut total_count) geladen sind.
const PAGE_SIZE = 500;
const MAX_PAGES = 50; // Sicherheitsgrenze, falls total_count je nicht stimmen sollte.

async function fetchAllPages<T>(basePath: string, fallback: T[]): Promise<{ data: T[]; source: "api" | "demo"; error?: string }> {
  const sep = basePath.includes("?") ? "&" : "?";
  const first = await apiGet<T[] | Paginated<T>>(`${basePath}${sep}limit=${PAGE_SIZE}`, fallback);
  if (Array.isArray(first.data)) return { ...first, data: first.data };

  const items = [...first.data.items];
  const total = first.data.total_count;

  for (let guard = 0; items.length < total && guard < MAX_PAGES; guard += 1) {
    const offset = items.length;
    const next = await apiGet<Paginated<T>>(
      `${basePath}${sep}limit=${PAGE_SIZE}&offset=${offset}`,
      { items: [], total_count: total, limit: PAGE_SIZE, offset },
    );
    if (next.data.items.length === 0) break;
    items.push(...next.data.items);
  }

  return { data: items, source: first.source, error: first.error };
}

export async function getCandidates() {
  return fetchAllPages<Candidate>("/candidates", demoCandidates);
}

/** Fragt genau eine Seite (statt des kompletten Bestands) ab - fuer die
 * serverseitig gesuchte/paginierte Kandidatenliste (siehe
 * lib/api/use-server-search.ts). Anders als getCandidates() hier bewusst
 * KEIN Demo-Fallback: eine leere Seite ist ein legitimes Suchergebnis
 * ("keine Treffer"), kein Fehlerzustand. */
export async function getCandidatesPage(query: PageQuery) {
  return apiGet<Paginated<Candidate>>(`/candidates?${pageQueryString(query)}`, {
    items: [],
    total_count: 0,
    limit: query.limit,
    offset: query.offset,
  });
}

function pageQueryString(query: PageQuery): string {
  const params = new URLSearchParams();
  if (query.search?.trim()) params.set("search", query.search.trim());
  if (query.status) params.set("status", query.status);
  if (query.ownerUserId) params.set("owner_user_id", query.ownerUserId);
  params.set("limit", String(query.limit));
  params.set("offset", String(query.offset));
  return params.toString();
}

export async function getCandidate(id: string) {
  const fallback = demoCandidates.find((candidate) => candidate.id === id) ?? demoCandidates[0];
  return apiGet<Candidate>(`/candidates/${id}`, fallback);
}

export async function getReactivationCandidates(thresholdMonths?: number) {
  const query = thresholdMonths ? `?threshold_months=${thresholdMonths}` : "";
  return apiGet<Candidate[]>(`/candidates/reactivation-list${query}`, []);
}

export async function getClients() {
  return fetchAllPages<ClientCompany>("/clients", demoClients);
}

/** Seitenweise Kanzlei-Suche, s. getCandidatesPage(). */
export async function getClientsPage(query: PageQuery) {
  return apiGet<Paginated<ClientCompany>>(`/clients?${pageQueryString(query)}`, {
    items: [],
    total_count: 0,
    limit: query.limit,
    offset: query.offset,
  });
}

/** Warnt vor wahrscheinlich schon vorhandenen Kanzleien mit ähnlichem Namen
 * (Marke, nicht Rechtsform) - blockiert nichts, da mehrere Standorte
 * derselben Marke (Ecovis, Afileon, PWC, ...) ausdrücklich erwünscht sind. */
export async function checkClientDuplicate(name: string, postalCode?: string, excludeId?: string) {
  const params = new URLSearchParams({ name });
  if (postalCode) params.set("postal_code", postalCode);
  if (excludeId) params.set("exclude_id", excludeId);
  const result = await apiGet<ClientDuplicateCandidate[]>(`/clients/check-duplicate?${params.toString()}`, []);
  return result.data;
}

export async function getGroupLocations(clientId: string) {
  return apiGet<ClientCompany[]>(`/clients/${clientId}/group-locations`, []);
}

export async function getSubmissions() {
  return fetchAllPages<CandidateSubmission>("/submissions", demoSubmissions);
}

export async function getPriorityView() {
  return apiGet<CandidateSubmission[]>("/submissions/priority-view", []);
}

/** Alle Interview-Runden ueber alle Prozesse hinweg (ungefiltert) - Basis fuer
 * die Kanban-Karten-Anzeige in submission-views.tsx, die clientseitig nach
 * submission_id gruppiert statt pro Karte einzeln nachzuladen. */
export async function getAllInterviews() {
  return apiGet<Interview[]>("/interviews", []);
}

export async function createInterview(submissionId: string, payload: InterviewCreate) {
  return apiPost<Interview>(`/submissions/${submissionId}/interviews`, payload);
}

export async function updateInterview(
  submissionId: string,
  interviewId: string,
  payload: InterviewUpdate,
) {
  return apiPatch<Interview>(`/submissions/${submissionId}/interviews/${interviewId}`, payload);
}

export async function deleteInterview(submissionId: string, interviewId: string) {
  return apiDelete(`/submissions/${submissionId}/interviews/${interviewId}`);
}

export async function getMailingGroups() {
  return apiGet<MailingGroup[]>("/mailing-groups", []);
}

export async function getActiveWarranties() {
  return apiGet<Placement[]>("/placements/active-warranties", []);
}

export async function getContacts() {
  return fetchAllPages<Contact>("/contacts", demoContacts);
}

/** Seitenweise Kontakte-Suche, s. getCandidatesPage(). Der Endpoint gibt seit
 * der Server-Side-Suche eine Page (mit total_count) statt einer flachen
 * Liste zurueck und liefert client_company_name bereits denormalisiert mit -
 * das Frontend muss dafuer nicht mehr den kompletten Kanzlei-Bestand laden. */
export async function getContactsPage(query: PageQuery) {
  return apiGet<Paginated<Contact>>(`/contacts?${pageQueryString(query)}`, {
    items: [],
    total_count: 0,
    limit: query.limit,
    offset: query.offset,
  });
}

export async function getVacancies() {
  return fetchAllPages<Vacancy>("/vacancies", demoVacancies);
}

export async function getGeoMappingResults() {
  return apiGet<GeoMappingResult[]>("/geo-mapping/results", demoGeoResults);
}

export async function getCockpit(period = "week") {
  return apiGet<Cockpit>(`/cockpit?period=${period}`, demoCockpit);
}

export async function getEmailTemplates() {
  return apiGet<EmailTemplate[]>("/email-templates", demoEmailTemplates);
}

export async function getActivitiesForCandidate(candidateId: string) {
  return apiGet<Activity[]>(`/activities?candidate_id=${candidateId}`, []);
}

export async function getTasksForCandidate(candidateId: string) {
  return apiGet<Task[]>(`/tasks?candidate_id=${candidateId}`, []);
}

export async function getDocumentsForOwner(ownerType: string, ownerId: string) {
  return apiGet<DocumentMeta[]>(`/documents?owner_type=${ownerType}&owner_id=${ownerId}`, []);
}

export async function getCandidateMatches(candidateId: string) {
  return apiGet<ClientMatch[]>(`/candidates/${candidateId}/matches`, []);
}

export interface CalendarEventQuery {
  startFrom?: string;
  startTo?: string;
  eventType?: CalendarEventType;
  ownerUserId?: string;
}

/** Kalender-Termine im Zeitraum [startFrom, startTo] - kein Pagination noetig
 * (ein Monat/eine Woche an Terminen ist eine ueberschaubare Anzahl, anders
 * als der Kandidaten-/Kanzlei-Bestand). Serverseitige Sichtbarkeitsregeln
 * (eigene vs. alle Termine) greifen unabhaengig von diesen Query-Parametern
 * (siehe Backend services/calendar_events.py::list_visible). */
export async function getCalendarEvents(query: CalendarEventQuery = {}) {
  const params = new URLSearchParams();
  if (query.startFrom) params.set("start_from", query.startFrom);
  if (query.startTo) params.set("start_to", query.startTo);
  if (query.eventType) params.set("event_type", query.eventType);
  if (query.ownerUserId) params.set("owner_user_id", query.ownerUserId);
  const suffix = params.toString() ? `?${params.toString()}` : "";
  return apiGet<CalendarEvent[]>(`/calendar-events${suffix}`, []);
}

export async function getCurrentUser() {
  return apiGet<CurrentUserInfo>("/auth/me", {
    id: "", email: "", display_name: null, is_admin: false, calendar_feed_token: null,
  });
}

export async function getAdminUsers() {
  return apiGet<AdminUser[]>("/users", []);
}

/** Fuer JEDEN eingeloggten Nutzer zugaenglich (anders als getAdminUsers/
 * GET /users, admin-only) - Grundlage der Owner-Auswahl beim Anlegen von
 * Kandidat/Kanzlei/Prozess/Aufgabe. */
export async function getAssignableUsers() {
  return apiGet<UserBrief[]>("/users/assignable", []);
}

export async function getAuditLogs() {
  return apiGet<AuditLogEntry[]>("/audit-logs", []);
}
