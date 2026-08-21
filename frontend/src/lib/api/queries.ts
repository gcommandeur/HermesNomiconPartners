import { demoCandidates, demoClients, demoCockpit, demoEmailTemplates, demoSubmissions } from "@/lib/demo-data";
import { demoContacts, demoGeoResults, demoVacancies } from "@/lib/ia-data";
import { apiDelete, apiGet, apiPatch, apiPost } from "./client";
import type { Activity, AdminUser, AuditLogEntry, Candidate, CandidateMatch, CandidateQuickLogCreate, CandidateQuickLogResult, CandidateStageSummary, CandidateSubmission, CalendarEvent, CalendarEventType, ClientCompany, ClientDuplicateCandidate, ClientMatch, Cockpit, Contact, CurrentUserInfo, DocumentMeta, EmailTemplate, Feedback, FeedbackCreate, FeedbackCreateResult, FeedbackUpdate, GeoMappingResult, Interview, InterviewCreate, InterviewUpdate, MailAccount, MailMatchStatus, MailMessageListItem, MailingGroup, Note, Offer, OfferCreate, OfferUpdate, PageQuery, Paginated, Placement, PlacementCreate, PlacementUpdate, SourcingLead, SourcingRunStatus, Task, TaskResolveOutcome, UserBrief, Vacancy } from "./types";

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
  for (const rolle of query.rollen ?? []) params.append("rollen", rolle);
  if (query.plzOrt?.trim() && query.radiusKm) {
    params.set("plz_ort", query.plzOrt.trim());
    params.set("radius_km", String(query.radiusKm));
  }
  if (query.ownerUserId) params.set("owner_user_id", query.ownerUserId);
  if (query.sortBy) params.set("sort_by", query.sortBy);
  if (query.sortDir) params.set("sort_dir", query.sortDir);
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

/** Interview-Runden EINES Prozesses - fuer das Interview-Panel der
 * Stufen-Bearbeitung auf der Kandidat-Detailseite (dort ist nur ein
 * Prozess relevant, anders als getAllInterviews() fuer die Kanban-Seite). */
