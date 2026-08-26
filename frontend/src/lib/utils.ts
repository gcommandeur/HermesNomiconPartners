import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";
import type { Abschlussart, Contact, Rechtsgebiet, Rolle } from "@/lib/api/types";

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

export function contactName(contact: Pick<Contact, "first_name" | "last_name"> | null | undefined) {
  if (!contact) return "Ansprechpartner offen";
  return `${contact.first_name} ${contact.last_name}`.trim();
}

export function formatDate(value?: string | null) {
  if (!value) return "–";
  return new Intl.DateTimeFormat("de-DE", {
    day: "2-digit",
    month: "short",
    year: "numeric",
  }).format(new Date(value));
}

export function formatDateTime(value?: string | null) {
  if (!value) return "–";
  return new Intl.DateTimeFormat("de-DE", {
    day: "2-digit",
    month: "short",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  }).format(new Date(value));
}

export function formatCurrency(value: number) {
  return new Intl.NumberFormat("de-DE", {
    style: "currency",
    currency: "EUR",
    maximumFractionDigits: 0,
  }).format(value);
}

// ClientCompany.terms_status ist backend-seitig ein freies String-Feld (kein
// DB-Enum) - "not_sent" ist bisher der einzige tatsächlich vorkommende Wert,
// aber die AGB-Statuspille im Frontend (clients-table.tsx) prüft bereits auf
// "accepted" als erwarteten künftigen Wert. Deckt den plausiblen AGB-Workflow
// ab (nicht versendet -> versendet -> akzeptiert/abgelehnt); unbekannte Werte
// fallen auf den Rohwert zurück statt "undefined" anzuzeigen.
const TERMS_STATUS_LABELS: Record<string, string> = {
  not_sent: "Nicht versendet",
  sent: "Versendet",
  accepted: "Akzeptiert",
  declined: "Abgelehnt",
};

export function termsStatusLabel(status?: string | null): string {
  if (!status) return TERMS_STATUS_LABELS.not_sent;
  return TERMS_STATUS_LABELS[status] ?? status;
}

// Feste 10 Zielrollen + "sonstige" (siehe Backend models/enums.py::Rolle) -
// ROLLE_OPTIONS haelt die Anzeige-Reihenfolge fest (fachliche Laufbahn-
// Stufen gruppiert: Steuer-/Bilanzbuchhaltung, dann Wirtschaftspruefung,
// dann Rechtsberatung, "sonstige" zuletzt), damit Filter-Dropdown und
// Badge-Listen ueberall gleich sortiert erscheinen statt in Insertions-
// Reihenfolge der jeweiligen candidate.rollen-Liste.
export const ROLLE_LABELS: Record<Rolle, string> = {
  steuerfachangestellte: "Steuerfachangestellte:r",
  steuerfachwirt: "Steuerfachwirt:in",
  bilanzbuchhalter: "Bilanzbuchhalter:in",
  steuerberater: "Steuerberater:in",
  partner: "Partner:in",
  pruefungsassistent: "Prüfungsassistent:in",
  pruefungsleiter: "Prüfungsleiter:in",
  wirtschaftspruefer: "Wirtschaftsprüfer:in",
  rechtsfachangestellte: "Rechtsfachangestellte:r",
  rechtsanwalt: "Rechtsanwält:in",
  sonstige: "Sonstige",
};

export const ROLLE_OPTIONS: Rolle[] = [
  "steuerfachangestellte",
  "steuerfachwirt",
  "bilanzbuchhalter",
  "steuerberater",
  "partner",
  "pruefungsassistent",
  "pruefungsleiter",
  "wirtschaftspruefer",
  "rechtsfachangestellte",
  "rechtsanwalt",
  "sonstige",
];

export function rolleLabel(value: Rolle): string {
  return ROLLE_LABELS[value] ?? value;
}

// Feste 9 Abschlussarten (siehe Backend models/enums.py::Abschlussart) -
// gleiches Anzeigemuster wie ROLLE_LABELS/ROLLE_OPTIONS/rolleLabel oben.
export const ABSCHLUSSART_LABELS: Record<Abschlussart, string> = {
  ausbildung: "Ausbildung",
  studium_bachelor: "Studium (Bachelor)",
  studium_master: "Studium (Master/Diplom)",
  studium_promotion: "Promotion",
  berufsexamen_stb: "Berufsexamen Steuerberater:in",
  berufsexamen_wp: "Berufsexamen Wirtschaftsprüfer:in",
  berufsexamen_ra: "Berufsexamen Rechtsanwalt/-anwältin",
  fortbildung: "Fortbildung",
  kein_abschluss_erkennbar: "Kein Abschluss erkennbar",
};

