"use client";

// NOMICON: Provisionsmodell - SWR-Hooks (nur Admins rufen diese auf).
import useSWR, { mutate } from "swr";
import { getCommissionConfig, getCommissionReport, getCommissionUsers } from "./commission";

const config = { revalidateOnFocus: false, dedupingInterval: 5_000 } as const;

export function useCommissionReport(year: number, quarter: number, enabled = true) {
  return useSWR(enabled ? `/commission/report?year=${year}&quarter=${quarter}` : null, () => getCommissionReport(year, quarter), config);
}

export function useCommissionConfig(enabled = true) {
  return useSWR(enabled ? "/commission/config" : null, getCommissionConfig, config);
}

export function useCommissionUsers(enabled = true) {
  return useSWR(enabled ? "/commission/users" : null, getCommissionUsers, config);
}

export function invalidateCommission() {
  return mutate((key) => typeof key === "string" && key.startsWith("/commission"));
}
