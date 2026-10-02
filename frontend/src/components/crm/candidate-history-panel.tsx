import { STAGE_LABELS } from "@/lib/stage-labels";
import type { AuditLogEntry, SubmissionStatus } from "@/lib/api/types";

function isSubmissionStatus(value: unknown): value is SubmissionStatus {
  return typeof value === "string" && value in STAGE_LABELS;
}

function stageLabel(value: unknown): string {
  return isSubmissionStatus(value) ? STAGE_LABELS[value] : String(value ?? "?");
}

const FIELD_LABELS: Record<string, string> = {
  first_name: "Vorname",
  last_name: "Nachname",
  email: "E-Mail",
  phone: "Telefon",
  city: "Ort",
  postal_code: "PLZ",
  job_title: "Jobtitel",
  salary_expectation: "Gehalt",
  notice_period: "Kündigungsfrist",
  status: "Status",
  next_step: "Nächster Schritt",
  summary: "Zusammenfassung",
  short_profile: "Kurzprofil",
  owner_user_id: "Verantwortliche/r",
};

function shortValue(value: unknown): string {
  if (value === null || value === undefined || value === "") return "—";
  const text = Array.isArray(value) ? value.join(", ") : String(value);
  return text.length > 40 ? `${text.slice(0, 40)}…` : text;
}

/** "Telefon: 0711 1 → 0711 2, Ort: Stuttgart → Esslingen" - nur die im
 * AuditLog-Eintrag "updated" tatsaechlich geaenderten Felder. */
function describeChanges(entry: AuditLogEntry): string {
  const keys = Object.keys(entry.new_values ?? {});
  if (keys.length === 0) return "";
  const shown = keys.slice(0, 3).map((key) => {
    const label = FIELD_LABELS[key] ?? key.replace(/_/g, " ");
    return `${label}: ${shortValue(entry.old_values?.[key])} → ${shortValue(entry.new_values?.[key])}`;
  });
  return keys.length > 3 ? `${shown.join(", ")} (+${keys.length - 3} weitere)` : shown.join(", ");
}

/** Ereignisse, die seit der Autorenerfassung IMMER einen Nutzer tragen - ein
 * fehlender Wert heisst hier "aus der Zeit davor", nicht "automatisch". */
export const AUTHORED_EVENT_ACTIONS = new Set([
  "interview_scheduled",
  "offer_received",
  "placement_created",
  "fee_calculated",
  "feedback_received",
]);

/** Uebersetzt einen AuditLog-Eintrag in verstaendliches Deutsch statt eines
 * Roh-JSON-Diffs (Nutzer-Vorgabe: "Stufe geändert: CV IN → CV OUT" statt
 * altValues/newValues). Ein unbekannter action/entity_type-Wert faellt auf
 * einen generischen, aber weiterhin lesbaren Text zurueck statt zu crashen
 * (kuenftige, hier noch nicht abgedeckte Aktionen sollen sichtbar bleiben,
 * nicht verschwinden). Einzige Uebersetzungsstelle - auch von der
 * vereinheitlichten Timeline (candidate-timeline.tsx) genutzt. */
export function describeEntry(entry: AuditLogEntry): string {
  if (entry.entity_type === "candidate_submission" && entry.action === "status_changed") {
    const from = stageLabel(entry.old_values?.status);
    const to = stageLabel(entry.new_values?.status);
    return `Stufe geändert: ${from} → ${to}`;
  }
  if (entry.entity_type === "candidate_submission" && entry.action === "archived") {
    return "Prozess abgeschlossen (aus dem Kanban entfernt)";
  }
  if (entry.entity_type === "candidate_submission" && entry.action === "unarchived") {
    return "Abschluss des Prozesses zurückgenommen";
  }
  if (entry.entity_type === "candidate_submission" && entry.action === "deleted") {
    return "Prozess gelöscht";
  }
  if (entry.entity_type === "candidate_submission" && entry.action === "interview_scheduled") {
    return "Interview angelegt";
  }
  if (entry.entity_type === "candidate_submission" && entry.action === "offer_received") {
    return "Offer erfasst";
  }
  if (entry.entity_type === "candidate_submission" && entry.action === "placement_created") {
    return "Placement angelegt";
  }
  if (entry.entity_type === "candidate_submission" && entry.action === "fee_calculated") {
    return "Fee berechnet";
  }
  if (entry.entity_type === "candidate_submission" && entry.action === "feedback_received") {
    return "Feedback erfasst";
  }
  if (entry.entity_type === "candidate" && entry.action === "deleted") {
    return "Kandidat gelöscht";
  }
  if (entry.entity_type === "candidate" && entry.action === "anonymized") {
    return "Kandidat anonymisiert (DSGVO)";
  }
  // Titelschutz-Korrektur Schritt 2 (Markieren statt Aendern).
  if (entry.entity_type === "candidate" && entry.action === "rollen_bestaetigt") {
    return "Titel bestätigt (nach Prüfung)";
  }
  if (entry.entity_type === "candidate" && entry.action === "rollen_korrigiert") {
    const from = (entry.old_values?.rollen as string[] | undefined)?.join(", ") || "—";
    const to = (entry.new_values?.rollen as string[] | undefined)?.join(", ") || "—";
    return `Rolle korrigiert (Titel war unbestätigt): ${from} → ${to}`;
  }
  // Normale Feld-Edits (AuditLog "updated", siehe Backend services/audit_diff.py).
  if (entry.action === "updated") {
    const subject = entry.entity_type === "candidate" ? "Kandidat bearbeitet" : "Prozess bearbeitet";
    const changes = describeChanges(entry);
    return changes ? `${subject}: ${changes}` : subject;
  }
  // Generischer Rueckfall - macht die Aktion lesbar sichtbar statt sie zu
  // verwerfen, auch wenn sie hier noch nicht explizit uebersetzt ist.
  const entityLabel = entry.entity_type === "candidate" ? "Kandidat" : "Prozess";
  return `${entityLabel}: ${entry.action.replace(/_/g, " ")}`;
}
