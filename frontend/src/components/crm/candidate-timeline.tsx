import { Clock3, History, MessageSquare, StickyNote } from "lucide-react";
import type { ReactNode } from "react";
import { Card, CardContent } from "@/components/ui/card";
import { AUTHORED_EVENT_ACTIONS, describeEntry } from "@/components/crm/candidate-history-panel";
import { STAGE_LABELS } from "@/lib/stage-labels";
import { createUserLabels } from "@/lib/user-labels";
import { formatDateTime } from "@/lib/utils";
import type { Activity, AuditLogEntry, CandidateComment, UserBrief } from "@/lib/api/types";

// Activities, die einen AuditLog-Zwilling haben (jede Statusaenderung und jedes
// Interview/Offer/Placement/Fee/Feedback schreibt BEIDES, siehe Backend
// services/submissions.py::transition und services/recruiting.py::_event) -
// der AuditLog-Eintrag traegt zusaetzlich den Urheber, die Activity wuerde
// dasselbe Ereignis nur ein zweites Mal ohne Autor zeigen (z.B. jedes CV-Out
// doppelt). Aktivitaeten OHNE Zwilling (Mails, Anrufe, "Prozess angelegt", ...)
// bleiben in der Liste.
const DUPLICATED_ACTIVITY_TYPES = new Set([
  "submission_status_changed",
  "feedback_received",
  "interview_scheduled",
  "offer_received",
  "placement_created",
  "fee_calculated",
]);

// Der Feedback-Text steht als eigener Kommentar-Eintrag (mit Stufe und
// Autor) in der Liste - der zugehoerige AuditLog-Eintrag waere ein Duplikat.
const DUPLICATED_AUDIT_ACTIONS = new Set(["feedback_received"]);

interface TimelineItem {
  key: string;
  at: string;
  kind: string;
  icon: ReactNode;
  text: string;
  detail?: string | null;
  author: ReactNode;
}

const unknownAuthor = (
  <span title="Aus der Zeit vor der Autorenerfassung - kein Nutzer gespeichert">Unbekannt</span>
);
const automaticAuthor = (
  <span className="text-brand-accent-light" title="Automatisch ausgelöst, keinem Nutzer zugeordnet">
    Automatisch
  </span>
);

function timestamp(value: string): number {
  const parsed = new Date(value).getTime();
  return Number.isNaN(parsed) ? 0 : parsed;
}

/** EINE chronologische Liste aller Ereignisse zu einem Kandidaten - Statuswechsel
 * und Aenderungen (AuditLog), Aktivitaeten, Notizen und Prozess-Feedback -
 * jeweils mit Zeitpunkt, Text und Urheber. Ersetzt die beiden vorherigen,
 * getrennt uebereinandergestapelten Bloecke (Aenderungshistorie + Aktivitaeten).
 *
 * Zusammengefuehrt im Frontend (statt eines eigenen Backend-Endpunkts):
 * Aenderungshistorie, Aktivitaeten und Notizen werden fuer die Seite ohnehin
 * schon geladen; neu hinzu kommt nur GET /candidates/{id}/comments fuer die
 * Kommentare, die als einziges prozessuebergreifend (auch bei Prozessen von
 * Kollegen) sichtbar sein muessen. */
export function CandidateTimeline({
  history,
  activities,
  comments,
  users,
}: {
  history: AuditLogEntry[];
  activities: Activity[];
  comments: CandidateComment[];
  users: UserBrief[];
}) {
  const labels = createUserLabels(users);
  const items: TimelineItem[] = [];

  for (const entry of history) {
    if (DUPLICATED_AUDIT_ACTIONS.has(entry.action)) continue;
    const author = labels.byEmail(entry.changed_by);
    items.push({
      key: `audit-${entry.id}`,
      at: entry.changed_at,
      kind: "Änderung",
      icon: <History size={14} />,
      text: describeEntry(entry),
      author: author ?? (AUTHORED_EVENT_ACTIONS.has(entry.action) ? unknownAuthor : automaticAuthor),
    });
  }

  for (const activity of activities) {
    if (DUPLICATED_ACTIVITY_TYPES.has(activity.activity_type)) continue;
    items.push({
      key: `activity-${activity.id}`,
      at: activity.occurred_at,
      kind: activity.activity_type.replace(/_/g, " "),
      icon: <Clock3 size={14} />,
      text: activity.subject,
      detail: activity.details,
      author: labels.byId(activity.sent_by_user_id) ?? null,
    });
  }

  for (const comment of comments) {
    const author = comment.author ?? unknownAuthor;
    if (comment.kind === "note") {
      items.push({
        key: `note-${comment.id}`,
        at: comment.occurred_at,
        kind: "Notiz",
        icon: <StickyNote size={14} />,
        text: comment.text,
        author,
      });
    } else {
      items.push({
        key: `feedback-${comment.id}`,
        at: comment.occurred_at,
        kind: comment.stage ? `Feedback · ${STAGE_LABELS[comment.stage] ?? comment.stage}` : "Feedback",
        icon: <MessageSquare size={14} />,
        text: comment.text,
        author,
      });
    }
  }

  items.sort((a, b) => timestamp(b.at) - timestamp(a.at));

  if (items.length === 0) {
    return (
      <Card>
        <CardContent className="py-12 text-center text-sm text-brand-gray">
          Noch keine Ereignisse für diesen Kandidaten.
        </CardContent>
      </Card>
    );
  }

  return (
    <div className="space-y-2">
      {items.map((item) => (
        <Card key={item.key}>
          <CardContent className="flex items-start gap-3">
            <span className="mt-0.5 grid size-8 shrink-0 place-items-center rounded-full bg-brand-accent-soft text-brand-platinum">
              {item.icon}
            </span>
            <div className="min-w-0 flex-1">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <p className="whitespace-pre-wrap text-sm font-semibold text-brand-text">{item.text}</p>
                <span className="text-xs text-brand-gray">{formatDateTime(item.at)}</span>
              </div>
              {item.detail && <p className="mt-1 text-xs text-brand-muted">{item.detail}</p>}
              <div className="mt-2 flex flex-wrap items-center gap-2">
                <span className="inline-block rounded bg-brand-panel px-2 py-0.5 text-[9.5px] uppercase tracking-wider text-brand-muted">
                  {item.kind}
                </span>
                {item.author && <span className="text-xs text-brand-soft">von {item.author}</span>}
              </div>
            </div>
          </CardContent>
        </Card>
      ))}
    </div>
  );
}
