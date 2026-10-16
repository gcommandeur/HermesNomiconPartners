"use client";

// NOMICON: Meine Provision - SWR-Hooks.
import useSWR from "swr";
import { getMyCommission, getMyCommissionPeople } from "./my-commission";

const config = { revalidateOnFocus: false, dedupingInterval: 5_000 } as const;

export function useMyCommission(year: number, quarter: number, userId?: string | null) {
  return useSWR(`/my-commission?year=${year}&quarter=${quarter}&user=${userId ?? "me"}`, () => getMyCommission(year, quarter, userId), config);
}

export function useMyCommissionPeople() {
  return useSWR("/my-commission/people", getMyCommissionPeople, config);
}
