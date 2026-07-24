export type CandidateStatus = "active" | "passive" | "placed" | "blocked" | "archived";
export type HonorarStufe = "standard" | "nachlass_1" | "nachlass_2" | "individuell";
/** Grammatikalisches Geschlecht für die Profilgenerierung (Kandidatin/Kandidat). */
export type Anrede = "frau" | "herr" | "divers";

export interface BeruflicheStation {
  kanzleityp: string;
  kanzleigroesse: string;
  dauer_jahre: number;
}
export type SubmissionStatus =
  | "qualification_call" | "cv_in" | "cv_out" | "interview" | "offer" | "placement" | "cancelled";
export type SubmissionCancellationReason =
  | "candidate_rejected" | "client_rejected" | "candidate_ghosting";
export type ClosingStatus = "hot" | "warm" | "risk" | "stop";

export interface Entity {
  id: string;
  created_at: string;
  updated_at: string;
}

export type CalendarEventType = "interview" | "quali_call" | "other";

export interface CalendarEvent extends Entity {
  title: string;
  event_type: CalendarEventType;
  start_at: string;
  end_at: string | null;
  location: string | null;
  notes: string | null;
  owner_user_id: string;
  created_by_user_id: string;
  candidate_id: string | null;
  client_company_id: string | null;
  candidate_submission_id: string | null;
  /** Nur gesetzt, wenn dieser Termin automatisch aus einem Interview
   * entstanden ist (siehe Backend services/recruiting.py::create_interview) -
   * rein informativ, nie ueber das Formular setzbar. */
  source_interview_id?: string | null;
  reminder_minutes_before: number;
}

/** Antwort von /auth/login und /auth/me - NUR fuer den eingeloggten Nutzer
 * selbst befuellt, `calendar_feed_token` ist ein Geheimnis (siehe Backend
 * schemas/auth.py::UserRead). Fuer die Admin-Nutzerliste andere Nutzer siehe
 * AdminUser weiter unten, die dieses Feld bewusst nicht enthaelt. */
export interface CurrentUserInfo {
  id: string;
  email: string;
  display_name: string | null;
  is_admin: boolean;
  calendar_feed_token?: string | null;
}

export interface AdminUser {
  id: string;
  email: string;
  display_name: string | null;
  is_admin: boolean;
  is_active: boolean;
}

/** Minimale Nutzerliste (GET /users/assignable) fuer Owner-Dropdowns beim
 * Anlegen von Kandidat/Kanzlei/Prozess/Aufgabe - anders als AdminUser fuer
 * JEDEN eingeloggten Nutzer zugaenglich, siehe Backend schemas/user.py::
 * UserBriefRead. */
export interface UserBrief {
  id: string;
  email: string;
  display_name: string | null;
}

export interface Candidate extends Entity {
  candidate_number?: string | null;
  first_name: string;
  last_name: string;
  email: string | null;
  phone: string | null;
  job_title: string | null;
  qualification?: string | null;
  postal_code: string | null;
  city: string | null;
  linkedin_url: string | null;
  salary_expectation: string | null;
  notice_period: string | null;
  available_from?: string | null;
  last_contact_at?: string | null;
  next_step?: string | null;
  cv_available?: boolean;
  short_profile?: string | null;
  consent_received?: boolean;
  summary: string | null;
  status: CandidateStatus;
  last_contact?: string;
  anrede?: Anrede | null;
  referred_by?: string | null;
  has_ghosting_history?: boolean;

  // --- Quali-Call-Erweiterung ---
  fachliche_schwerpunkte?: string[];
  ausbildung_titel?: string | null;
  berufliche_stationen?: BeruflicheStation[];
  aktuelles_umfeld_kanzleityp?: string | null;
  aktuelles_umfeld_kanzleigroesse?: string | null;
  /** INTERN — niemals in anonyme Profile / ausgehende Dokumente übernehmen. */
  wechselgrund?: string | null;
  remote_teilzeit_wuensche?: string | null;
  passender_kanzleityp?: string | null;
  /** INTERN — niemals in anonyme Profile / ausgehende Dokumente übernehmen. */
  no_gos?: string[];
  freitext_notizen?: string | null;
  /** Zustaendiger Mitarbeiter (Komfort-Filter "Meine Kandidaten", KEINE
   * Sichtbarkeitsgrenze - siehe Backend models/candidate.py::owner_user_id). */
  owner_user_id?: string | null;
}

