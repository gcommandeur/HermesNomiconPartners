export type CandidateStatus = "active" | "passive" | "placed" | "blocked" | "archived";
/** Normalisierte Berufsrollen-Taxonomie (siehe Backend models/enums.py::
 * Rolle) - feste 10 Zielrollen + "sonstige" statt Freitext. Candidate.rollen
 * ist eine LISTE (mehrere gleichzeitig gueltige Rollen moeglich, z.B.
 * Steuerberater UND Partner), keine zeitliche Abfolge. */
export type Rolle =
  | "steuerfachangestellte"
  | "steuerfachwirt"
  | "bilanzbuchhalter"
  | "steuerberater"
  | "partner"
  | "pruefungsassistent"
  | "pruefungsleiter"
  | "wirtschaftspruefer"
  | "rechtsfachangestellte"
  | "rechtsanwalt"
  | "sonstige";
/** Strukturierte Abschlussart(en) (Backend models/enums.py::Abschlussart) -
 * macht ausbildung_titel/qualification (Freitext) filterbar. Candidate.
 * abschluesse ist eine LISTE (mehrere Abschlussarten gleichzeitig moeglich,
 * z.B. Ausbildung UND spaeteres Berufsexamen). */
export type Abschlussart =
  | "ausbildung"
  | "studium_bachelor"
  | "studium_master"
  | "studium_promotion"
  | "berufsexamen_stb"
  | "berufsexamen_wp"
  | "berufsexamen_ra"
  | "fortbildung"
  | "kein_abschluss_erkennbar";
/** Strukturierte Rechtsgebiete (Backend models/enums.py::Rechtsgebiet) -
 * nur bei rechtsanwalt/rechtsfachangestellte inhaltlich relevant, aber
 * kandidatenweit gefuehrt. LISTE, da mehrere Rechtsgebiete gleichzeitig
 * moeglich. */
export type Rechtsgebiet =
  | "arbeitsrecht"
  | "steuerrecht"
  | "gesellschaftsrecht"
  | "handelsrecht"
  | "vertragsrecht"
  | "familienrecht"
  | "erbrecht"
  | "insolvenzrecht"
  | "immobilienrecht"
  | "ip_recht"
  | "datenschutzrecht"
  | "prozessrecht"
  | "sonstiges";
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
  /** Normalisierte Rollen-Kategorien (Backend models/enums.py::Rolle) -
   * durchsuchbare, kategoriale Ergaenzung zu job_title (Freitext-
   * Originaltitel aus dem CV), nicht dessen Ersatz. */
  rollen?: Rolle[];
  /** Titelschutz-Korrektur Schritt 2: gesetzt, wenn eine geschuetzte Rolle
   * (steuerberater/wirtschaftspruefer/rechtsanwalt) OHNE erkennbaren Beleg
   * im CV vergeben wurde (siehe Backend scripts/
   * audit_titelschutz_unverified_roles.py). rollen selbst bleibt dabei
   * unangetastet - system-gesetzt, nicht direkt ueber PATCH steuerbar,
   * siehe Backend models/candidate.py::rollen_unbestaetigt. */
  rollen_unbestaetigt?: boolean;
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
  /** Software/IT-Tools (DATEV, SAP, MS Office, ...) - getrennt von
   * fachliche_schwerpunkte, siehe Backend models/candidate.py::edv_kenntnisse. */
  edv_kenntnisse?: string[];
  ausbildung_titel?: string | null;
  /** Strukturierte Abschlussart(en) aus festem Vokabular - macht
   * ausbildung_titel/qualification (Freitext) filterbar, siehe Backend
   * models/candidate.py::abschluesse. */
  abschluesse?: Abschlussart[];
  /** Nur bei rechtsanwalt/rechtsfachangestellte inhaltlich relevant, siehe
   * Backend models/candidate.py::rechtsgebiete. */
  rechtsgebiete?: Rechtsgebiet[];
  /** Nur bei rechtsanwalt relevant, kurzer Freitext (z.B. "1. Staatsexamen:
   * befriedigend (7,5 Punkte)") - siehe Backend models/candidate.py::
   * examensnoten. */
  examensnoten?: string | null;
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
  /** Nur gesetzt, wenn GET /candidates mit `search` aufgerufen wurde (siehe
   * Backend repositories/candidates.py::compute_search_match_fields) -
   * macht nachvollziehbar, WARUM ein Treffer gefunden wurde: welche
   * Feld(er) gematcht haben (Feld-Keys, siehe SEARCH_FIELD_LABELS in
   * lib/utils.ts) und - fuer fachliche_schwerpunkte/edv_kenntnisse - die
   * konkreten gematchten Eintraege fuers Hervorheben. null bei jeder
   * anderen Abfrage (z.B. GET /candidates/{id}). */
  search_match_fields?: string[] | null;
  search_matched_values?: string[] | null;
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
  /** Von einem Nicht-Admin angelegt, Freigabe durch die GF steht aus. */
  approval_pending?: boolean;
}

