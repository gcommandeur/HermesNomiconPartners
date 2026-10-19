// NOMICON: Ansicht "Gesamt" (Geschäftsführung, nur Admins). Plain-Modul.
import { apiGet } from "./client";
import type { components } from "./schema";
import type { DataResult } from "./types";

type Schemas = components["schemas"];

export type ManagementOverview = Schemas["ManagementOverviewRead"];
export type ManagementPeriod = ManagementOverview["period"];
export type ManagementAlert = Schemas["ManagementAlertRead"];

const EMPTY = (period: ManagementPeriod): ManagementOverview => ({
  period,
  date_from: "",
  date_to: "",
  employer_factor: "1.23",
  gross_profit: { direct: "0", staffing: "0", total: "0", staffing_hours: "0", staffing_missing_rates: 0 },
  forecast: {
    direct_weighted: "0",
    direct_without_probability: 0,
    direct_without_fee: 0,
    staffing_margin: "0",
    staffing_counted: 0,
    staffing_excluded: 0,
    total: "0",
  },
  both_business_clients: [],
  takeover: { pairs: 0, taken_over: 0, rate: null },
  alerts: [],
  assumptions: [],
});

export function getManagementOverview(period: ManagementPeriod): Promise<DataResult<ManagementOverview>> {
  return apiGet<ManagementOverview>(`/management/overview?period=${period}`, EMPTY(period));
}
