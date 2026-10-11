// NOMICON: Arbeitnehmerüberlassung - Beispieldaten für den Demo-Modus (CI-Build, Vorschau ohne
// Backend). Keine echten Personen; Lohn und Verrechnungssatz sind wie für Nicht-Admins leer.
import type {
  StaffingAssignment,
  StaffingAssignmentDetail,
  StaffingContract,
  StaffingLicense,
  StaffingOverview,
  StaffingPairDeadline,
  StaffingSettings,
  StaffingWorker,
} from "@/lib/api/staffing";

const STAMP = "2026-01-05T08:00:00Z";
const ID = (n: number) => `00000000-0000-4000-8000-${String(n).padStart(12, "0")}`;

export const DEMO_WORKERS: StaffingWorker[] = [
  {
    id: ID(1), created_at: STAMP, updated_at: STAMP, candidate_id: ID(101),
    candidate_name: "Mira Beispiel", candidate_number: "4001", status: "active",
    entry_date: "2025-03-01", exit_date: null, hourly_wage: null, pay_grade: "EG 2",
    weekly_hours: "35", work_permit_valid_until: null, notes: null,
  },
  {
    id: ID(2), created_at: STAMP, updated_at: STAMP, candidate_id: ID(102),
    candidate_name: "Jonas Muster", candidate_number: "4002", status: "applicant",
    entry_date: null, exit_date: null, hourly_wage: null, pay_grade: null,
    weekly_hours: null, work_permit_valid_until: null, notes: null,
  },
];

export const DEMO_CONTRACTS: StaffingContract[] = [
  {
    id: ID(11), created_at: STAMP, updated_at: STAMP, client_company_id: ID(201),
    client_name: "Beispiel Logistik GmbH", contract_number: "R-2025-01", valid_from: "2025-01-01",
    valid_to: null, industry_sector: "Logistik", document_id: null, status: "active", notes: null,
  },
];

export const DEMO_ASSIGNMENTS: StaffingAssignment[] = [
  {
    id: ID(21), created_at: STAMP, updated_at: STAMP, worker_id: ID(1), worker_name: "Mira Beispiel",
    client_company_id: ID(201), client_name: "Beispiel Logistik GmbH", contract_id: ID(11),
    owner_user_id: null, start_date: "2025-03-01", planned_end_date: null, actual_end_date: null,
    location: "Lager Nord", activity: "Kommissionierung", billing_rate: null, hourly_wage: null,
    status: "active", notes: null, checklist_done: 6, checklist_total: 6,
  },
  {
    id: ID(22), created_at: STAMP, updated_at: STAMP, worker_id: ID(2), worker_name: "Jonas Muster",
    client_company_id: ID(201), client_name: "Beispiel Logistik GmbH", contract_id: ID(11),
    owner_user_id: null, start_date: "2026-02-01", planned_end_date: "2026-07-31", actual_end_date: null,
    location: "Lager Süd", activity: "Staplerfahrer", billing_rate: null, hourly_wage: null,
    status: "planned", notes: null, checklist_done: 2, checklist_total: 6,
  },
];

const KEYS = [
  "employment_contract", "info_leaflet", "supply_contract", "specification", "safety_briefing", "ppe_protocol",
] as const;

export const DEMO_ASSIGNMENT_DETAIL: StaffingAssignmentDetail = {
  ...DEMO_ASSIGNMENTS[1],
  checklist: KEYS.map((key, index) => ({
    id: ID(300 + index), item_key: key, done: index < 2, done_on: index < 2 ? "2026-01-20" : null, document_id: null,
  })),
  deadline: {
    has_chain: true, chain_start: "2026-02-01", elapsed_months: 0, elapsed_days: 0, counted_days: 0,
    equal_pay_from: "2026-11-01", equal_pay_reached: false, max_end_date: "2027-07-31",
    days_remaining: 500, exceeded: false, traffic: "green",
  },
  activation_problems: [
    "Keine gültige AÜG-Erlaubnis für den Zeitraum 01.02.2026 bis 31.07.2026 hinterlegt.",
    "Pflicht-Checkliste unvollständig (offen: Überlassungsvertrag, Konkretisierung, Sicherheitsunterweisung, PSA-Übergabeprotokoll).",
  ],
};

export const DEMO_DEADLINES: StaffingPairDeadline[] = [
  {
    worker_id: ID(1), worker_name: "Mira Beispiel", client_company_id: ID(201),
    client_name: "Beispiel Logistik GmbH", owner_user_id: null, has_chain: true,
    chain_start: "2025-03-01", elapsed_months: 10, elapsed_days: 5, counted_days: 310,
    equal_pay_from: "2025-12-01", equal_pay_reached: true, max_end_date: "2026-08-31",
    days_remaining: 55, exceeded: false, traffic: "yellow",
  },
];

export const DEMO_LICENSES: StaffingLicense[] = [
  {
    id: ID(31), created_at: STAMP, updated_at: STAMP, authority: "Bundesagentur für Arbeit",
    file_number: "Beispiel-Az. 123", valid_from: "2025-01-01", valid_to: "2026-12-31",
    document_id: null, reminder_days: 90, notes: null,
  },
];

export const DEMO_OVERVIEW: StaffingOverview = {
  active_assignments: 1,
  planned_assignments: 1,
  open_checklist_assignments: 1,
  license: { valid: true, valid_to: "2026-12-31", days_remaining: 300, traffic: "green" },
  deadlines: DEMO_DEADLINES,
};

export const DEMO_SETTINGS: StaffingSettings = {
  max_months: 18,
  equal_pay_months: 9,
  reset_gap_months: 3,
  yellow_days: 60,
  red_days: 30,
  notice:
    "Hinweis: Diese Werte sind einstellbare Annahmen und kein Rechtsrat. Bitte mit Fachanwalt oder Verband bestätigen; Tarifverträge können abweichen.",
};
