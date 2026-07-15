import { demoCandidates, demoClients, demoCockpit, demoEmailTemplates, demoSubmissions } from "@/lib/demo-data";
import { demoContacts, demoGeoResults, demoVacancies } from "@/lib/ia-data";
import { apiGet } from "./client";
import type { Activity, Candidate, CandidateSubmission, ClientCompany, ClientDuplicateCandidate, ClientMatch, Cockpit, Contact, DocumentMeta, EmailTemplate, GeoMappingResult, MailingGroup, Paginated, Placement, Task, Vacancy } from "./types";

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

export async function getMailingGroups() {
  return apiGet<MailingGroup[]>("/mailing-groups", []);
}

export async function getActiveWarranties() {
  return apiGet<Placement[]>("/placements/active-warranties", []);
}

export async function getContacts() {
  return fetchAllPages<Contact>("/contacts", demoContacts);
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
