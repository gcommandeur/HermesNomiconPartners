import type { Candidate, CandidateSubmission, ClientCompany, Cockpit, EmailTemplate } from "./api/types";

const date = (days: number) => new Date(Date.now() - days * 86400000).toISOString();

export const demoCandidates: Candidate[] = [
  { id: "c-1", first_name: "Anna", last_name: "Weber", email: "anna.weber@example.test", phone: "+49 170 0000001", job_title: "Steuerberaterin", postal_code: "70173", city: "Stuttgart", linkedin_url: null, salary_expectation: "95.000 EUR", notice_period: "3 Monate", summary: "Schwerpunkt M&A Tax und Transaktionsberatung.", status: "active", created_at: date(90), updated_at: date(1), last_contact: date(1), next_step: "Interview vorbereiten" },
  { id: "c-2", first_name: "Markus", last_name: "Klein", email: "markus.klein@example.test", phone: "+49 170 0000002", job_title: "Prüfungsleiter", postal_code: "41199", city: "Mönchengladbach", linkedin_url: null, salary_expectation: "88.000 EUR", notice_period: "6 Wochen", summary: "Audit, HGB und Konzernabschlüsse.", status: "passive", created_at: date(130), updated_at: date(3), last_contact: date(3), next_step: "Quali-Call" },
  { id: "c-3", first_name: "Julia", last_name: "König", email: "julia.koenig@example.test", phone: "+49 170 0000003", job_title: "Tax Managerin", postal_code: "78628", city: "Rottweil", linkedin_url: null, salary_expectation: "105.000 EUR", notice_period: "3 Monate", summary: "International Tax und Verrechnungspreise.", status: "active", created_at: date(70), updated_at: date(2), last_contact: date(2), next_step: "Feedback nachfassen" },
  { id: "c-4", first_name: "David", last_name: "Braun", email: "david.braun@example.test", phone: "+49 170 0000004", job_title: "Steuerfachwirt", postal_code: "72336", city: "Balingen", linkedin_url: null, salary_expectation: "68.000 EUR", notice_period: "4 Wochen", summary: "Mittelstandsberatung und Jahresabschlüsse.", status: "placed", created_at: date(200), updated_at: date(8), last_contact: date(8), next_step: "Start begleiten" },
  { id: "c-5", first_name: "Lea", last_name: "Fischer", email: "lea.fischer@example.test", phone: "+49 170 0000005", job_title: "Senior Tax Consultant", postal_code: "60311", city: "Frankfurt", linkedin_url: null, salary_expectation: "79.000 EUR", notice_period: "2 Monate", summary: "Corporate Tax und Tax Compliance.", status: "active", created_at: date(55), updated_at: date(0), last_contact: date(0), next_step: "CV freigeben" },
];

export const demoClients: ClientCompany[] = [
  { id: "cl-1", name: "BlueTax Partners", status: "active", website: null, email: "kontakt@bluetax.example.test", phone: "+49 711 000001", street: null, postal_code: "70173", city: "Stuttgart", notes: null, size: "80 Mitarbeitende", focus: "Tax Advisory", contact_name: "Dr. Eva Berger", active_mandates: 3, last_contact: date(1), terms_status: "Unterzeichnet", created_at: date(500), updated_at: date(1) },
  { id: "cl-2", name: "Rhein Audit GmbH", status: "acquisition", website: null, email: "kontakt@rheinaudit.example.test", phone: "+49 2161 000002", street: null, postal_code: "41199", city: "Mönchengladbach", notes: null, size: "45 Mitarbeitende", focus: "Audit & Accounting", contact_name: "Thomas Schmitz", active_mandates: 1, last_contact: date(6), terms_status: "In Prüfung", created_at: date(320), updated_at: date(6) },
  { id: "cl-3", name: "Neckar Treuhand", status: "active", website: null, email: "kontakt@neckar.example.test", phone: "+49 741 000003", street: null, postal_code: "78628", city: "Rottweil", notes: null, size: "120 Mitarbeitende", focus: "Tax & Legal", contact_name: "Laura Fischer", active_mandates: 4, last_contact: date(2), terms_status: "Unterzeichnet", created_at: date(600), updated_at: date(2) },
  { id: "cl-4", name: "Zollern Consulting", status: "blocked", website: null, email: "kontakt@zollern.example.test", phone: "+49 7433 000004", street: null, postal_code: "72336", city: "Balingen", notes: null, size: "25 Mitarbeitende", focus: "Mittelstand", contact_name: "Michael Wolf", active_mandates: 0, last_contact: date(40), terms_status: "Nicht vorhanden", created_at: date(410), updated_at: date(40) },
];

