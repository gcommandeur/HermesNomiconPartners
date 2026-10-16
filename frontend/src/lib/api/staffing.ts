// NOMICON: Arbeitnehmerüberlassung - nur in der Nomicon-Kopie.
// Typen kommen aus dem erzeugten Schema (schema.d.ts), Abfragen/Aktionen gegen /staffing.
// Plain-Modul (kein "use client"): aus Server- und Client-Komponenten nutzbar.
import { apiDownload, apiGet, apiPatch, apiPost, apiPut } from "./client";
import type { components } from "./schema";
import type { DataResult } from "./types";
import {
  DEMO_ASSIGNMENT_DETAIL,
  DEMO_ASSIGNMENTS,
  DEMO_CONTRACTS,
  DEMO_DEADLINES,
  DEMO_LICENSES,
  DEMO_OVERVIEW,
  DEMO_SETTINGS,
  DEMO_WORKERS,
} from "@/lib/staffing-demo";

type Schemas = components["schemas"];

export type StaffingWorker = Schemas["StaffingWorkerRead"];
export type StaffingWorkerStatus = Schemas["StaffingWorkerStatus"];
export type StaffingContract = Schemas["StaffingContractRead"];
export type StaffingAssignment = Schemas["StaffingAssignmentRead"];
export type StaffingAssignmentDetail = Schemas["StaffingAssignmentDetail"];
export type StaffingAssignmentStatus = Schemas["StaffingAssignmentStatus"];
export type StaffingChecklistItem = Schemas["StaffingChecklistItemRead"];
export type StaffingChecklistKey = Schemas["StaffingChecklistKey"];
export type StaffingDeadline = Schemas["StaffingDeadlineRead"];
export type StaffingPairDeadline = Schemas["StaffingPairDeadlineRead"];
export type StaffingLicense = Schemas["StaffingLicenseRead"];
export type StaffingOverview = Schemas["StaffingOverviewRead"];
export type StaffingSettings = Schemas["StaffingSettingsRead"];
export type StaffingDisposition = Schemas["StaffingDispositionRead"];
export type StaffingTasks = Schemas["StaffingTasksRead"];
export type StaffingTask = Schemas["StaffingTaskRead"];
export type StaffingBenchWorker = Schemas["StaffingBenchWorkerRead"];
export type StaffingSettingsInput = Schemas["StaffingSettingsUpdate"];
export type Traffic = Schemas["Traffic"];
export type StaffingTimesheet = Schemas["StaffingTimesheetRead"];
export type StaffingTimesheetStatus = Schemas["StaffingTimesheetStatus"];
export type StaffingTimesheetSubmitResult = Schemas["StaffingTimesheetSubmitResult"];
export type PublicTimesheet = Schemas["PublicTimesheetRead"];
export type StaffingBillableTimesheet = Schemas["StaffingBillableTimesheetRead"];
export type StaffingInvoice = Schemas["StaffingInvoiceRead"];
export type StaffingInvoiceStatusResult = Schemas["StaffingInvoiceStatusResult"];
export type StaffingTakeoverResult = Schemas["StaffingTakeoverResult"];
export type InvoiceStatus = Schemas["InvoiceStatus"];

export const WORKER_STATUS_LABELS: Record<StaffingWorkerStatus, string> = {
  applicant: "Anwärter",
  active: "Aktiv",
  dormant: "Ruhend",
  left: "Ausgeschieden",
};

export const ASSIGNMENT_STATUS_LABELS: Record<StaffingAssignmentStatus, string> = {
  planned: "Geplant",
  active: "Aktiv",
  ended: "Beendet",
  aborted: "Abgebrochen",
};

export const CONTRACT_STATUS_LABELS: Record<Schemas["StaffingContractStatus"], string> = {
  draft: "Entwurf",
  active: "Aktiv",
  expired: "Abgelaufen",
  terminated: "Gekündigt",
};

export const CHECKLIST_LABELS: Record<StaffingChecklistKey, string> = {
  employment_contract: "Arbeitsvertrag / Nachweis (§ 11 AÜG)",
  info_leaflet: "Merkblatt für Leiharbeitnehmer",
  supply_contract: "Überlassungsvertrag (§ 12 AÜG)",
  specification: "Konkretisierung der Person",
  safety_briefing: "Sicherheitsunterweisung",
  ppe_protocol: "PSA-Übergabeprotokoll",
};

export const TIMESHEET_STATUS_LABELS: Record<StaffingTimesheetStatus, string> = {
  open: "Offen",
  submitted: "Beim Kunden",
  approved: "Freigegeben",
  rejected: "Abgelehnt",
};

export const INVOICE_STATUS_LABELS: Record<InvoiceStatus, string> = {
  draft: "Entwurf",
  issued: "Gestellt",
  due: "Fällig",
  paid: "Bezahlt",
  cancelled: "Storniert",
};