export interface ClientCompany extends Entity {
  name: string;
  kanzleigruppe?: string | null;
  status: "active" | "acquisition" | "prospect" | "blocked" | "archived";
  website: string | null;
  email: string | null;
  phone: string | null;
  street: string | null;
  postal_code: string | null;
  city: string | null;
  region?: string | null;
  company_size?: string | null;
  focus?: string | null;
  linkedin_url?: string | null;
  last_contact_at?: string | null;
  next_follow_up_at?: string | null;
  terms_status?: string;
  fee_percentage?: number;
  honorar_stufe?: HonorarStufe;
  nachlass_begruendung?: string | null;
  agb_version?: string | null;
  refund_terms?: string;
  guarantee_period_months?: number;
  payment_terms_days?: number;
  special_terms?: string | null;
  commercial_notes?: string | null;
  notes: string | null;
  size?: string;
  contact_name?: string;
  active_mandates?: number;
  last_contact?: string;
  /** Zustaendiger Mitarbeiter (Komfort-Filter "Meine Kanzleien", KEINE
   * Sichtbarkeitsgrenze - siehe Backend models/client_company.py::owner_user_id). */
  owner_user_id?: string | null;
}

export interface ClientDuplicateCandidate {
  id: string;
  name: string;
  kanzleigruppe: string | null;
  city: string | null;
  postal_code: string | null;
  similarity: number;
  same_location: boolean;
}

export interface Contact extends Entity {
  client_company_id: string;
  first_name: string;
  last_name: string;
  role_title: string | null;
  email: string | null;
  phone: string | null;
  is_primary: boolean;
  /** Vom Backend denormalisiert mitgeliefert (Join gegen client_companies),
   * damit die Kontakte-Liste den Kanzleinamen zeigen kann, ohne selbst den
   * kompletten Kanzlei-Bestand laden zu muessen. */
  client_company_name?: string | null;
}

export interface Vacancy extends Entity {
  title: string;
  client_company_id: string | null;
  location: string | null;
  search_radius_km: number;
  qualifications: string | null;
  experience: string | null;
  salary_min: number | null;
  salary_max: number | null;
  work_model: string | null;
  description: string | null;
  must_have: string[];
  nice_to_have: string[];
  status: "draft" | "open" | "on_hold" | "filled" | "closed";
  priority: "low" | "normal" | "high" | "urgent";
}

export interface GeoMappingResult {
  id: string;
  kind: "candidate" | "client";
  name: string;
  location: string;
  postal_code: string | null;
  latitude: number | null;
  longitude: number | null;
  status: string;
  tags: string[];
  mailing_ready: boolean;
  email?: string | null;
  // Kandidaten-spezifisch (bei kind="client" immer null)
  role?: string | null;
  qualification?: string | null;
  salary_expectation?: string | null;
  notice_period?: string | null;
  available_from?: string | null;
  remote_preference?: string | null;
  // Kanzlei-spezifisch (bei kind="candidate" immer null)
  terms_status?: string | null;
  fee_tier?: string | null;
  primary_contact_name?: string | null;
  active_vacancy_count?: number | null;
}

export type MailingRecipientKind = "candidate" | "client" | "contact";

export interface MailingRecipient {
  kind: MailingRecipientKind;
  id: string;
  name: string;
  email?: string | null;
}

export interface MailingGroup extends Entity {
  name: string;
  recipients: MailingRecipient[];
  template_key?: string | null;
}

export interface CandidateSubmission extends Entity {
  candidate_id: string;
  client_company_id: string | null;
  job_mandate_id: string | null;
  contact_person_id: string | null;
  status: SubmissionStatus;
  cancellation_reason?: SubmissionCancellationReason | null;
  submitted_at: string | null;
  summary: string | null;
  sent_profile_text?: string | null;
  salary_at_submission?: string | null;
  fee_percentage?: number | null;
  expected_fee?: number | null;
  refund_terms?: string | null;
  feedback_summary?: string | null;
  next_step?: string | null;
  follow_up_at?: string | null;
  owner?: string | null;
  outlook_draft_created?: boolean;
  email_sent?: boolean;
  last_activity_at: string;
  closed_at: string | null;
  pain_staerke?: number | null;
  entscheidungsklarheit?: number | null;
  markt_fit?: number | null;
  momentum?: number | null;
  closing_probability?: number | null;
  closing_status?: ClosingStatus | null;
  /** Zustaendiger Mitarbeiter (Komfort-Filter "Meine Prozesse", KEINE
   * Sichtbarkeitsgrenze - nicht zu verwechseln mit dem Freitextfeld `owner`
   * oben, siehe Backend models/submission.py::owner_user_id). */
  owner_user_id?: string | null;
}