export type ApprovalKind = "new_client" | "honorar_change" | "invoice_issue";

export interface ApprovalRequest {
  id: string;
  entity_type: "client_company" | "fee";
  entity_id: string;
  kind: ApprovalKind;
  status: "pending" | "approved" | "rejected";
  requested_by: string | null;
  requested_at: string;
  old_values: Record<string, unknown> | null;
  proposed_values: Record<string, unknown> | null;
  decided_by: string | null;
  decided_at: string | null;
  decision_note: string | null;
  entity_label: string | null;
}

export type InvoiceStatus = "draft" | "issued" | "due" | "paid" | "cancelled";

export interface Fee extends Entity {
  placement_id: string;
  amount_net: string;
  vat_rate: string;
  amount_gross: string;
  invoice_status: InvoiceStatus;
  invoice_date: string | null;
  payment_due_date: string | null;
  paid_at: string | null;
}

export interface InvoiceStatusChangeResult {
  fee: Fee;
  approval_request: ApprovalRequest | null;
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
  fee_percentage: number | null;
  work_model: string | null;
  description: string | null;
  must_have: string[];
  nice_to_have: string[];
  status: "draft" | "open" | "on_hold" | "filled" | "closed";
  priority: "low" | "normal" | "high" | "urgent";
}

export interface CandidateMatch {
  candidate: Candidate;
  score: number;
  reasons: string[];
  in_radius: boolean | null;
}

/** Geo Mapping ist eine reine Kanzleien-Umkreissuche (die kandidatenzentrierte
 * Umkreissuche uebernimmt die "CV Out"-Kampagne direkt am Kandidaten) - kein
 * `kind`-Feld mehr, jedes Ergebnis ist implizit eine Kanzlei. */
