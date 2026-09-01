"use client";

import { History } from "lucide-react";
import { Card, CardContent } from "@/components/ui/card";
import { STAGE_LABELS } from "@/components/crm/submission-stage-bar";
import { formatDate } from "@/lib/utils";
import type { AuditLogEntry, SubmissionStatus } from "@/lib/api/types";

function isSubmissionStatus(value: unknown): value is SubmissionStatus {
  return typeof value === "string" && value in STAGE_LABELS;
}

function stageLabel(value: unknown): string {
  return isSubmissionStatus(value) ? STAGE_LABELS[value] : String(value ?? "?");
}

/** Uebersetzt einen AuditLog-Eintrag in verstaendliches Deutsch statt eines
 * Roh-JSON-Diffs (Nutzer-Vorgabe: "Stufe geändert: CV IN → CV OUT" statt
 * altValues/newValues). Nur die Faelle, die tatsaechlich vorkommen (siehe
 * Backend services/candidates.py::CandidateService.history) - ein
 * unbekannter action/entity_type-Wert faellt auf einen generischen, aber
 * weiterhin lesbaren Text zurueck statt zu crashen (kuenftige, hier noch
 * nicht abgedeckte Aktionen sollen sichtbar bleiben, nicht verschwinden). */
function describeEntry(entry: AuditLogEntry): string {
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
  // Generischer Rueckfall - macht die Aktion lesbar sichtbar statt sie zu
  // verwerfen, auch wenn sie hier noch nicht explizit uebersetzt ist.
  const entityLabel = entry.entity_type === "candidate" ? "Kandidat" : "Prozess";
  return `${entityLabel}: ${entry.action.replace(/_/g, " ")}`;
}

export function CandidateHistoryPanel({ entries }: { entries: AuditLogEntry[] }) {
  if (entries.length === 0) return null;

  return (
    <div className="mb-6 space-y-2">
      <p className="flex items-center gap-2 text-xs font-semibold uppercase tracking-wider text-[#94A3B8]">
        <History size={13} />Änderungshistorie
      </p>
      <div className="space-y-1.5">
        {entries.map((entry) => (
          <Card key={entry.id}>
            <CardContent className="flex flex-wrap items-center justify-between gap-2 py-2.5">
              <p className="text-xs text-[#D8DADF]">{describeEntry(entry)}</p>
              <p className="text-[10px] text-[#8b9196]">
                {formatDate(entry.changed_at)} ·{" "}
                {entry.changed_by ?? (
                  <span className="text-[#69A7EA]" title="Automatisch ausgelöst, keinem Nutzer zugeordnet">
                    Automatisch
                  </span>
                )}
              </p>
            </CardContent>
          </Card>
        ))}
      </div>
    </div>
  );
}