/** Freitext-Feedback zu einem Prozess (siehe Backend models/recruiting.py::
 * SubmissionFeedback) - wird auch als generisches "Datum + Notiz"-Feld fuer
 * die Stufen qualification_call/cv_in/cv_out wiederverwendet (bewusste
 * Nutzer-Entscheidung: keine neuen DB-Spalten pro Stufe). */
export type FeedbackType = "client" | "candidate" | "internal";

export interface Feedback extends Entity {
  submission_id: string;
  feedback_type: FeedbackType;
  feedback_text: string;
  received_at: string;
  next_step: string | null;
  created_by: string | null;
  stage: SubmissionStatus | null;
}

export interface FeedbackCreate {
  feedback_type: FeedbackType;
  feedback_text: string;
  received_at: string;
  next_step?: string | null;
  created_by?: string | null;
  stage?: SubmissionStatus | null;
  /** Bullhorn-artiges "Action"-Feld (siehe feedback-panel.tsx): weicht dieser
   * Zielstatus vom aktuellen Submission-Status ab, wendet das Backend in
   * derselben Transaktion die bestehende Transition-Validierung an. Nur
   * qualification_call/cv_in/cv_out sind hier erlaubte Ziele. */
  target_status?: FeedbackTargetStatus | null;
}

export interface FeedbackUpdate {
  feedback_type?: FeedbackType;
  feedback_text?: string;
  received_at?: string;
  next_step?: string | null;
  created_by?: string | null;
  stage?: SubmissionStatus | null;
}

/** Antwort von POST /submissions/{id}/feedback - enthaelt neben der neuen
 * Notiz auch den (ggf. per target_status aktualisierten) Submission-Stand. */
export interface FeedbackCreateResult {
  feedback: Feedback;
  submission: CandidateSubmission;
}

/** Stufen, die ueber das Notiz-Status-Feld (FeedbackPanel/CandidateProcessLog)
 * gesetzt werden koennen - Interview/Offer/Placement brauchen eine
 * verknuepfte Kanzlei und haben eigene Panels (siehe stage-edit-modal.tsx). */
export type FeedbackTargetStatus = "qualification_call" | "cv_in" | "cv_out";

/** Payload fuer POST /candidates/{id}/quick-log - legt bei Bedarf automatisch
 * einen Prozess an (siehe candidate-process-log.tsx). */
export interface CandidateQuickLogCreate {
  stage: FeedbackTargetStatus;
  feedback_type: FeedbackType;
  feedback_text: string;
  received_at: string;
  next_step?: string | null;
}

export interface CandidateQuickLogResult {
  submission: CandidateSubmission;
  feedback: Feedback;
}

/** Anzahl erreichter Ereignisse je Stufe ueber ALLE Submissions eines
 * Kandidaten (siehe candidate-process-log.tsx). */
export interface CandidateStageSummary {
  qualification_call: number;
  cv_in: number;
  cv_out: number;
  interview: number;
  offer: number;
  placement: number;
}

/** Interview-Runde zu einem Prozess (siehe Backend models/recruiting.py::
 * Interview) - unabhaengig vom SubmissionStatus "interview": ein Prozess kann
 * mehrere Interview-Runden haben (Erstgespraech, 2. Runde, Finale, ...). Das
 * Backend legt beim Anlegen/Aendern automatisch einen verknuepften
 * CalendarEvent an (source_interview_id) - das passiert serverseitig, das
 * Frontend muss sich darum nicht kuemmern. */
export type InterviewStatus = "scheduled" | "completed" | "cancelled" | "no_show";

export interface Interview extends Entity {
  submission_id: string;
  scheduled_at: string;
  interview_type: string;
  location_or_link: string | null;
  participants: string[];
  status: InterviewStatus;
  notes: string | null;
}

export interface InterviewCreate {
  scheduled_at: string;
  interview_type: string;
  location_or_link?: string | null;
  participants?: string[];
  status?: InterviewStatus;
  notes?: string | null;
}

export interface InterviewUpdate {
  scheduled_at?: string;
  interview_type?: string;
  location_or_link?: string | null;
  participants?: string[];
  status?: InterviewStatus;
  notes?: string | null;
}

