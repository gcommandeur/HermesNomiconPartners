import type { Contact, GeoMappingResult, Vacancy } from "@/lib/api/types";

const date = (days: number) => new Date(Date.now() - days * 86400000).toISOString();

export const demoContacts: Contact[] = [
  { id: "ct-1", client_company_id: "cl-1", first_name: "Eva", last_name: "Berger", role_title: "Partnerin Tax", email: "eva.berger@bluetax.example.com", phone: "+49 711 000011", is_primary: true, created_at: date(500), updated_at: date(1) },
  { id: "ct-2", client_company_id: "cl-1", first_name: "Simon", last_name: "Keller", role_title: "HR Business Partner", email: "simon.keller@bluetax.example.com", phone: "+49 711 000012", is_primary: false, created_at: date(300), updated_at: date(5) },
  { id: "ct-3", client_company_id: "cl-2", first_name: "Thomas", last_name: "Schmitz", role_title: "Geschäftsführer", email: "thomas.schmitz@rheinaudit.example.com", phone: "+49 2161 000021", is_primary: true, created_at: date(320), updated_at: date(6) },
  { id: "ct-4", client_company_id: "cl-3", first_name: "Laura", last_name: "Fischer", role_title: "Partnerin Legal & Tax", email: "laura.fischer@neckar.example.com", phone: "+49 741 000031", is_primary: true, created_at: date(600), updated_at: date(2) },
  { id: "ct-5", client_company_id: "cl-4", first_name: "Michael", last_name: "Wolf", role_title: "Inhaber", email: "michael.wolf@zollern.example.com", phone: "+49 7433 000041", is_primary: true, created_at: date(410), updated_at: date(40) },
];

export const demoVacancies: Vacancy[] = [
  { id: "v-1", title: "Senior Tax Manager M&A", client_company_id: "cl-1", location: "Stuttgart", search_radius_km: 60, qualifications: "Steuerberaterexamen", experience: "6+ Jahre", salary_min: 95000, salary_max: 120000, work_model: "Hybrid", description: "Beratung nationaler und internationaler Transaktionen.", must_have: ["M&A Tax", "Steuerberaterexamen"], nice_to_have: ["Big4-Erfahrung", "Englisch C1"], status: "open", priority: "urgent", created_at: date(20), updated_at: date(1) },
  { id: "v-2", title: "Prüfungsleiter Audit", client_company_id: "cl-2", location: "Mönchengladbach", search_radius_km: 80, qualifications: "WP-Track oder HGB Audit", experience: "4+ Jahre", salary_min: 80000, salary_max: 95000, work_model: "Hybrid", description: "Eigenverantwortliche Prüfungsleitung im Mittelstand.", must_have: ["HGB", "Teamleitung"], nice_to_have: ["Konzernabschluss", "DATEV"], status: "open", priority: "high", created_at: date(35), updated_at: date(6) },
  { id: "v-3", title: "Tax Consultant Corporate Tax", client_company_id: null, location: "Frankfurt", search_radius_km: 50, qualifications: "BWL / Steuern", experience: "2+ Jahre", salary_min: 65000, salary_max: 82000, work_model: "Remote möglich", description: "Suchprofil für mehrere passende Kanzleien im Rhein-Main-Gebiet.", must_have: ["Corporate Tax", "Tax Compliance"], nice_to_have: ["DATEV", "Englisch"], status: "draft", priority: "normal", created_at: date(8), updated_at: date(0) },
];

export const demoGeoResults: GeoMappingResult[] = [
  { id: "geo-c-1", kind: "candidate", name: "Anna Weber", location: "70173 Stuttgart", postal_code: "70173", latitude: null, longitude: null, status: "active", tags: ["M&A Tax", "95k", "3 Monate"], mailing_ready: true },
  { id: "geo-c-5", kind: "candidate", name: "Lea Fischer", location: "60311 Frankfurt", postal_code: "60311", latitude: null, longitude: null, status: "active", tags: ["Corporate Tax", "Kurzprofil offen"], mailing_ready: true },
  { id: "geo-cl-1", kind: "client", name: "BlueTax Partners", location: "70173 Stuttgart", postal_code: "70173", latitude: null, longitude: null, status: "active", tags: ["Vertrag aktiv", "Tax Advisory"], mailing_ready: true },
  { id: "geo-cl-4", kind: "client", name: "Zollern Consulting", location: "72336 Balingen", postal_code: "72336", latitude: null, longitude: null, status: "blocked", tags: ["Do-not-touch"], mailing_ready: false },
];