export const TRAFFIC_LABELS: Record<Traffic, string> = {
  green: "Im Rahmen",
  yellow: "Bald fällig",
  red: "Dringend",
};

/** Geld kommt als Text ("14.50"), `null` für alle ohne Admin-Recht. */
export function formatMoney(value: string | null | undefined): string {
  if (value === null || value === undefined || value === "") return "–";
  const amount = Number(value);
  if (!Number.isFinite(amount)) return "–";
  return new Intl.NumberFormat("de-DE", { style: "currency", currency: "EUR" }).format(amount);
}

/** "9 Monate, 3 Tage" für die bisherige Überlassungsdauer. */
export function formatElapsed(deadline: Pick<StaffingDeadline, "elapsed_months" | "elapsed_days">): string {
  const months = `${deadline.elapsed_months} ${deadline.elapsed_months === 1 ? "Monat" : "Monate"}`;
  const days = `${deadline.elapsed_days} ${deadline.elapsed_days === 1 ? "Tag" : "Tage"}`;
  return deadline.elapsed_months === 0 ? days : `${months}, ${days}`;
}

/** Restlaufzeit als Satz ("noch 45 Tage" / "seit 3 Tagen überschritten"). */
export function formatRemaining(daysRemaining: number | null): string {
  if (daysRemaining === null) return "–";
  if (daysRemaining < 0) return `seit ${-daysRemaining} ${-daysRemaining === 1 ? "Tag" : "Tagen"} überschritten`;
  if (daysRemaining === 0) return "letzter zulässiger Tag";
  return `noch ${daysRemaining} ${daysRemaining === 1 ? "Tag" : "Tage"}`;
}

// --- Abfragen --------------------------------------------------------------------------------

export async function getStaffingOverview(): Promise<DataResult<StaffingOverview>> {
  return apiGet<StaffingOverview>("/staffing/overview", DEMO_OVERVIEW);
}

export async function getStaffingTasks(): Promise<DataResult<StaffingTasks>> {
  return apiGet<StaffingTasks>("/staffing/tasks", { tasks: [], alerts: [], bench_after_days: 14, equal_pay_warn_days: 30 });
}

export async function getStaffingDisposition(): Promise<DataResult<StaffingDisposition>> {
  return apiGet<StaffingDisposition>("/staffing/disposition", {
    active_assignments: DEMO_OVERVIEW.active_assignments,
    planned_assignments: DEMO_OVERVIEW.planned_assignments,
    open_checklist_assignments: DEMO_OVERVIEW.open_checklist_assignments,
    bench_count: 0,
    timesheet_backlog: 0,
    license: DEMO_OVERVIEW.license,
    inbox: { open: 0, open_overdue: 0, submitted: 0, approved_unbilled: 0, rejected: 0 },
    bench: [],
  });
}

export async function getStaffingDeadlines(): Promise<DataResult<StaffingPairDeadline[]>> {
  return apiGet<StaffingPairDeadline[]>("/staffing/deadlines", DEMO_DEADLINES);
}

export async function getStaffingSettings(): Promise<DataResult<StaffingSettings>> {
  return apiGet<StaffingSettings>("/staffing/settings", DEMO_SETTINGS);
}

export async function getStaffingLicenses(): Promise<DataResult<StaffingLicense[]>> {
  return apiGet<StaffingLicense[]>("/staffing/licenses", DEMO_LICENSES);
}

export async function getStaffingWorkers(status?: StaffingWorkerStatus): Promise<DataResult<StaffingWorker[]>> {
  const query = status ? `?status=${status}` : "";
  return apiGet<StaffingWorker[]>(`/staffing/workers${query}`, DEMO_WORKERS);
}

export async function getStaffingWorker(id: string): Promise<DataResult<StaffingWorker | null>> {
  return apiGet<StaffingWorker | null>(`/staffing/workers/${id}`, DEMO_WORKERS.find((w) => w.id === id) ?? null);
}

/** `null` = der Kandidat hat (noch) kein Überlassungsprofil (Backend antwortet 404 mit dieser
 * Meldung); jeder andere Fehler wird weitergereicht, damit er nicht als „kein Profil“ erscheint. */
export async function getStaffingWorkerForCandidate(candidateId: string): Promise<StaffingWorker | null> {
  try {
    const result = await apiGet<StaffingWorker | null>(`/staffing/workers/by-candidate/${candidateId}`, null);
    return result.data;
  } catch (error) {
    if (error instanceof Error && error.message.startsWith("Kein Leiharbeitnehmer-Profil")) return null;
    throw error;
  }
}

