"use client";

// NOMICON: Arbeitnehmerüberlassung - nur in der Nomicon-Kopie. SWR-Hooks für /staffing.
import useSWR, { mutate } from "swr";
import {
  assignmentsPath,
  getBillableTimesheets,
  getStaffingAssignment,
  getStaffingCandidateSummaries,
  getWorkerTimesheetSummary,
  getStaffingAssignments,
  getStaffingContracts,
  getStaffingDeadlines,
  getTakeoverFeeTiers,
  getTakeoverPreview,
  getStaffingDisposition,
  getStaffingInvoice,
  getStaffingInvoices,
  getStaffingLicenses,
  getStaffingOverview,
  getStaffingPriorPeriods,
  getStaffingSettings,
  getStaffingTasks,
  getStaffingTimesheets,
  getStaffingWorker,
  getStaffingWorkerForCandidate,
  getStaffingWorkers,
  type AssignmentFilter,
  type StaffingWorkerStatus,
} from "./staffing";

// Überlassungsdaten ändern sich durch Aktionen anderer Disponenten und den Tagesjob: kurzer
// Cache, beim Zurückkehren in den Tab neu laden.
const config = { revalidateOnFocus: true, dedupingInterval: 5_000 } as const;

export function useStaffingOverview() {
  return useSWR("/staffing/overview", getStaffingOverview, config);
}

export function useStaffingDisposition() {
  return useSWR("/staffing/disposition", getStaffingDisposition, config);
}

/** Sammelabfrage für die Spalte "Überlassung" der Kandidatenliste; nur mit Ansicht Überlassung. */
export function useStaffingCandidateSummaries(candidateIds: string[], enabled: boolean) {
  const key = enabled && candidateIds.length > 0 ? `/staffing/candidate-summary?${candidateIds.join(",")}` : null;
  return useSWR(key, () => getStaffingCandidateSummaries(candidateIds), { revalidateOnFocus: false, dedupingInterval: 10_000, keepPreviousData: true });
}

export function useWorkerTimesheetSummary(workerId: string | null) {
  return useSWR(workerId ? `/staffing/workers/${workerId}/timesheet-summary` : null, () => getWorkerTimesheetSummary(workerId as string), config);
}

export function useStaffingTasks(enabled = true) {
  return useSWR(enabled ? "/staffing/tasks" : null, getStaffingTasks, config);
}

export function useStaffingDeadlines() {
  return useSWR("/staffing/deadlines", getStaffingDeadlines, config);
}

export function useStaffingSettings() {
  return useSWR("/staffing/settings", getStaffingSettings, config);
}

export function useStaffingLicenses() {
  return useSWR("/staffing/licenses", getStaffingLicenses, config);
}

export function useStaffingWorkers(status?: StaffingWorkerStatus) {
  return useSWR(`/staffing/workers${status ? `?status=${status}` : ""}`, () => getStaffingWorkers(status), config);
}

export function useStaffingWorker(id: string) {
  return useSWR(`/staffing/workers/${id}`, () => getStaffingWorker(id), config);
}

export function useStaffingWorkerForCandidate(candidateId: string) {
  return useSWR(`/staffing/workers/by-candidate/${candidateId}`, () => getStaffingWorkerForCandidate(candidateId), config);
}

export function useStaffingPriorPeriods(workerId: string | null) {
  return useSWR(workerId ? `/staffing/workers/${workerId}/prior-periods` : null, () => getStaffingPriorPeriods(workerId as string), config);
}

export function useStaffingContracts(clientCompanyId?: string) {
  return useSWR(
    `/staffing/contracts${clientCompanyId ? `?client_company_id=${clientCompanyId}` : ""}`,
    () => getStaffingContracts(clientCompanyId),
    config,
  );
}

export function useStaffingAssignments(filter: AssignmentFilter = {}) {
  return useSWR(assignmentsPath(filter), () => getStaffingAssignments(filter), config);
}

export function useStaffingAssignment(id: string) {
  return useSWR(`/staffing/assignments/${id}`, () => getStaffingAssignment(id), config);
}

export function useStaffingTimesheets(assignmentId: string, enabled = true) {
  return useSWR(enabled ? `/staffing/assignments/${assignmentId}/timesheets` : null, () => getStaffingTimesheets(assignmentId), config);
}

export function useBillableTimesheets() {
  return useSWR("/staffing/billable-timesheets", getBillableTimesheets, config);
}

export function useStaffingInvoices() {
  return useSWR("/staffing/invoices", getStaffingInvoices, config);
}

export function useStaffingInvoice(id: string) {
  return useSWR(`/staffing/invoices/${id}`, () => getStaffingInvoice(id), config);
}

/** Nach jeder Änderung aufrufen: lädt alle Überlassungs-Listen und -Details neu. */
export function invalidateStaffing() {
  return mutate((key) => typeof key === "string" && key.startsWith("/staffing"));
}

export function useTakeoverFeeTiers() {
  return useSWR("/staffing/takeover-fee-tiers", getTakeoverFeeTiers, config);
}

export function useTakeoverPreview(assignmentId: string, takeoverDate: string) {
  return useSWR(takeoverDate ? `/staffing/assignments/${assignmentId}/takeover-preview?${takeoverDate}` : null, () => getTakeoverPreview(assignmentId, takeoverDate), config);
}
