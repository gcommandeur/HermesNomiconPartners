// NOMICON: Kundenfreigabe von Stundenzetteln (öffentlich, ohne Login) - Aufrufe im Browser.
// Gehen über /api/stundenzettel (eigene, schmale Weiterleitung), nie über den Login-Proxy.
import type { PublicTimesheet } from "./staffing";

export type PublicLinkErrorKind = "invalid" | "expired" | "rate_limited" | "network" | "validation";

export class PublicLinkError extends Error {
  constructor(
    public readonly kind: PublicLinkErrorKind,
    message: string,
  ) {
    super(message);
  }
}

const MESSAGES: Record<PublicLinkErrorKind, string> = {
  invalid: "Dieser Link ist ungültig. Bitte den Link aus der E-Mail vollständig verwenden.",
  expired: "Dieser Link ist abgelaufen oder wurde bereits verwendet. Bitte beim Dienstleister einen neuen Link anfordern.",
  rate_limited: "Zu viele ungültige Versuche. Bitte in ein paar Minuten erneut versuchen.",
  network: "Der Dienst ist gerade nicht erreichbar. Bitte später erneut versuchen.",
  validation: "Bitte Name (mindestens 2 Zeichen) und - bei Ablehnung - eine Begründung angeben.",
};

async function call(path: string, init?: RequestInit): Promise<PublicTimesheet> {
  let response: Response;
  try {
    response = await fetch(`/api/stundenzettel/${path}`, { ...init, cache: "no-store", headers: { Accept: "application/json", ...(init?.headers ?? {}) } });
  } catch {
    throw new PublicLinkError("network", MESSAGES.network);
  }
  if (response.ok) return (await response.json()) as PublicTimesheet;
  if (response.status === 404) throw new PublicLinkError("invalid", MESSAGES.invalid);
  if (response.status === 410) throw new PublicLinkError("expired", MESSAGES.expired);
  if (response.status === 429) throw new PublicLinkError("rate_limited", MESSAGES.rate_limited);
  if (response.status === 422) {
    // Eingabefehler (z. B. Name zu kurz): die Meldung des Servers ist für Kunden nicht lesbar.
    throw new PublicLinkError("validation", MESSAGES.validation);
  }
  throw new PublicLinkError("network", MESSAGES.network);
}

export function getPublicTimesheet(token: string) {
  return call(encodeURIComponent(token));
}

export function approvePublicTimesheet(token: string, approverName: string) {
  return call(`${encodeURIComponent(token)}/approve`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ approver_name: approverName }),
  });
}

export function rejectPublicTimesheet(token: string, approverName: string, reason: string) {
  return call(`${encodeURIComponent(token)}/reject`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ approver_name: approverName, reason }),
  });
}