export async function getStaffingContracts(clientCompanyId?: string): Promise<DataResult<StaffingContract[]>> {
  const query = clientCompanyId ? `?client_company_id=${clientCompanyId}` : "";
  return apiGet<StaffingContract[]>(`/staffing/contracts${query}`, DEMO_CONTRACTS);
}

export interface AssignmentFilter {
  status?: StaffingAssignmentStatus;
  workerId?: string;
  clientCompanyId?: string;
}

export function assignmentsPath(filter: AssignmentFilter = {}): string {
  const params = new URLSearchParams();
  if (filter.status) params.set("status", filter.status);
  if (filter.workerId) params.set("worker_id", filter.workerId);
  if (filter.clientCompanyId) params.set("client_company_id", filter.clientCompanyId);
  const query = params.toString();
  return `/staffing/assignments${query ? `?${query}` : ""}`;
}

export async function getStaffingAssignments(filter: AssignmentFilter = {}): Promise<DataResult<StaffingAssignment[]>> {
  return apiGet<StaffingAssignment[]>(assignmentsPath(filter), DEMO_ASSIGNMENTS);
}

export async function getStaffingAssignment(id: string): Promise<DataResult<StaffingAssignmentDetail | null>> {
  return apiGet<StaffingAssignmentDetail | null>(
    `/staffing/assignments/${id}`,
    DEMO_ASSIGNMENT_DETAIL.id === id ? DEMO_ASSIGNMENT_DETAIL : null,
  );
}

// --- Aktionen --------------------------------------------------------------------------------

export interface NewWorkerInput {
  candidate_id: string;
  status?: StaffingWorkerStatus;
  entry_date?: string | null;
  pay_grade?: string | null;
  weekly_hours?: string | null;
  work_permit_valid_until?: string | null;
  hourly_wage?: string | null; // nur Admins - das Backend lehnt es sonst mit 403 ab
  notes?: string | null;
}

export function createStaffingWorker(input: NewWorkerInput) {
  return apiPost<StaffingWorker>("/staffing/workers", input);
}

export function updateStaffingWorker(id: string, input: Partial<Omit<NewWorkerInput, "candidate_id">> & { exit_date?: string | null }) {
  return apiPatch<StaffingWorker>(`/staffing/workers/${id}`, input);
}

export interface NewAssignmentInput {
  worker_id: string;
  client_company_id: string;
  contract_id?: string | null;
  owner_user_id?: string | null;
  start_date: string;
  planned_end_date?: string | null;
  location?: string | null;
  activity?: string | null;
  billing_rate?: string | null; // nur Admins
  hourly_wage?: string | null; // nur Admins
  notes?: string | null;
}

export function createStaffingAssignment(input: NewAssignmentInput, confirmEngagement = false) {
  return apiPost<StaffingAssignment>(`/staffing/assignments${confirmEngagement ? "?confirm_engagement=true" : ""}`, input);
}

export function updateStaffingAssignment(id: string, input: Partial<Omit<NewAssignmentInput, "worker_id" | "client_company_id">>) {
  return apiPatch<StaffingAssignmentDetail>(`/staffing/assignments/${id}`, input);
}

export function changeStaffingAssignmentStatus(id: string, status: StaffingAssignmentStatus, actualEndDate?: string) {
  return apiPost<StaffingAssignmentDetail>(`/staffing/assignments/${id}/status`, {
    status,
    actual_end_date: actualEndDate ?? null,
  });
}

export function setStaffingChecklistItem(assignmentId: string, itemId: string, done: boolean) {
  return apiPatch<StaffingAssignmentDetail>(`/staffing/assignments/${assignmentId}/checklist/${itemId}`, { done });
}

export function createStaffingLicense(input: {
  authority: string;
  file_number?: string | null;
  valid_from: string;
  valid_to?: string | null;
  reminder_days?: number;
  notes?: string | null;
}) {
  return apiPost<StaffingLicense>("/staffing/licenses", input);
}

export function updateStaffingLicense(id: string, input: Partial<Omit<StaffingLicense, "id" | "created_at" | "updated_at" | "document_id">>) {
  return apiPatch<StaffingLicense>(`/staffing/licenses/${id}`, input);
}

export function saveStaffingSettings(input: StaffingSettingsInput) {
  return apiPut<StaffingSettings>("/staffing/settings", input);
}

export function createStaffingContract(input: {
  client_company_id: string;
  contract_number?: string | null;
  valid_from?: string | null;
  valid_to?: string | null;
  industry_sector?: string | null;
  status?: Schemas["StaffingContractStatus"];
}) {
  return apiPost<StaffingContract>("/staffing/contracts", input);
}

// --- Stundenzettel ---------------------------------------------------------------------------

export async function getStaffingTimesheets(assignmentId: string): Promise<DataResult<StaffingTimesheet[]>> {
  return apiGet<StaffingTimesheet[]>(`/staffing/assignments/${assignmentId}/timesheets`, []);
}

