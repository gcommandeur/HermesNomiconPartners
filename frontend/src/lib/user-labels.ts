import type { UserBrief } from "@/lib/api/types";

/** Anzeigename (Fallback E-Mail) von Nutzern, nachgeschlagen per ID oder per
 * E-Mail - AuditLog.changed_by und Feedback.created_by speichern die E-Mail
 * als Text, Activity.sent_by_user_id/Note.created_by_user_id die ID. Ein
 * unbekannter Wert (z.B. ein inzwischen deaktivierter Nutzer oder ein frei
 * getippter Alt-Name) wird unveraendert zurueckgegeben, nie verschluckt. */
export function createUserLabels(users: UserBrief[]) {
  const byId = new Map(users.map((user) => [user.id, user.display_name || user.email]));
  const byEmail = new Map(users.map((user) => [user.email.toLowerCase(), user.display_name || user.email]));
  return {
    byId: (id: string | null | undefined): string | null => (id ? (byId.get(id) ?? null) : null),
    byEmail: (email: string | null | undefined): string | null =>
      email ? (byEmail.get(email.toLowerCase()) ?? email) : null,
  };
}
