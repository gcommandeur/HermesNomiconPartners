// NOMICON: Überlassung - wer was sieht (reine Funktion, passend zum Server: `require_compliance_access`).
// Compliance (Erlaubnis, Fristen-Einstellungen, Übernahme-Staffel) und die ausführlichen Tabellen
// sehen nur Admins und Teamleiter; Vermittler sehen "Meine Einsätze" und "Meine nächsten Schritte".

export interface RoleInfo {
  is_admin?: boolean;
  role?: string;
}

export function canSeeCompliance(user: RoleInfo | null | undefined): boolean {
  return Boolean(user && (user.is_admin || user.role === "admin" || user.role === "team_lead"));
}