export function createStaffingTimesheet(assignmentId: string, periodStart: string, periodEnd: string) {
  return apiPost<StaffingTimesheet>(`/staffing/assignments/${assignmentId}/timesheets`, {
    period_start: periodStart,
    period_end: periodEnd,
  });
}

export interface TimesheetEntryInput {
  work_date: string;
  hours: string;
  break_minutes: number;
}

export function saveStaffingTimesheetEntries(timesheetId: string, entries: TimesheetEntryInput[]) {
  return apiPut<StaffingTimesheet>(`/staffing/timesheets/${timesheetId}/entries`, { entries });
}

/** Reicht ein und erzeugt den Freigabelink für den Kunden (erneuter Aufruf = neuer Link). */
export function submitStaffingTimesheet(timesheetId: string) {
  return apiPost<StaffingTimesheetSubmitResult>(`/staffing/timesheets/${timesheetId}/submit`, {});
}

// --- Abrechnung, Export, Übernahme -----------------------------------------------------------

export async function getBillableTimesheets(): Promise<DataResult<StaffingBillableTimesheet[]>> {
  return apiGet<StaffingBillableTimesheet[]>("/staffing/billable-timesheets", []);
}

export async function getStaffingInvoices(): Promise<DataResult<StaffingInvoice[]>> {
  return apiGet<StaffingInvoice[]>("/staffing/invoices", []);
}

export async function getStaffingInvoice(id: string): Promise<DataResult<StaffingInvoice | null>> {
  return apiGet<StaffingInvoice | null>(`/staffing/invoices/${id}`, null);
}

export function createStaffingInvoice(timesheetIds: string[], notes?: string) {
  return apiPost<StaffingInvoice>("/staffing/invoices", { timesheet_ids: timesheetIds, notes: notes || null });
}

export function changeStaffingInvoiceStatus(
  id: string,
  status: InvoiceStatus,
  dates?: { invoice_date?: string; payment_due_date?: string },
) {
  return apiPost<StaffingInvoiceStatusResult>(`/staffing/invoices/${id}/status`, { invoice_status: status, ...dates });
}

/** Lädt die CSV für die Lohnabrechnung (nur Admins): Stunden je Leiharbeitnehmer und Kunde. */
export function downloadHoursCsv(periodStart: string, periodEnd: string) {
  return apiDownload(`/staffing/export/hours.csv?period_start=${periodStart}&period_end=${periodEnd}`, `stunden_${periodStart}_${periodEnd}.csv`);
}

export type TakeoverFeeTier = Schemas["TakeoverFeeTierInput"];
export type TakeoverFeeTiers = Schemas["TakeoverFeeTiersRead"];
export type TakeoverPreview = Schemas["StaffingTakeoverPreview"];
export type StaffingOfferResult = Schemas["StaffingOfferResult"];

export function getTakeoverPreview(id: string, takeoverDate: string): Promise<DataResult<TakeoverPreview | null>> {
  return apiGet<TakeoverPreview | null>(`/staffing/assignments/${id}/takeover-preview?takeover_date=${takeoverDate}`, null);
}

export function getTakeoverFeeTiers(): Promise<DataResult<TakeoverFeeTiers>> {
  return apiGet<TakeoverFeeTiers>("/staffing/takeover-fee-tiers", {
    tiers: [
      { up_to_months: 3, percent_of_fee: "100" },
      { up_to_months: 6, percent_of_fee: "75" },
      { up_to_months: 9, percent_of_fee: "50" },
      { up_to_months: 12, percent_of_fee: "25" },
      { up_to_months: null, percent_of_fee: "0" },
    ],
    notice: "Platzhalter-Staffel, nicht abgestimmt: mit der vertraglich vereinbarten Staffel abgleichen. Kein Rechtsrat.",
  });
}

export function saveTakeoverFeeTiers(tiers: TakeoverFeeTier[]) {
  return apiPut<TakeoverFeeTiers>("/staffing/takeover-fee-tiers", { tiers });
}

/** "Als Einsatz anbieten" (Direct -> Überlassung). 409 mit Hinweistext, wenn der Kandidat schon im Austausch ist. */
export function offerCandidateAsAssignment(
  input: { candidate_id: string; client_company_id?: string | null; start_date?: string | null; planned_end_date?: string | null },
  confirmEngagement = false,
) {
  return apiPost<StaffingOfferResult>(`/staffing/offer-from-candidate${confirmEngagement ? "?confirm_engagement=true" : ""}`, input);
}

export function takeOverStaffingAssignment(
  id: string,
  input: { takeover_date?: string | null; annual_salary?: string | null; fee_percentage?: string | null },
) {
  return apiPost<StaffingTakeoverResult>(`/staffing/assignments/${id}/takeover`, input);
}