export async function getInterviews(submissionId: string) {
  return apiGet<Interview[]>(`/submissions/${submissionId}/interviews`, []);
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

/** Feedback-Eintraege eines Prozesses - dienen auch als generisches
 * "Datum + Notiz"-Feld fuer die Stufen qualification_call/cv_in/cv_out
 * (siehe stage-edit-modal.tsx). */
export async function getFeedback(submissionId: string) {
  return apiGet<Feedback[]>(`/submissions/${submissionId}/feedback`, []);
}

export async function createFeedback(submissionId: string, payload: FeedbackCreate) {
  return apiPost<FeedbackCreateResult>(`/submissions/${submissionId}/feedback`, payload);
}

export async function updateFeedback(
  submissionId: string,
  feedbackId: string,
  payload: FeedbackUpdate,
) {
  return apiPatch<Feedback>(`/submissions/${submissionId}/feedback/${feedbackId}`, payload);
}

export async function deleteFeedback(submissionId: string, feedbackId: string) {
  return apiDelete(`/submissions/${submissionId}/feedback/${feedbackId}`);
}

export async function getOffers(submissionId: string) {
  return apiGet<Offer[]>(`/submissions/${submissionId}/offers`, []);
}

export async function createOffer(submissionId: string, payload: OfferCreate) {
  return apiPost<Offer>(`/submissions/${submissionId}/offers`, payload);
}

export async function updateOffer(submissionId: string, offerId: string, payload: OfferUpdate) {
  return apiPatch<Offer>(`/submissions/${submissionId}/offers/${offerId}`, payload);
}

export async function deleteOffer(submissionId: string, offerId: string) {
  return apiDelete(`/submissions/${submissionId}/offers/${offerId}`);
}

/** Placement ist singulaer (ein Objekt pro Prozess) - kein :id-Segment im
 * Pfad, analog zum Backend (siehe api/v1/submissions.py). Ein 404 vom GET
 * bedeutet schlicht "noch kein Placement angelegt", kein echter Fehler -
 * deshalb wird er hier zu `null` statt einer geworfenen Exception, der
 * Aufrufer (stage-edit-modal.tsx) zeigt in diesem Fall das Anlegen-Formular. */
export async function getPlacement(submissionId: string): Promise<Placement | null> {
  try {
    const result = await apiGet<Placement | null>(`/submissions/${submissionId}/placement`, null);
    return result.data;
  } catch (error) {
    if (error instanceof Error && error.message.includes("404")) return null;
    throw error;
  }
}

export async function createPlacement(submissionId: string, payload: PlacementCreate) {
  return apiPost<Placement>(`/submissions/${submissionId}/placement`, payload);
}

export async function updatePlacement(submissionId: string, payload: PlacementUpdate) {
  return apiPatch<Placement>(`/submissions/${submissionId}/placement`, payload);
}

export async function deletePlacement(submissionId: string) {
  return apiDelete(`/submissions/${submissionId}/placement`);
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

/** "Spaeter erinnern" - blendet den Task fuer `days` Tage aus GET
 * /tasks?status=open (und der Dashboard-To-Do-Sektion) aus, ohne ihn zu
 * schliessen (siehe Backend services/tasks.py::snooze). */
export async function snoozeTask(taskId: string, days: number) {
  return apiPost<Task>(`/tasks/${taskId}/snooze`, { days });
}

/** Reaktion auf ein (i.d.R. automatisch erzeugtes) Task - "no_response"
 * schliesst es nur, "meeting_scheduled" legt zusaetzlich einen
 * Quali-Call-Kalendertermin an (siehe Backend services/tasks.py::resolve). */
export async function resolveTask(
  taskId: string,
  payload: { outcome: TaskResolveOutcome; scheduled_at?: string; notes?: string },
) {
  return apiPost<Task>(`/tasks/${taskId}/resolve`, payload);
}

export async function getDocumentsForOwner(ownerType: string, ownerId: string) {
  return apiGet<DocumentMeta[]>(`/documents?owner_type=${ownerType}&owner_id=${ownerId}`, []);
}

/** Nur die allgemeinen (nicht prozessgebundenen) Notizen eines Kandidaten -
 * siehe repositories/notes.py::NoteRepository.filtered() (ohne submission_id
 * filtert das serverseitig automatisch auf candidate_submission_id IS NULL). */
export async function getNotesForCandidate(candidateId: string) {
  return apiGet<Note[]>(`/notes?candidate_id=${candidateId}`, []);
}

export async function createNote(payload: { candidate_id: string; body: string }) {
  return apiPost<Note>("/notes", payload);
}

export async function getCandidateMatches(candidateId: string) {
  return apiGet<ClientMatch[]>(`/candidates/${candidateId}/matches`, []);
}

export async function getVacancyMatches(vacancyId: string) {
  return apiGet<CandidateMatch[]>(`/vacancies/${vacancyId}/matches`, []);
}

export async function geocodePlace(query: string) {
  return apiGet<{ latitude: number | null; longitude: number | null }>(
    `/geo-mapping/geocode?query=${encodeURIComponent(query)}`,
    { latitude: null, longitude: null },
  );
}

const emptyStageSummary: CandidateStageSummary = {
  qualification_call: 0,
  cv_in: 0,
  cv_out: 0,
  interview: 0,
  offer: 0,
  placement: 0,
};

/** Anzahl erreichter Ereignisse je Stufe ueber ALLE Submissions eines
 * Kandidaten - Basis der Prozess-Timeline (candidate-process-log.tsx). */
export async function getStageSummary(candidateId: string) {
  return apiGet<CandidateStageSummary>(`/candidates/${candidateId}/stage-summary`, emptyStageSummary);
}

/** Pitch-/Quali-Call-Notiz anlegen - startet dabei bei Bedarf automatisch
 * einen Prozess (siehe candidate-process-log.tsx). */
export async function quickLogCandidateStage(candidateId: string, payload: CandidateQuickLogCreate) {
  return apiPost<CandidateQuickLogResult>(`/candidates/${candidateId}/quick-log`, payload);
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

/** Admin-only: verbundene Postfaecher (siehe /einstellungen/postfaecher). */
export async function getMailAccounts() {
  return apiGet<MailAccount[]>("/mail-accounts", []);
}

/** Admin-only: eingelesene Mails eines Postfachs (siehe
 * /einstellungen/postfaecher) - kein useSWR-Hook, da paginiert per
 * "mehr laden" statt einmalig geladen. */
export async function getMailMessages(
  accountId: string,
  options: { matchStatus?: MailMatchStatus[]; offset?: number; limit?: number } = {},
) {
  const params = new URLSearchParams();
  for (const status of options.matchStatus ?? []) params.append("match_status", status);
  params.set("offset", String(options.offset ?? 0));
  params.set("limit", String(options.limit ?? 50));
  return apiGet<MailMessageListItem[]>(
    `/mail-accounts/${accountId}/messages?${params.toString()}`,
    [],
  );
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

/** Offene Sourcing-Leads (pending + possible_duplicate) fuer die Review-Seite
 * /sourcing - beide Status in einem Rutsch, da die Seite sie gemeinsam (aber
 * getrennt hervorgehoben) anzeigt. Bewusst limit=500 statt fetchAllPages: ein
 * einzelner Sourcing-Lauf liefert Dutzende, nicht Tausende offener Leads. */
/** Stand des Hintergrund-Sourcing-Laufs fuer die Lauf-Anzeige/Stop-Button -
 * null (per Fallback), solange noch nie ein Lauf gestartet wurde. */
export async function getSourcingRunStatus() {
  return apiGet<SourcingRunStatus | null>("/sourcing/status", null);
}

export async function getOpenSourcingLeads() {
  const [pending, duplicates] = await Promise.all([
    apiGet<Paginated<SourcingLead>>("/sourcing/leads?status=pending&limit=500", { items: [], total_count: 0, limit: 500, offset: 0 }),
    apiGet<Paginated<SourcingLead>>("/sourcing/leads?status=possible_duplicate&limit=500", { items: [], total_count: 0, limit: 500, offset: 0 }),
  ]);
  return {
    data: [...pending.data.items, ...duplicates.data.items],
    source: pending.source,
    error: pending.error,
  };
}
