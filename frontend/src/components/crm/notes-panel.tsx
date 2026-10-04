"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { StickyNote } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { ErrorBanner } from "@/components/crm/error-banner";
import { createNote } from "@/lib/api/queries";
import type { Note } from "@/lib/api/types";
import { formatDate } from "@/lib/utils";

const textareaClass = "min-h-48 w-full rounded-md border border-white/10 bg-brand-surface p-3 text-sm text-brand-text outline-none focus:border-brand-accent";

// Vorbereiteter Entwurf fuer ein Quali-Call-Gespraech - fuellt die
// wichtigsten Eckdaten-Ueberschriften vor, statt mit einem leeren Textfeld
// zu starten (gleiches Prinzip wie QUALIFICATION_CALL_TEMPLATE in
// feedback-panel.tsx, dort an den Prozess-Feedback-Eintrag gebunden - hier
// bewusst als freie Notiz, unabhaengig von einem laufenden Prozess).
const QUALI_CALL_NOTE_TEMPLATE =
  "Ort: \nAusbildung: \nGehalt: \nKündigungsfrist/Verfügbarkeit: \n\nErfahrungen: \n\nWechselmotivation: \n\nEDV: ";

/** Freier, nicht prozessgebundener Notizen-Tab am Kandidaten (Phase 1b) -
 * nutzt das bestehende Note-Modell/API mit candidate_submission_id == null
 * (siehe queries.ts::getNotesForCandidate/createNote), anders als die
 * bestehende Prozess-Timeline (candidate-process-log.tsx), die immer an
 * einen Recruiting-Prozess/-Stufe gebunden ist. */
export function NotesPanel({ candidateId, initialNotes }: { candidateId: string; initialNotes: Note[] }) {
  const router = useRouter();
  const [notes, setNotes] = useState(initialNotes);
  const [body, setBody] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  function handleInsertQualiCallTemplate() {
    setBody((current) =>
      current.trim() ? `${current}\n\n${QUALI_CALL_NOTE_TEMPLATE}` : QUALI_CALL_NOTE_TEMPLATE,
    );
  }

  async function handleSubmit(event: React.FormEvent) {
    event.preventDefault();
    if (!body.trim()) {
      setError("Bitte einen Text eingeben.");
      return;
    }
    setBusy(true);
    setError(null);
    try {
      const created = await createNote({ candidate_id: candidateId, body: body.trim() });
      setNotes((current) => [created, ...current]);
      setBody("");
      // Timeline-Tab (Server Component) zeigt die neue Notiz sonst erst nach
      // einem Neuladen.
      router.refresh();
    } catch (exception) {
      setError(exception instanceof Error ? exception.message : "Notiz konnte nicht gespeichert werden.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="space-y-4">
      <Card>
        <CardContent>
          <form className="space-y-3" onSubmit={handleSubmit}>
            <ErrorBanner message={error} />
            <textarea
              className={textareaClass}
              placeholder="Neue Notiz…"
              value={body}
              onChange={(event) => setBody(event.target.value)}
            />
            <div className="flex justify-between gap-2">
              <Button type="button" size="sm" variant="outline" onClick={handleInsertQualiCallTemplate}>
                Quali-Call-Entwurf einfügen
              </Button>
              <Button type="submit" size="sm" disabled={busy}>
                {busy ? "Speichert…" : "Speichern"}
              </Button>
            </div>
          </form>
        </CardContent>
      </Card>
      <div className="space-y-2">
        {notes.map((note) => (
          <Card key={note.id}>
            <CardContent className="flex items-start gap-3">
              <span className="mt-0.5 grid size-8 shrink-0 place-items-center rounded-full bg-brand-accent-soft text-brand-platinum">
                <StickyNote size={14} />
              </span>
              <div className="min-w-0 flex-1">
                <p className="whitespace-pre-wrap text-sm text-brand-platinum">{note.body}</p>
                <span className="mt-2 inline-block text-xs text-brand-gray">
                  {formatDate(note.created_at)} ·{" "}
                  {note.created_by_name ?? (
                    <span title="Alt-Notiz oder automatisch erzeugt - kein Autor erfasst">Unbekannt</span>
                  )}
                </span>
              </div>
            </CardContent>
          </Card>
        ))}
        {notes.length === 0 && (
          <Card>
            <CardContent className="py-12 text-center text-sm text-brand-gray">
              Noch keine Notizen für diesen Kandidaten.
            </CardContent>
          </Card>
        )}
      </div>
    </div>
  );
}
