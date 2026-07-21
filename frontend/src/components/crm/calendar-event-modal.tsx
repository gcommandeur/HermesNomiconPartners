"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { Link2 } from "lucide-react";
import { Modal } from "@/components/ui/modal";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { SearchSelect } from "@/components/ui/search-select";
import { ErrorBanner } from "@/components/crm/error-banner";
import { apiDelete, apiPatch, apiPost } from "@/lib/api/client";
import { searchCandidates, searchClients } from "@/lib/api/search-select-helpers";
import { getSubmissions } from "@/lib/api/queries";
import { formatDate } from "@/lib/utils";
import type { AdminUser, CalendarEvent, CalendarEventType } from "@/lib/api/types";

const labelClass = "mb-1 block text-xs text-[#94A3B8]";
const textareaClass = "min-h-20 w-full rounded-md border border-white/10 bg-[#0D1B2E] p-3 text-sm text-[#F8FAFC] outline-none focus:border-[#1F5FA8]";
const selectClass = "h-10 w-full rounded-md border border-white/10 bg-[#0D1B2E] px-3 text-sm text-[#F8FAFC] outline-none focus:border-[#1F5FA8]";

const EVENT_TYPE_OPTIONS: { value: CalendarEventType; label: string }[] = [
  { value: "interview", label: "Interview" },
  { value: "quali_call", label: "Quali Call" },
  { value: "other", label: "Sonstiges" },
];

/** ISO-Datetime aus dem Backend (z.B. "2026-08-05T14:00:00") direkt auf die
 * ersten 16 Zeichen kuerzen statt ueber ein Date-Objekt zu gehen - vermeidet
 * eine Zeitzonen-Reinterpretation durch JS (siehe Backend-Kommentar in
 * services/ics_feed.py: alle Zeiten werden als feste Europe/Berlin-
 * Wanduhrzeit behandelt, kein Umrechnen). */
function toDatetimeLocalValue(iso: string | null | undefined): string {
  if (!iso) return "";
  return iso.slice(0, 16);
}

interface FormState {
  title: string;
  event_type: CalendarEventType;
  start_at: string;
  end_at: string;
  location: string;
  notes: string;
  candidate_id: string;
  client_company_id: string;
  candidate_submission_id: string;
  reminder_minutes_before: string;
  owner_user_id: string;
}

function emptyForm(defaultStart: string, ownerUserId: string): FormState {
  return {
    title: "",
    event_type: "other",
    start_at: defaultStart,
    end_at: "",
    location: "",
    notes: "",
    candidate_id: "",
    client_company_id: "",
    candidate_submission_id: "",
    reminder_minutes_before: "30",
    owner_user_id: ownerUserId,
  };
}