export interface GeoMappingResult {
  id: string;
  name: string;
  location: string;
  postal_code: string | null;
  latitude: number | null;
  longitude: number | null;
  status: string;
  tags: string[];
  mailing_ready: boolean;
  email?: string | null;
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

// "CV Out"-Kampagne (Radius-Umkreissuche ab Kandidat, siehe
// GET /candidates/{id}/cv-out-targets) - nicht zu verwechseln mit dem
// bestehenden CV-Out-Status im Matching-/Submission-Tab (candidate-matching-
// panel.tsx), das ist eine reine Pipeline-Statusmarkierung ohne Mailversand.
export interface CvOutContact {
  id: string;
  first_name: string;
  last_name: string;
  email: string;
  role_title: string | null;
  is_primary: boolean;
}

export interface CvOutTargetClient {
  id: string;
  name: string;
  location: string;
  postal_code: string | null;
  status: string;
  distance_km: number;
  contacts: CvOutContact[];
}

export interface CvOutTargetsResult {
  candidate_id: string;
  radius_km: number;
  targets: CvOutTargetClient[];
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
  /** Expliziter Abschluss NACH einem Placement (POST /submissions/{id}/
   * archive) - blendet den Prozess aus dem Kanban aus, ohne Status/
   * Historie anzutasten. null ist der Normalfall (nicht abgeschlossen). */
  archived_at?: string | null;
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
  // KEIN SubmissionStatus-Feld wie die uebrigen sechs - Pitch/InMail ist
  // keine Kanban-Stufe (Nutzer-Entscheidung: kein eigener Prozess-Status,
  // keine Kanzlei-Bindung wie bei CV-Outs), sondern zaehlt unabhaengige
  // CandidatePitchLog-Eintraege direkt am Kandidaten (siehe
  // candidate-process-log.tsx/POST /candidates/{id}/pitch-log).
  pitch: number;
  qualification_call: number;
  cv_in: number;
  cv_out: number;
  interview: number;
  offer: number;
  placement: number;
}

/** Payload fuer POST /candidates/{id}/pitch-log - loggt ein Pitch/InMail-
 * Ereignis, OHNE einen Prozess anzulegen oder einen Statuswechsel
 * auszuloesen (anders als CandidateQuickLogCreate oben). */
export interface CandidatePitchLogCreate {
  occurred_at: string;
  notes_text?: string | null;
  next_step?: string | null;
}

export interface CandidatePitchLogRead extends Entity {
  candidate_id: string;
  occurred_at: string;
  notes_text: string | null;
  next_step: string | null;
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
  /** Additiver Rabatt in % auf die berechnete Fee, nur im "Berechnet"-Modus
   * wirksam (siehe fee_fix). 0 = kein Rabatt. */
  rabatt_percentage: number;
  /** Wenn gesetzt: dieser Betrag ist die Fee 1:1, fee_percentage/
   * rabatt_percentage werden ignoriert (aber weiterhin gespeichert/angezeigt,
   * falls spaeter zurueck auf "Berechnet" gewechselt wird). */
  fee_fix: number | null;
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
  rabatt_percentage?: number;
  fee_fix?: number | null;
  guarantee_period_months?: number;
  status?: PlacementStatus;
}

export interface PlacementUpdate {
  start_date?: string;
  final_salary?: number;
  fee_percentage?: number | null;
  rabatt_percentage?: number;
  fee_fix?: number | null;
  /** Einziger Weg, fee_fix nach dem Speichern wieder zu loeschen (Umschalter
   * zurueck auf "Berechnet") - siehe Backend PlacementUpdate.clear_fee_fix. */
  clear_fee_fix?: boolean;
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
  /** Nur bei kind="task" gesetzt - fuer die Dashboard-To-Do-Sektion
   * (snooze/resolve), siehe Backend schemas/operational.py::CockpitItem. */
  task_id?: string | null;
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

/** Zwei unterschiedliche Fragen, bewusst getrennt (Backend schemas/
 * operational.py::CockpitKpis-Docstring fuer die volle Begruendung):
 * PIPELINE-Kennzahlen (*_reached_count/interviews) aus der echten
 * Statuswechsel-Historie ("wurde dieser Schritt im Kanban gemacht"),
 * KAUFMAENNISCHE Kennzahlen (offers/placements/expected_fees/realized_fees)
 * aus den gepflegten Offer-/Placement-Datensaetzen (Gehalt/Fee haengen nur
 * dort). Wo beide nebeneinander stehen, ist die Differenz eine Kennzahl
 * fuer sich - siehe Cockpit.data_gaps. */
export interface CockpitKpis {
  qualification_calls: number;
  cv_available: number;
  /** "Neue Prozesse" - im Zeitraum ANGELEGTE Prozesse (nicht: erreichte
   * CV-Out-Stufe, trotz des Feldnamens - siehe cv_outs_reached_count). */
  submissions: number;
  /** PIPELINE: im Zeitraum tatsaechlich CV_OUT erreicht (Transition). */
  cv_outs_reached_count: number;
  /** PIPELINE: im Zeitraum tatsaechlich INTERVIEW erreicht (Transition). */
  interviews: number;
  /** KAUFMAENNISCH: echte Offer-Objekte, im Zeitraum angelegt. */
  offers: number;
  /** PIPELINE: im Zeitraum tatsaechlich OFFER erreicht (Transition). */
  offer_stage_reached_count: number;
  /** KAUFMAENNISCH: echte Placement-Objekte, im Zeitraum angelegt. */
  placements: number;
  /** PIPELINE: im Zeitraum tatsaechlich PLACEMENT erreicht (Transition). */
  placement_stage_reached_count: number;
  expected_fees: number;
  realized_fees: number;
  /** DISTINCT Placements mit mindestens einer nicht-bezahlten Fee (draft/
   * issued/due) - unabhaengig vom gewaehlten `period`. */
  open_invoice_placement_count: number;
  /** PIPELINE: geloggte Pitch/InMail-Ereignisse im Zeitraum (Stufe 1 der
   * 7-stufigen Pipeline, siehe CandidatePitchLog) - ersetzt die vorherige
   * manuelle SourcingFunnel.pitches-Zahl. */
  pitches: number;
}

export interface Cockpit {
  period: string;
  important: CockpitItem[];
  hot_processes: CockpitItem[];
  /** Prozesse im Status OFFER/PLACEMENT ohne zugehoerigen Offer-/Placement-
   * Datensatz - unfertige Erfassungen (Kanban-Drag ohne ausgefuelltes
   * Formular). */
  data_gaps: CockpitItem[];
  recruiting_kpis: RecruitingKpis;
  kpis: CockpitKpis;
  rates: {
    pitch_to_qualification_call_rate: number;
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

// PATCH /email-templates/{key} - bewusst ohne `key` (Key ist die stabile
// Referenz fuer MailingGroup.template_key, siehe Backend-Docstring).
export interface EmailTemplateUpdate {
  name?: string;
  subject?: string;
  body?: string;
}

export interface Activity extends Entity {
  candidate_id: string | null;
  client_company_id: string | null;
  candidate_submission_id: string | null;
  activity_type: string;
  subject: string;
  details: string | null;
  occurred_at: string;
  /** Ausloesender Nutzer (z.B. Mailversand) - null bei automatischen/eingehenden. */
  sent_by_user_id?: string | null;
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
  /** "Spaeter erinnern" (POST /tasks/{id}/snooze) - solange in der Zukunft,
   * blendet GET /tasks?status=open (und die Dashboard-To-Do-Sektion) den
   * Task aus, ohne ihn zu schliessen. */
  snoozed_until?: string | null;
  /** Nur bei automatisch aus einer Mail erzeugten Tasks gesetzt (siehe
   * Backend services/mail_sync.py). */
  source_mail_message_id?: string | null;
  /** Abschlussgrund von POST /tasks/{id}/resolve - null, solange offen oder
   * per snooze() zurueckgestellt (kein Abschluss). */
  resolution_outcome?: TaskResolveOutcome | null;
}

export type TaskResolveOutcome = "no_response" | "meeting_scheduled" | "done" | "not_relevant";

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
  /** Autor - null bei Alt-Notizen und automatisch erzeugten Notizen. */
  created_by_user_id?: string | null;
  created_by_name?: string | null;
}

/** Notiz oder Prozess-Feedback zu einem Kandidaten mit Autor (Timeline). */
export interface CandidateComment {
  kind: "note" | "feedback";
  id: string;
  occurred_at: string;
  author: string | null;
  text: string;
  stage: SubmissionStatus | null;
  feedback_type: string | null;
  submission_id: string | null;
}

export interface CvExtractionSuggestion {
  first_name: string | null;
  last_name: string | null;
  email: string | null;
  postal_code: string | null;
  city: string | null;
  phone: string | null;
  job_title: string | null;
  qualification: string | null;
  ausbildung_titel: string | null;
  source_is_agency_profile: boolean;
}

/** Antwort von POST/GET /candidates/cv-preview: "processing" heisst, ein
 * gescanntes PDF wird im Hintergrund ausgewertet - das Ergebnis liefert
 * GET /candidates/cv-preview/{job_id}. */
export interface CvPreviewResponse extends CvExtractionSuggestion {
  status: "done" | "processing" | "failed";
  job_id: string | null;
  error: string | null;
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
  /** Nur fuer Kandidaten (Backend GET /candidates?rollen=...) - Filter auf
   * die normalisierte Rollen-Taxonomie, unabhaengig von `search` und
   * miteinander UND-verknuepft nutzbar. */
  rollen?: Rolle[];
  /** Nur fuer Kandidaten (Backend GET /candidates?abschluesse=...) - Filter
   * auf die strukturierte Abschlussart-Taxonomie, gleiches Muster wie
   * `rollen` (Mehrfachauswahl, ODER-verknuepft, unabhaengig von `rollen`
   * nutzbar). */
  abschluesse?: Abschlussart[];
  /** Nur fuer Kandidaten - echter PLZ+Umkreis-Filter (Backend GET
   * /candidates?plz_ort=...&radius_km=...), unabhaengig vom bestehenden
   * `status`-Filter oben und kombinierbar mit `search`/`rollen`. Beide
   * Werte muessen gesetzt sein, sonst greift kein Umkreis-Filter (siehe
   * services/candidates.py::list_filtered). */
  plzOrt?: string;
  radiusKm?: number;
  /** Nur fuer Kandidaten (Backend GET /candidates?rollen_unbestaetigt=...) -
   * Titelschutz-Korrektur Schritt 2: findet Kandidaten mit unbestaetigter
   * geschuetzter Rolle wieder (Nutzer-Vorgabe - "sonst findet man sie nicht
   * wieder"). undefined laesst den Filter aus. */
  rollenUnbestaetigt?: boolean;
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

/** Loeschanfrage (Art. 17 DSGVO), Nachverfolgung um die bestehende
 * Anonymisierung herum - admin-only, siehe app/einstellungen/loeschanfragen/
 * page.tsx und Backend models/deletion_request.py. */
export interface DeletionRequestEntry {
  id: string;
  candidate_id: string;
  requested_at: string;
  requested_via: string;
  deadline: string;
  completed_at: string | null;
  completed_by_user_id: string | null;
  candidate_first_name: string;
  candidate_last_name: string;
  candidate_number: string | null;
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
  // Stellenbeschreibung/Werdegang/weitere Infos laut Quelle - wird bei
  // "Übernehmen" als Notiz am neuen Kandidaten hinterlegt (siehe Backend
  // SourcingService.approve_lead).
  notes_text: string | null;
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

/** Verbundenes Postfach (IMAP lesend, SMTP schreibend). Enthaelt bewusst
 * KEIN Passwort-Feld - das Backend gibt es nie zurueck, auch nicht
 * maskiert (siehe backend/schemas/mail.py). */
export type MailAccountProvider = "imap_smtp" | "microsoft_graph";
export type MailAccountOAuthStatus = "connected" | "needs_reconnect";

export interface MailAccount {
  id: string;
  address: string;
  label: string;
  /** "imap_smtp" (Passwort-Login, Default) oder "microsoft_graph" (OAuth,
   * z.B. info@commandeurconsulting.de) - siehe Backend models/mail.py::
   * MailAccount. imap_host/smtp_host/username sind fuer microsoft_graph-
   * Konten null. */
  provider: MailAccountProvider;
  imap_host: string | null;
  imap_port: number;
  imap_use_ssl: boolean;
  smtp_host: string | null;
  smtp_port: number;
  smtp_use_ssl: boolean;
  username: string | null;
  /** Nur fuer provider="microsoft_graph" gesetzt - "needs_reconnect" zeigt
   * den "Postfach neu verbinden"-Button statt eines stillen Ausfalls. */
  oauth_status: MailAccountOAuthStatus | null;
  is_active: boolean;
  default_for_cv_out: boolean;
  /** Rate-Limiting fuer den SMTP-Versand (Backend services/mail_send.py) -
   * Pause in Sekunden zwischen zwei Sends bzw. maximale Anzahl Mails pro
   * Tag ueber dieses Postfach, je Postfach konfigurierbar statt hart
   * verdrahtet. */
  send_throttle_seconds: number;
  daily_send_limit: number;
  last_synced_at: string | null;
  sync_error: string | null;
}

/** Ergebnis eines manuellen Abrufs. ok=false kommt mit HTTP 200 zurueck,
 * damit die Oberflaeche den konkreten Grund anzeigen kann. */
export interface MailSyncResult {
  mail_account_id: string;
  ok: boolean;
  fetched: number;
  created_activities: number;
  pending_review: number;
  skipped_duplicates: number;
  failed_messages: number;
  // Nur Mails ab services/mail_sync.py::AUTOMATION_CUTOFF ohne Fuzzy-
  // Namenstreffer - separat ausgewiesen, weil hier ohne menschliche
  // Bestaetigung ein neuer Kandidat entstanden ist.
  auto_created_candidates: number;
  error: string | null;
}

export type MailMatchStatus = "matched" | "pending_review" | "unmatched";

/** Eine Zeile in der Liste der eingelesenen Mails (Postfaecher-Seite,
 * GET /mail-accounts/{id}/messages) - siehe backend/schemas/mail.py::
 * MailMessageRead. Kontaktpersonen haben keine eigene Detailseite, deshalb
 * traegt matched_contact_person_client_company_id die Kanzlei-ID, zu der
 * stattdessen verlinkt wird. */
export interface MailMessageListItem {
  id: string;
  from_name: string | null;
  from_address: string | null;
  subject: string | null;
  received_at: string;
  match_status: MailMatchStatus;
  is_linkedin: boolean;
  matched_candidate_id: string | null;
  matched_candidate_name: string | null;
  matched_contact_person_id: string | null;
  matched_contact_person_name: string | null;
  matched_contact_person_client_company_id: string | null;
  matched_client_company_id: string | null;
  matched_client_company_name: string | null;
}

/** Payload fuer POST /mail/send (Auftrag "M365-Postfach-Integration",
 * Compose-UI) - siehe backend/schemas/mail.py::MailSendRequest. */
export interface MailSendRequest {
  account_id?: string | null;
  to_address: string;
  to_name?: string | null;
  subject: string;
  body_text: string;
  // Dokument-IDs (siehe DocumentMeta) - CV-Dokumente werden serverseitig
  // hart abgelehnt (project_submission_workflow_cv_attachment_guard),
  // clientseitig zusaetzlich aus dem Picker ausgeblendet.
  attachment_document_ids?: string[];
  candidate_id?: string | null;
  client_company_id?: string | null;
  contact_person_id?: string | null;
}

export interface MailSendResult {
  id: string;
  mail_account_id: string;
  to_address: string;
  subject: string;
  sent_at: string;
  matched_candidate_id: string | null;
  matched_client_company_id: string | null;
  matched_contact_person_id: string | null;
  created_activity_id: string | null;
}

/** Antwort auf GET /mail-accounts/oauth/start - das Frontend leitet den
 * Browser per window.location.href dorthin weiter. */
export interface MailOAuthStartResult {
  authorization_url: string;
}

// KPI-Punkte-System + Geschaeftsfuehrer-Ansicht + Live-Ranking (Auftrag
// "Geschaeftsfuehrer-Ansicht + KPI-Punkte-System + Live-Ranking") - `stage`
// ist einer der 7 STAGE_KEYS-Werte aus backend/src/cc_crm/services/
// kpi_scoring.py, siehe stage-labels.ts fuer die deutschen Anzeigenamen.
export interface KpiPointRule {
  stage: string;
  points: number;
}

export interface AppSettings {
  kpi_ranking_metric: string;
  kpi_ranking_period: "day" | "week";
}

export interface TeamMemberKpis {
  user_id: string;
  display_name: string;
  stages: Record<string, number>;
  points: number;
  // Immer null bis Soll-Werte pro Mitarbeiter spezifiziert sind (Nutzer-
  // Vorgabe: nicht raten) - Spalte im Frontend trotzdem vorbereitet.
  target: null;
}

export interface TeamKpiOverview {
  period: string;
  members: TeamMemberKpis[];
}

export interface KpiRankingEntry {
  user_id: string;
  display_name: string;
  value: number;
}

export interface KpiRankingResult {
  period: string;
  metric: string;
  entries: KpiRankingEntry[];
}