export type OfferStatus = "draft" | "received" | "accepted" | "declined" | "withdrawn";

export interface Offer extends Entity {
  submission_id: string;
  offered_salary: number;
  variable_compensation: number | null;
  start_date: string | null;
  offer_status: OfferStatus;
  notes: string | null;
}

export interface OfferCreate {
  offered_salary: number;
  variable_compensation?: number | null;
  start_date?: string | null;
  offer_status?: OfferStatus;
  notes?: string | null;
}

export interface OfferUpdate {
  offered_salary?: number;
  variable_compensation?: number | null;
  start_date?: string | null;
  offer_status?: OfferStatus;
  notes?: string | null;
}

export interface ClosingScoreResult {
  closing_probability: number;
  closing_status: ClosingStatus;
  action_recommendation: string;
}

export interface RegionModifier extends Entity {
  plz_prefix: string;
  label: string | null;
  modifier: number;
}

export type WarrantyStatus = "laufend" | "bald_ablaufend" | "abgelaufen";

export type PlacementStatus = "planned" | "started" | "completed" | "cancelled";

export interface Placement extends Entity {
  submission_id: string;
  start_date: string;
  final_salary: number;
  fee_percentage: number;
  calculated_fee: number;
  guarantee_period_months: number;
  status: PlacementStatus;
  warranty_end_date: string;
  warranty_status: WarrantyStatus;
}

export interface PlacementCreate {
  start_date: string;
  final_salary: number;
  fee_percentage?: number | null;
  guarantee_period_months?: number;
  status?: PlacementStatus;
}

export interface PlacementUpdate {
  start_date?: string;
  final_salary?: number;
  fee_percentage?: number | null;
  guarantee_period_months?: number;
  status?: PlacementStatus;
}

export interface CockpitItem {
  kind: string;
  title: string;
  detail: string;
  due_at: string | null;
  candidate_id: string | null;
  client_company_id: string | null;
  submission_id: string | null;
  priority: string;
}

export interface SourcingFunnel {
  has_data: boolean;
  pitches: number;
  responses: number;
  positive_responses: number;
  qualification_calls: number;
  pitch_to_response_rate: number | null;
  response_to_qualification_call_rate: number | null;
}

/** Etablierte Standard-Recruiting-Kennzahlen ueber den gesamten historischen
 * Bestand (nicht auf den period-Zeitraum beschraenkt) - siehe Backend
 * CockpitService::_recruiting_kpis. null, solange keine einzige
 * Placement/Interview-Transition vorliegt. */
export interface RecruitingKpis {
  time_to_fill_days: number | null;
  time_to_interview_days: number | null;
  average_fee_per_placement: number | null;
}

export interface Cockpit {
  period: string;
  important: CockpitItem[];
  hot_processes: CockpitItem[];
  recruiting_kpis: RecruitingKpis;
  kpis: {
    qualification_calls: number;
    cv_available: number;
    submissions: number;
    interviews: number;
    offers: number;
    placements: number;
    expected_fees: number;
    realized_fees: number;
  };
  rates: {
    submission_to_interview: number;
    interview_to_offer: number;
    offer_to_placement: number;
    placement_to_paid: number;
  };
  sourcing: SourcingFunnel;
}

export interface SourcingMetric extends Entity {
  period_start: string;
  period_end: string;
  source: string;
  campaign: string | null;
  pitches: number;
  responses: number;
  positive_responses: number;
  qualification_calls: number;
  notes: string | null;
}

export interface EmailTemplate {
  key: string;
  name: string;
  subject: string;
  body: string;
  placeholders: string[];
}

export interface Activity extends Entity {
  candidate_id: string | null;
  client_company_id: string | null;
  candidate_submission_id: string | null;
  activity_type: string;
  subject: string;
  details: string | null;
  occurred_at: string;
}

export interface Task extends Entity {
  candidate_id: string | null;
  client_company_id: string | null;
  candidate_submission_id: string | null;
  title: string;
  description: string | null;
  due_at: string | null;
  status: "open" | "in_progress" | "done" | "cancelled";
  priority: "low" | "normal" | "high" | "urgent";
  /** Zustaendiger Mitarbeiter (Komfort-Filter "Meine Aufgaben", KEINE
   * Sichtbarkeitsgrenze - siehe Backend models/task.py::owner_user_id). */
  owner_user_id?: string | null;
}