export function CalendarEventModal({
  event,
  defaultStart,
  currentUserId,
  isAdmin,
  adminUsers,
  onClose,
  onSaved,
  onDeleted,
}: {
  /** null = neuen Termin anlegen, sonst bearbeiten. */
  event: CalendarEvent | null;
  /** Vorbelegter Start (z.B. angeklickter Kalendertag) - nur beim Neuanlegen relevant. */
  defaultStart?: string;
  currentUserId: string;
  isAdmin: boolean;
  /** Nur befuellt, wenn isAdmin - fuer die Owner-Auswahl. */
  adminUsers: AdminUser[];
  onClose: () => void;
  onSaved: () => void;
  onDeleted: () => void;
}) {
  const [form, setForm] = useState<FormState>(() =>
    event
      ? {
          title: event.title,
          event_type: event.event_type,
          start_at: toDatetimeLocalValue(event.start_at),
          end_at: toDatetimeLocalValue(event.end_at),
          location: event.location ?? "",
          notes: event.notes ?? "",
          candidate_id: event.candidate_id ?? "",
          client_company_id: event.client_company_id ?? "",
          candidate_submission_id: event.candidate_submission_id ?? "",
          reminder_minutes_before: String(event.reminder_minutes_before),
          owner_user_id: event.owner_user_id,
        }
      : emptyForm(defaultStart ?? "", currentUserId),
  );
  const [submissionOptions, setSubmissionOptions] = useState<
    { value: string; label: string; sublabel?: string }[]
  >([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  function set<K extends keyof FormState>(key: K, value: FormState[K]) {
    setForm((current) => ({ ...current, [key]: value }));
  }

  // Prozess-Auswahl: nur Prozesse des gewaehlten Kandidaten (optional
  // zusaetzlich auf die gewaehlte Kanzlei eingegrenzt) - eine serverseitige
  // Suche wie bei Kandidat/Kanzlei lohnt sich hier nicht (Prozesse sind ein
  // kleiner, bereits komplett geladener Bestand, siehe fetchAllPages-Hinweis
  // in lib/api/queries.ts), daher client-seitige Filterung der vollen Liste.
  useEffect(() => {
    if (!form.candidate_id) {
      setSubmissionOptions([]);
      return;
    }
    let cancelled = false;
    getSubmissions().then((result) => {
      if (cancelled) return;
      const matches = result.data.filter(
        (submission) =>
          submission.candidate_id === form.candidate_id &&
          (!form.client_company_id || submission.client_company_id === form.client_company_id),
      );
      setSubmissionOptions(
        matches.map((submission) => ({
          value: submission.id,
          label: `${submission.status} · ${submission.submitted_at ? formatDate(submission.submitted_at) : "Datum offen"}`,
          sublabel: submission.summary ?? undefined,
        })),
      );
    });
    return () => {
      cancelled = true;
    };
  }, [form.candidate_id, form.client_company_id]);

  async function handleSubmit(formEvent: React.FormEvent) {
    formEvent.preventDefault();
    setBusy(true);
    setError(null);
    try {
      if (!form.title.trim()) throw new Error("Bitte einen Titel angeben.");
      if (!form.start_at) throw new Error("Bitte einen Start-Zeitpunkt angeben.");

      const payload = {
        title: form.title.trim(),
        event_type: form.event_type,
        start_at: form.start_at,
        end_at: form.end_at || null,
        location: form.location.trim() || null,
        notes: form.notes.trim() || null,
        candidate_id: form.candidate_id || null,
        client_company_id: form.client_company_id || null,
        candidate_submission_id: form.candidate_submission_id || null,
        reminder_minutes_before: Number(form.reminder_minutes_before) || 0,
        ...(isAdmin ? { owner_user_id: form.owner_user_id || currentUserId } : {}),
      };

      if (event) {
        await apiPatch(`/calendar-events/${event.id}`, payload);
      } else {
        await apiPost("/calendar-events", payload);
      }
      onSaved();
    } catch (exception) {
      setError(exception instanceof Error ? exception.message : "Termin konnte nicht gespeichert werden.");
    } finally {
      setBusy(false);
    }
  }

  async function handleDelete() {
    if (!event) return;
    setBusy(true);
    setError(null);
    try {
      await apiDelete(`/calendar-events/${event.id}`);
      onDeleted();
    } catch (exception) {
      setError(exception instanceof Error ? exception.message : "Termin konnte nicht gelöscht werden.");
      setBusy(false);
    }
  }

  return (
    <Modal
      title={event ? "Termin bearbeiten" : "Termin anlegen"}
      eyebrow="Kalender"
      onClose={onClose}
    >
      <form className="space-y-4" onSubmit={handleSubmit}>
        {event?.source_interview_id && (
          <div className="flex items-center gap-2 rounded-lg border border-[#1F5FA8]/30 bg-[#1F5FA8]/10 p-2.5 text-xs text-[#c5dcfa]">
            <Link2 size={13} className="shrink-0" />
            <span>Automatisch aus Interview verknüpft.</span>
            {event.candidate_id && (
              <Link href={`/kandidaten/${event.candidate_id}`} className="ml-auto underline hover:text-white">
                Zum Prozess
              </Link>
            )}
          </div>
        )}
        <div>
          <label className={labelClass}>Titel *</label>
          <Input required value={form.title} onChange={(e) => set("title", e.target.value)} />
        </div>
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
          <div>
            <label className={labelClass}>Typ</label>
            <select
              className={selectClass}
              value={form.event_type}
              onChange={(e) => set("event_type", e.target.value as CalendarEventType)}
            >
              {EVENT_TYPE_OPTIONS.map((option) => (
                <option key={option.value} value={option.value}>{option.label}</option>
              ))}
            </select>
          </div>
          <div>
            <label className={labelClass}>Erinnerung (Minuten vorher)</label>
            <Input
              type="number"
              min={0}
              value={form.reminder_minutes_before}
              onChange={(e) => set("reminder_minutes_before", e.target.value)}
            />
          </div>
        </div>
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
          <div>
            <label className={labelClass}>Start *</label>
            <Input
              type="datetime-local"
              required
              value={form.start_at}
              onChange={(e) => set("start_at", e.target.value)}
            />
          </div>
          <div>
            <label className={labelClass}>Ende (optional)</label>
            <Input
              type="datetime-local"
              value={form.end_at}
              onChange={(e) => set("end_at", e.target.value)}
            />
          </div>
        </div>
        <div>
          <label className={labelClass}>Ort (optional)</label>
          <Input value={form.location} onChange={(e) => set("location", e.target.value)} />
        </div>

        {isAdmin && (
          <div>
            <label className={labelClass}>Für wen (Owner)</label>
            <select
              className={selectClass}
              value={form.owner_user_id}
              onChange={(e) => set("owner_user_id", e.target.value)}
            >
              {adminUsers.map((user) => (
                <option key={user.id} value={user.id}>
                  {user.display_name ?? user.email}
                </option>
              ))}
            </select>
          </div>
        )}

        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
          <div>
            <label className={labelClass}>Kandidat (optional)</label>
            <SearchSelect
              onSearch={searchCandidates}
              value={form.candidate_id}
              onChange={(value) => {
                set("candidate_id", value);
                set("candidate_submission_id", "");
              }}
              placeholder="Kandidat suchen…"
              emptyLabel="Kein Kandidat gefunden"
              clearLabel="Kein Kandidat"
            />
          </div>
          <div>
            <label className={labelClass}>Kanzlei (optional)</label>
            <SearchSelect
              onSearch={searchClients}
              value={form.client_company_id}
              onChange={(value) => {
                set("client_company_id", value);
                set("candidate_submission_id", "");
              }}
              placeholder="Kanzlei suchen…"
              emptyLabel="Keine Kanzlei gefunden"
              clearLabel="Keine Kanzlei"
            />
          </div>
        </div>

        {form.candidate_id && (
          <div>
            <label className={labelClass}>Verknüpfter Prozess (optional)</label>
            <SearchSelect
              options={submissionOptions}
              value={form.candidate_submission_id}
              onChange={(value) => set("candidate_submission_id", value)}
              placeholder="Prozess wählen…"
              emptyLabel="Kein passender Prozess gefunden"
              clearLabel="Kein Prozess"
            />
          </div>
        )}

        <div>
          <label className={labelClass}>Notiz (optional)</label>
          <textarea className={textareaClass} value={form.notes} onChange={(e) => set("notes", e.target.value)} />
        </div>

        <ErrorBanner message={error} />
        <div className="flex items-center justify-between gap-2">
          {event ? (
            <Button type="button" variant="outline" disabled={busy} onClick={handleDelete}>
              Löschen
            </Button>
          ) : <span />}
          <div className="flex gap-2">
            <Button type="button" variant="outline" onClick={onClose}>Abbrechen</Button>
            <Button type="submit" disabled={busy}>{busy ? "Speichern…" : "Speichern"}</Button>
          </div>
        </div>
      </form>
    </Modal>
  );
}