export const ABSCHLUSSART_OPTIONS: Abschlussart[] = [
  "ausbildung",
  "studium_bachelor",
  "studium_master",
  "studium_promotion",
  "berufsexamen_stb",
  "berufsexamen_wp",
  "berufsexamen_ra",
  "fortbildung",
  "kein_abschluss_erkennbar",
];

export function abschlussartLabel(value: Abschlussart): string {
  return ABSCHLUSSART_LABELS[value] ?? value;
}

// Feste 13 Rechtsgebiete (siehe Backend models/enums.py::Rechtsgebiet) - nur
// bei rechtsanwalt/rechtsfachangestellte inhaltlich relevant, aber
// kandidatenweit gefuehrt.
export const RECHTSGEBIET_LABELS: Record<Rechtsgebiet, string> = {
  arbeitsrecht: "Arbeitsrecht",
  steuerrecht: "Steuerrecht",
  gesellschaftsrecht: "Gesellschaftsrecht",
  handelsrecht: "Handelsrecht",
  vertragsrecht: "Vertragsrecht",
  familienrecht: "Familienrecht",
  erbrecht: "Erbrecht",
  insolvenzrecht: "Insolvenzrecht",
  immobilienrecht: "Immobilienrecht",
  ip_recht: "Gewerblicher Rechtsschutz",
  datenschutzrecht: "Datenschutzrecht",
  prozessrecht: "Prozessrecht",
  sonstiges: "Sonstiges",
};

export function rechtsgebietLabel(value: Rechtsgebiet): string {
  return RECHTSGEBIET_LABELS[value] ?? value;
}

// Feld-Keys aus Candidate.search_match_fields (siehe Backend
// repositories/candidates.py::compute_search_match_fields) -> Anzeige-Label
// fuer den "Treffer in: ..."-Hinweis in candidates-table.tsx (Punkt 5 des
// Freitextsuche-Auftrags: Nachvollziehbarkeit, warum ein Treffer gefunden
// wurde).
export const SEARCH_FIELD_LABELS: Record<string, string> = {
  first_name: "Vorname",
  last_name: "Nachname",
  email: "E-Mail",
  job_title: "Rolle",
  candidate_number: "Kandidatennummer",
  qualification: "Qualifikation",
  ausbildung_titel: "Ausbildung/Weiterbildung",
  current_employer_internal: "Aktueller Arbeitgeber",
  summary: "Zusammenfassung",
  fachliche_schwerpunkte: "Fachliche Schwerpunkte",
  edv_kenntnisse: "EDV-Kenntnisse",
  berufliche_stationen: "Berufliche Stationen",
};

export function searchFieldLabel(field: string): string {
  return SEARCH_FIELD_LABELS[field] ?? field;
}

// Feste Auswahl gaengiger Kuendigungsfrist-Kombinationen (Backend
// Candidate.notice_period bleibt bewusst String(160) Freitext - siehe
// models/candidate.py - keine Migration noetig, nur die UI wird
// eingeschraenkt). "sonstige" ist ein reiner UI-Sentinel-Wert, KEIN
// gueltiger notice_period-Wert selbst - waehlt der Nutzer ihn, klappt ein
// Freitextfeld auf, dessen Inhalt (nicht "sonstige") tatsaechlich
// gespeichert wird. Bestandswerte, die keiner Option hier exakt
// entsprechen, fallen beim Laden automatisch auf "sonstige" + Originaltext
// zurueck (siehe NoticePeriodField in candidate-create-modal.tsx) statt
// stillschweigend ueberschrieben zu werden.
export const NOTICE_PERIOD_OPTIONS: string[] = [
  "1 Monat zum Monatsende",
  "2 Monate zum Monatsende",
  "3 Monate zum Monatsende",
  "3 Monate zum Quartalsende",
  "4 Monate zum Quartalsende",
  "5 Monate zum Quartalsende",
  "6 Monate zum Quartalsende",
];

export const NOTICE_PERIOD_OTHER = "sonstige";
