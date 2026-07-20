import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";
import type { Contact } from "@/lib/api/types";

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