export const demoSubmissions: CandidateSubmission[] = [
  { id: "s-1", candidate_id: "c-1", client_company_id: "cl-1", job_mandate_id: "m-1", contact_person_id: null, status: "interview", submitted_at: date(8), summary: "Interview mit Partnerkreis.", last_activity_at: date(1), closed_at: null, created_at: date(10), updated_at: date(1) },
  { id: "s-2", candidate_id: "c-3", client_company_id: "cl-3", job_mandate_id: "m-2", contact_person_id: null, status: "offer", submitted_at: date(12), summary: "Finales Feedback steht aus.", last_activity_at: date(2), closed_at: null, created_at: date(14), updated_at: date(2) },
  { id: "s-3", candidate_id: "c-2", client_company_id: "cl-2", job_mandate_id: null, contact_person_id: null, status: "cv_out", submitted_at: date(3), summary: "Profil an Fachbereich weitergegeben.", last_activity_at: date(3), closed_at: null, created_at: date(4), updated_at: date(3) },
  { id: "s-4", candidate_id: "c-5", client_company_id: null, job_mandate_id: null, contact_person_id: null, status: "cv_in", submitted_at: date(0), summary: "CV liegt vor, Kanzlei noch offen.", last_activity_at: date(0), closed_at: null, created_at: date(0), updated_at: date(0) },
  { id: "s-5", candidate_id: "c-4", client_company_id: "cl-3", job_mandate_id: "m-4", contact_person_id: null, status: "placement", submitted_at: date(50), summary: "Start zum Monatsbeginn.", last_activity_at: date(8), closed_at: date(8), created_at: date(52), updated_at: date(8) },
];

export const demoActivities = [
  { title: "Interview terminiert", detail: "Anna Weber · BlueTax Partners", time: "Vor 35 Min." },
  { title: "CV-Out versendet", detail: "Lea Fischer · BlueTax Partners", time: "Vor 2 Std." },
  { title: "Offer-Feedback ergänzt", detail: "Julia König · Neckar Treuhand", time: "Gestern" },
  { title: "Kandidatenprofil aktualisiert", detail: "Markus Klein", time: "Gestern" },
];

export const demoFollowUps = [
  { title: "Feedback zu CV-Out einholen", subject: "Markus Klein · Rhein Audit", due: "Heute", priority: "Hoch" },
  { title: "Interview-Briefing durchführen", subject: "Anna Weber · BlueTax Partners", due: "Morgen", priority: "Normal" },
  { title: "Offer-Konditionen abstimmen", subject: "Julia König · Neckar Treuhand", due: "30. Juni", priority: "Hoch" },
];

export const demoCockpit: Cockpit = {
  period: "week",
  important: [
    { kind: "submission", title: "CV-Out nachfassen", detail: "Markus Klein · Rhein Audit GmbH", due_at: date(0), candidate_id: "c-2", client_company_id: "cl-2", submission_id: "s-3", priority: "high" },
    { kind: "interview", title: "Interviewfeedback einholen", detail: "Anna Weber · BlueTax Partners", due_at: date(-1), candidate_id: "c-1", client_company_id: "cl-1", submission_id: "s-1", priority: "high" },
    { kind: "offer", title: "Offer-Konditionen abstimmen", detail: "Julia König · Neckar Treuhand", due_at: date(0), candidate_id: "c-3", client_company_id: "cl-3", submission_id: "s-2", priority: "urgent" },
  ],
  hot_processes: [
    { kind: "submission", title: "Interview geplant", detail: "Anna Weber · BlueTax Partners", due_at: date(-1), candidate_id: "c-1", client_company_id: "cl-1", submission_id: "s-1", priority: "high" },
    { kind: "submission", title: "Offer erwartet", detail: "Julia König · Neckar Treuhand", due_at: date(0), candidate_id: "c-3", client_company_id: "cl-3", submission_id: "s-2", priority: "high" },
    { kind: "submission", title: "Placement", detail: "David Braun · Neckar Treuhand", due_at: null, candidate_id: "c-4", client_company_id: "cl-3", submission_id: "s-5", priority: "normal" },
  ],
  data_gaps: [],
  recruiting_kpis: { time_to_fill_days: 38, time_to_interview_days: 11, average_fee_per_placement: 18250 },
  kpis: { qualification_calls: 7, cv_available: 12, submissions: 9, cv_outs_reached_count: 6, interviews: 4, offers: 2, offer_stage_reached_count: 2, placements: 1, placement_stage_reached_count: 1, expected_fees: 48600, realized_fees: 18250, open_invoice_placement_count: 1 },
  rates: { submission_to_interview: 44.4, interview_to_offer: 50, offer_to_placement: 50, placement_to_paid: 100 },
  sourcing: { has_data: true, pitches: 126, responses: 34, positive_responses: 18, qualification_calls: 7, pitch_to_response_rate: 27, response_to_qualification_call_rate: 20.6 },
};

export const demoEmailTemplates: EmailTemplate[] = [
  { key: "candidate_submission", name: "Kandidat vorstellen", subject: "Profil: {candidate} – {role}", body: "Guten Tag {contact},\n\n{short_profile}\n\nBeste Grüße", placeholders: ["candidate", "client", "contact", "role", "short_profile"] },
  { key: "submission_follow_up", name: "CV-Out nachfassen", subject: "Feedback zu {candidate}", body: "Guten Tag {contact},\n\nkonnten Sie das Profil bereits prüfen?", placeholders: ["candidate", "client", "contact"] },
  { key: "interview_feedback", name: "Interviewfeedback", subject: "Feedback zum Interview", body: "Guten Tag {contact},\n\nwie ist Ihr Eindruck aus dem Gespräch?", placeholders: ["candidate", "client", "contact"] },
  { key: "send_terms", name: "AGB senden", subject: "Zusammenarbeit mit CC", body: "Guten Tag {contact},\n\nanbei erhalten Sie unsere Konditionen.", placeholders: ["client", "contact"] },
];