export interface DocumentMeta extends Entity {
  owner_type: "candidate" | "client" | "submission" | "placement" | "fee";
  owner_id: string;
  document_type: string;
  filename: string;
  storage_key: string;
  content_type: string | null;
  size_bytes: number | null;
  uploaded_by: string | null;
  sent_with_submission_id: string | null;
  has_generic_filename?: boolean;
}

export interface Note extends Entity {
  candidate_id: string | null;
  client_company_id: string | null;
  candidate_submission_id: string | null;
  body: string;
}

export interface CvExtractionSuggestion {
  postal_code: string | null;
  city: string | null;
  phone: string | null;
  job_title: string | null;
  qualification: string | null;
  ausbildung_titel: string | null;
  source_is_agency_profile: boolean;
}

export interface ClientMatch {
  client: ClientCompany;
  score: number;
  reasons: string[];
  already_submitted: boolean;
}

export interface BulkSubmitResultItem {
  client_company_id: string;
  outcome: "created" | "skipped";
  submission_id: string | null;
  reason: string | null;
}

export interface BulkSubmitResponse {
  results: BulkSubmitResultItem[];
  created_count: number;
  skipped_count: number;
}

export interface Paginated<T> {
  items: T[];
  total_count: number;
  limit: number;
  offset: number;
}

/** Serverseitige Such-/Pagination-Anfrage fuer Kandidaten/Kanzleien/Kontakte
 * (siehe lib/api/use-server-search.ts) - loest fetchAllPages() ab, das
 * bislang immer den kompletten Bestand lud. */
export interface PageQuery {
  search?: string;
  status?: string;
  /** Komfort-Filter "Meine..." - siehe owner_user_id auf Candidate/
   * ClientCompany/CandidateSubmission/Task oben. */
  ownerUserId?: string;
  /** Serverseitige Sortierspalte - muss ueber den gesamten Bestand laufen
   * (ORDER BY im Backend), nicht nur ueber die aktuell geladene Seite (siehe
   * candidates-table.tsx/clients-table.tsx SORT_ACCESSORS-Kommentar). */
  sortBy?: string;
  sortDir?: "asc" | "desc";
  limit: number;
  offset: number;
}

/** Chronologischer Eintrag im Audit-Log (nur sicherheits-/admin-relevante
 * Aktionen, siehe Backend models/recruiting.py::AuditLog) - admin-only, siehe
 * app/einstellungen/audit-log/page.tsx. */
export interface AuditLogEntry {
  id: string;
  entity_type: string;
  entity_id: string;
  action: string;
  changed_at: string;
  changed_by: string | null;
  old_values: Record<string, unknown> | null;
  new_values: Record<string, unknown> | null;
}

export interface DataResult<T> {
  data: T;
  source: "api" | "demo";
  error?: string;
}

export type SourcingSourceType =
  | "steuerberaterverzeichnis"
  | "wpk_berufsregister"
  | "brak_anwaltsverzeichnis"
  | "kanzlei_team_page";

export type SourcingLeadStatus = "pending" | "approved" | "rejected" | "possible_duplicate";

/** Vorschlags-Ebene des Sourcing-Agents (siehe Backend
 * models/sourcing_lead.py): automatisiert aus oeffentlichen Registern/
 * Team-Seiten gefundene Personen, die erst nach expliziter Bestaetigung
 * ("Uebernehmen") zu echten Kandidaten werden. */
export interface SourcingLead {
  id: string;
  created_at: string;
  updated_at: string;
  source_type: SourcingSourceType;
  source_url: string | null;
  first_name: string;
  last_name: string;
  current_employer: string | null;
  city: string | null;
  postal_code: string | null;
  raw_data: Record<string, unknown> | null;
  matched_client_company_id: string | null;
  status: SourcingLeadStatus;
  duplicate_of_candidate_id: string | null;
  created_candidate_id: string | null;
  found_at: string;
  reviewed_at: string | null;
  reviewed_by_user_id: string | null;
}

export type SourcingRunStatusValue = "running" | "completed" | "stopped";

/** Stand des Hintergrund-Sourcing-Laufs "alle Kanzleien scannen" (siehe
 * Backend models/sourcing_run.py) - Basis fuer Lauf-Anzeige + Stop-Button. */
export interface SourcingRunStatus {
  id: string;
  source_type: SourcingSourceType;
  status: SourcingRunStatusValue;
  total: number;
  processed: number;
  leads_created: number;
  stop_requested: boolean;
  started_at: string;
  finished_at: string | null;
}
