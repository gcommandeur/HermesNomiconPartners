// NOMICON: Provisionsmodell (nur Admins). Typen aus dem erzeugten Schema.
import { apiGet, apiPut } from "./client";
import type { components } from "./schema";
import type { DataResult } from "./types";

type Schemas = components["schemas"];

export type CommissionReport = Schemas["CommissionReportRead"];
export type CommissionRow = Schemas["CommissionRowRead"];
export type CommissionConfig = Schemas["CommissionConfigRead"];
export type CommissionConfigInput = Schemas["CommissionConfigUpdate"];
export type CommissionRank = Schemas["CommissionRankConfig-Output"];
export type CommissionUserRank = Schemas["CommissionUserRankRead"];

const EMPTY_REPORT: CommissionReport = {
  year: 2026,
  quarter: 1,
  period_start: "2026-01-01",
  period_end: "2026-03-31",
  target_margin: "50",
  rows: [],
  unassigned: [],
  totals: { revenue: "0", commission: "0", fixed_pay: "0", employer_cost: "0", margin: "0", margin_percent: null, traffic: "green" },
  revenue_basis: { placement_fees: "paid", include_staffing: true, staffing: "issued" },
  notice: "",
};

export async function getCommissionReport(year?: number, quarter?: number): Promise<DataResult<CommissionReport>> {
  const query = year && quarter ? `?year=${year}&quarter=${quarter}` : "";
  return apiGet<CommissionReport>(`/commission/report${query}`, EMPTY_REPORT);
}

export async function getCommissionConfig(): Promise<DataResult<CommissionConfig>> {
  return apiGet<CommissionConfig>("/commission/config", {
    general: { commission_free_base: "10000", employer_factor: "1.23", extra_cost_monthly: "500", fee_rate_on_target_salary: "28", min_fee: "12000", target_margin: "50" },
    ranks: [],
    revenue_basis: EMPTY_REPORT.revenue_basis,
    notice: "",
  });
}

export async function getCommissionUsers(): Promise<DataResult<CommissionUserRank[]>> {
  return apiGet<CommissionUserRank[]>("/commission/users", []);
}

export function saveCommissionConfig(config: CommissionConfigInput) {
  return apiPut<CommissionConfig>("/commission/config", config);
}

export function setCommissionUserRank(userId: string, rankKey: string | null) {
  return apiPut<CommissionUserRank>(`/commission/users/${userId}/rank`, { rank_key: rankKey });
}

/** Aktuelles Quartal als { year, quarter }. */
export function currentQuarter(now: Date = new Date()): { year: number; quarter: number } {
  return { year: now.getFullYear(), quarter: Math.floor(now.getMonth() / 3) + 1 };
}

export function shiftQuarter(year: number, quarter: number, delta: number): { year: number; quarter: number } {
  const index = year * 4 + (quarter - 1) + delta;
  return { year: Math.floor(index / 4), quarter: (index % 4) + 1 };
}

/** Euro-Betrag aus einem Dezimal-Text; fehlende Werte als „–“. */
export function eur(value: string | null | undefined): string {
  if (value === null || value === undefined || value === "") return "–";
  const amount = Number(value);
  if (!Number.isFinite(amount)) return "–";
  return new Intl.NumberFormat("de-DE", { style: "currency", currency: "EUR" }).format(amount);
}
