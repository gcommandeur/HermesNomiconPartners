// NOMICON: Meine Provision (jeder Mitarbeiter sieht sich, Teamleiter ihr Team, Admins alle).
import { apiGet } from "./client";
import type { components } from "./schema";
import type { DataResult } from "./types";

type Schemas = components["schemas"];

export type MyCommission = Schemas["MyCommissionRead"];
export type MyCommissionPerson = Schemas["MyCommissionPerson"];

export async function getMyCommission(year: number, quarter: number, userId?: string | null): Promise<DataResult<MyCommission | null>> {
  const user = userId ? `&user_id=${userId}` : "";
  return apiGet<MyCommission | null>(`/my-commission?year=${year}&quarter=${quarter}${user}`, null);
}

export async function getMyCommissionPeople(): Promise<DataResult<MyCommissionPerson[]>> {
  return apiGet<MyCommissionPerson[]>("/my-commission/people", []);
}

export type MyCommissionTimeline = Schemas["MyCommissionTimeline"];

export async function getMyCommissionTimeline(userId?: string | null): Promise<DataResult<MyCommissionTimeline | null>> {
  const user = userId ? `?user_id=${userId}` : "";
  return apiGet<MyCommissionTimeline | null>(`/my-commission/timeline${user}`, null);
}
