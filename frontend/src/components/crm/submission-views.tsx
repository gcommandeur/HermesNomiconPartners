"use client";

import { useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import { Archive, ArchiveRestore, Ban, Building2, CalendarPlus, ChevronDown, Columns3, Download, Eye, List, ShieldAlert, X } from "lucide-react";
import type {
  Candidate,
  CandidateSubmission,
  ClientCompany,
  Contact,
  Interview,
  SubmissionCancellationReason,
  SubmissionStatus,
} from "@/lib/api/types";
import { StatusPill } from "./status-pill";
import { STAGE_LABELS } from "@/components/crm/submission-stage-bar";
import { DataTable } from "./data-table";
import { FilterBar } from "@/components/crm/filter-bar";
import { ExportActions, downloadCsv } from "@/components/crm/export-actions";
import { InterviewModal } from "@/components/crm/interview-modal";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { apiDelete, apiPatch } from "@/lib/api/client";
import { archiveSubmission, unarchiveSubmission } from "@/lib/api/queries";
import { useCurrentUser } from "@/lib/api/hooks";
import { useInterviewMutations } from "@/lib/use-interview-mutations";
import { formatTimeFromIso, toLocalIsoString } from "@/lib/calendar-utils";
import { allowedTransitions } from "@/lib/submission-transitions";
import { cn, contactName as formatContactName, formatDate } from "@/lib/utils";
import { CandidateQuickViewDrawer } from "./candidate-quickview-drawer";
import { ClosingScoreForm } from "./closing-score-form";

const closingStatusTone = { hot: "green", warm: "amber", risk: "blue", stop: "red" } as const;
const closingStatusLabel = { hot: "Hot", warm: "Warm", risk: "Risk", stop: "Stop" } as const;

function ClosingScoreBadge({ status, probability }: { status: CandidateSubmission["closing_status"]; probability?: number | null }) {
  if (!status) return null;
  return <Badge tone={closingStatusTone[status]}>{closingStatusLabel[status]}{probability != null ? ` ${probability}%` : ""}</Badge>;
}

const columns: { status: SubmissionStatus; title: string }[] = [
  { status: "qualification_call", title: "Quali Call" },
  { status: "cv_in", title: "CV IN" },
  { status: "cv_out", title: "CV OUT" },
  { status: "interview", title: "Interview" },
  { status: "offer", title: "Offer" },
  { status: "placement", title: "Placement" },
];

const CANCELLATION_REASONS: { value: SubmissionCancellationReason; label: string }[] = [
  { value: "candidate_rejected", label: "Absage Kandidat" },
  { value: "client_rejected", label: "Absage Kanzlei" },
  { value: "candidate_ghosting", label: "Ghosting Kandidat" },
];

function isHot(status: SubmissionStatus) {
  return ["interview", "offer", "placement"].includes(status);
}

/** scheduled_at ist eine naive Europe/Berlin-Wanduhrzeit ohne verlaessliches
 * Zeitzonen-Suffix (auf SQLite ganz ohne Suffix, auf Postgres theoretisch mit
 * einem - siehe services/ics_feed.py-Kommentar: "kein Umrechnen noetig/
 * gewollt"). `new Date(iso).getHours()` wuerde das je nach Suffix/Browser-
 * Zeitzone als echten Zeitpunkt umrechnen (das genau war der Bug: 14:00
 * eingegeben, Chip zeigte 16:00) - stattdessen wird hier wie bei
 * calendar-event-modal.tsx::toDatetimeLocalValue nur der naive Text
 * verwendet, nie new Date().getHours()/.getMinutes(). */
function naiveScheduledAt(iso: string): string {
  return iso.slice(0, 19);
}

/** Kompaktes "dd.MM. HH:MM"-Format fuer die Runden-Chips auf der Kanban-Karte
 * - formatDate/formatDateTime aus lib/utils sind fuer diesen engen Platz zu
 * lang (Monatsname + Jahr). Nutzt dieselben ISO-String-Hilfsfunktionen wie
 * die Kalender-Ansicht (lib/calendar-utils.ts), statt ueber new Date() zu
 * gehen - siehe naiveScheduledAt oben fuer die Begruendung. */
function formatChipDateTime(iso: string): string {
  const dd = iso.slice(8, 10);
  const mm = iso.slice(5, 7);
  return `${dd}.${mm}. ${formatTimeFromIso(iso)}`;
}

/** Grün = durchgeführt, Rot = abgesagt/nicht erschienen, Blau = geplant und
 * noch in der Zukunft, Grau = geplant, aber der Termin liegt bereits in der
 * Vergangenheit ohne Status-Update ("überfällig"). Vergleich als reiner
 * String (nicht als new Date(...).getTime()), damit "jetzt" (toLocalIsoString)
 * und scheduled_at im selben naiven Berlin-Wanduhrzeit-Format verglichen
 * werden - siehe naiveScheduledAt oben. */
function interviewDotClass(interview: Interview): string {
  if (interview.status === "completed") return "bg-emerald-400";
  if (interview.status === "cancelled" || interview.status === "no_show") return "bg-red-400";
  const isOverdue = naiveScheduledAt(interview.scheduled_at) < toLocalIsoString(new Date());
  return isOverdue ? "bg-[#94A3B8]" : "bg-[#1F5FA8]";
}

/** Nachfassen faellig, wenn follow_up_at heute oder in der Vergangenheit
 * liegt (Phase 5b) - farblich klar unterscheidbar vom bestehenden blauen
 * "Hot"-Badge (siehe isHot oben), das den Prozess-Status widerspiegelt statt
 * eines konkreten Termins. follow_up_at ist ein echtes tz-aware ISO-Datetime
 * (anders als scheduled_at bei Interviews), new Date() ist hier also sicher. */
function isFollowUpDue(item: CandidateSubmission): boolean {
  if (!item.follow_up_at) return false;
  const endOfToday = new Date();
  endOfToday.setHours(23, 59, 59, 999);
  return new Date(item.follow_up_at) <= endOfToday;
}

export function SubmissionViews({ submissions, candidates, clients, contacts = [], interviews: initialInterviews = [], initialStage = null, initialMineOnly = false }: {
  submissions: CandidateSubmission[];
  candidates: Candidate[];
  clients: ClientCompany[];
  contacts?: Contact[];
  interviews?: Interview[];
  // Vorfilter aus der URL (?stage=...&mine=1), z.B. per Klick auf eine
  // KPI-Kachel in der Übersicht (siehe dashboard-cockpit.tsx).
  initialStage?: SubmissionStatus | null;
  initialMineOnly?: boolean;
}) {
  const router = useRouter();
  const [view, setView] = useState<"kanban" | "table">("kanban");
  const [items, setItems] = useState(submissions);
  const [interviews, setInterviews] = useState(initialInterviews);
  const [interviewModal, setInterviewModal] = useState<{ submissionId: string; interview: Interview | null } | null>(null);
  const [search, setSearch] = useState("");
  // "Meine Prozesse" - reiner Komfort-Filter nach owner_user_id, KEINE
  // Sichtbarkeitsgrenze (Default "Alle" bleibt unveraendert). Clientseitig
  // gefiltert, da Prozesse hier bereits vollstaendig geladen sind (siehe
  // getSubmissions() in lib/api/queries.ts, keine Server-Pagination).
  const [mineOnly, setMineOnly] = useState(initialMineOnly);
  const [stageFilter, setStageFilter] = useState<SubmissionStatus | null>(initialStage);
  // Abgeschlossene Placements (archived_at gesetzt) sind standardmaessig
  // aus dem Kanban ausgeblendet (Nutzer-Vorgabe "Nach Placement aus der
  // Prozessuebersicht herausnehmen") - ueber diesen Filter wieder
  // einblendbar, rein client-seitig (die Daten bleiben unveraendert
  // geladen, betrifft nur die Kanban-/Tabellen-Anzeige hier).
  const [showArchived, setShowArchived] = useState(false);
  // Mobile-Kanban (Nutzer-Vorgabe "Mobile"): statt sechs nebeneinander-/
  // untereinanderliegender Spalten (die meisten leer) eine Stufen-Auswahl
  // plus nur die Prozesse DIESER EINEN Stufe darunter, siehe den
  // lg:hidden-Block im view === "kanban"-Zweig unten. Nur fuer den
  // Kanban-Modus relevant.
  const [mobileStage, setMobileStage] = useState<SubmissionStatus>(initialStage ?? "qualification_call");
  const { data: currentUserData } = useCurrentUser();
  const currentUserId = currentUserData?.data.id;
  const [draggedId, setDraggedId] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  // `target` gesetzt: Kanzlei-Auswahl ist Teil eines Statuswechsels (Drag&Drop
  // nach Interview). `target` undefined: eigenstaendige "Kanzlei hinzufuegen/
  // aendern"-Aktion auf der Karte, unabhaengig vom Status (Phase M.1) - PATCHt
  // direkt nur client_company_id, ohne Statuswechsel.
  const [clientPrompt, setClientPrompt] = useState<{ submissionId: string; target?: SubmissionStatus } | null>(null);
  const [cancelPrompt, setCancelPrompt] = useState<string | null>(null);
  const [quickViewCandidateId, setQuickViewCandidateId] = useState<string | null>(null);
  // Kanban-Karten sind auf eine Zeile (Name/Kanzlei/Datum) reduziert (Phase
  // 5b) - Closing-Score, Naechster Schritt, Interview-Runden und Fee werden
  // erst bei Klick auf den Ausklapp-Pfeil sichtbar, statt permanent Platz zu
  // beanspruchen.
  const [expandedIds, setExpandedIds] = useState<Set<string>>(new Set());

  function toggleExpanded(submissionId: string) {
    setExpandedIds((current) => {
      const next = new Set(current);
      if (next.has(submissionId)) next.delete(submissionId);
      else next.add(submissionId);
      return next;
    });
  }

  const candidateOf = (id: string) => candidates.find((candidate) => candidate.id === id);
  const candidateName = (id: string) => {
    const item = candidateOf(id);
    return item ? `${item.first_name} ${item.last_name}` : "Kandidat";
  };
  const clientName = (id: string | null) => clients.find((client) => client.id === id)?.name ?? "Kanzlei offen";
  const contactPersonName = (id: string | null) => formatContactName(contacts.find((contact) => contact.id === id));
  const expectedFee = (item: CandidateSubmission) => item.expected_fee ?? Math.round(Number(candidates.find((candidate) => candidate.id === item.candidate_id)?.salary_expectation?.replace(/\D/g, "") ?? 80000) * 0.27);

  // Nach submission_id gruppiert (aufsteigend nach scheduled_at sortiert,
  // "R1"/"R2"/... entspricht dieser Reihenfolge) - einmalig ueber die
  // vollstaendig geladene Interview-Liste, keine Einzel-Requests pro Karte.
  const interviewsBySubmission = useMemo(() => {
    const map = new Map<string, Interview[]>();
    for (const interview of interviews) {
      const list = map.get(interview.submission_id);
      if (list) list.push(interview);
      else map.set(interview.submission_id, [interview]);
    }
    for (const list of map.values()) {
      // String- statt new Date(...).getTime()-Vergleich: bei identisch
      // formatierten naiven ISO-Strings ergibt der lexikografische Vergleich
      // dieselbe chronologische Reihenfolge, ist aber robust gegen eine
      // moegliche Zeitzonen-Fehlinterpretation durch new Date() (siehe
      // naiveScheduledAt oben) - z.B. bei zwei Terminen ueber einen DST-
      // Wechsel hinweg.
      list.sort((a, b) => naiveScheduledAt(a.scheduled_at).localeCompare(naiveScheduledAt(b.scheduled_at)));
    }
    return map;
  }, [interviews]);

  function nextUpcomingInterview(submissionId: string): Interview | null {
    const list = interviewsBySubmission.get(submissionId) ?? [];
    const now = toLocalIsoString(new Date());
    return (
      list.find((interview) => interview.status === "scheduled" && naiveScheduledAt(interview.scheduled_at) >= now) ??
      null
    );
  }

  const filteredItems = useMemo(() => {
    const term = search.trim().toLowerCase();
    return items.filter((item) => {
      if (!showArchived && item.archived_at) return false;
      if (mineOnly && item.owner_user_id !== currentUserId) return false;
      if (stageFilter && item.status !== stageFilter) return false;
      if (!term) return true;
      const haystack = [
        candidateName(item.candidate_id), clientName(item.client_company_id),
        contactPersonName(item.contact_person_id), item.status,
      ].join(" ").toLowerCase();
      return haystack.includes(term);
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [items, search, mineOnly, stageFilter, showArchived, currentUserId, candidates, clients, contacts]);

  const exportRows = filteredItems.map((item) => ({
    Kandidat: candidateName(item.candidate_id),
    Kanzlei: clientName(item.client_company_id),
    Ansprechpartner: contactPersonName(item.contact_person_id),
    Status: item.status,
    FollowUp: formatDate(item.follow_up_at),
    ErwarteteFee: expectedFee(item),
  }));

  async function applyTransition(
    submissionId: string,
    target: SubmissionStatus,
    extra?: { client_company_id?: string; cancellation_reason?: SubmissionCancellationReason },
  ) {
    // Optimistic UI: die Kanban-Karte springt sofort in die Zielspalte, statt
    // erst auf die Serverantwort zu warten (spuerbare Verzoegerung bei jedem
    // Drag&Drop). Bei einem Fehler (z.B. Statuswechsel vom Server abgelehnt)
    // wird exakt der vorherige Zustand wiederhergestellt.
    const previous = items;
    setItems((current) =>
      current.map((item) =>
        item.id === submissionId ? { ...item, status: target, ...extra } : item,
      ),
    );
    setMessage(null);
    try {
      const updated = await apiPatch<CandidateSubmission>(`/submissions/${submissionId}/transition`, {
        status: target,
        ...extra,
      });
      setItems((current) => current.map((item) => (item.id === submissionId ? updated : item)));
    } catch (error) {
      setItems(previous);
      setMessage(error instanceof Error ? error.message : "Statuswechsel fehlgeschlagen.");
    }
  }

  /** Verknuepft/aendert die Kanzlei eines Prozesses unabhaengig vom Status
   * (Phase M.1) - vorher ging das nur ueber den clientPrompt-Dialog beim
   * Drag&Drop nach Interview; ein Prozess, der schon in Interview (oder
   * spaeter) ohne Kanzlei lag, hatte keine Moeglichkeit, das nachtraeglich zu
   * tun, ausser die Karte aus der Spalte heraus- und wieder hineinzuziehen. */
  async function updateClient(submissionId: string, clientCompanyId: string) {
    const previous = items;
    setItems((current) =>
      current.map((item) =>
        item.id === submissionId ? { ...item, client_company_id: clientCompanyId } : item,
      ),
    );
    setMessage(null);
    try {
      const updated = await apiPatch<CandidateSubmission>(`/submissions/${submissionId}`, {
        client_company_id: clientCompanyId,
      });
      setItems((current) => current.map((item) => (item.id === submissionId ? updated : item)));
    } catch (error) {
      setItems(previous);
      setMessage(error instanceof Error ? error.message : "Kanzlei konnte nicht zugeordnet werden.");
    }
  }

  /** Löscht einen versehentlich angelegten/aktivierten Prozess vollständig
   * (statt ihn nur auf "cancelled" zu setzen) - landet dadurch NICHT in der
   * Abgebrochen-Spalte/Archiv. Das Backend cascadet abhängige Activities/
   * Tasks/Notes/Feedback/Interviews/Offers; ein bereits erreichtes Placement
   * blockt die Löschung bewusst (ondelete=RESTRICT). */
  async function deleteErroneousSubmission(submissionId: string) {
    try {
      await apiDelete(`/submissions/${submissionId}`);
      setItems((current) => current.filter((item) => item.id !== submissionId));
      setMessage(null);
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Löschen fehlgeschlagen.");
    }
  }

  /** Expliziter Abschluss NACH einem Placement (siehe Backend services/
   * submissions.py::CandidateSubmissionService.archive) - blendet die Karte
   * aus dem Kanban aus, ohne Status/Historie anzutasten. Optimistic UI wie
   * applyTransition oben: sofort lokal setzen, bei Fehler zurueckrollen. */
  async function toggleArchived(submissionId: string, archive: boolean) {
    const previous = items;
    setItems((current) =>
      current.map((item) =>
        item.id === submissionId
          ? { ...item, archived_at: archive ? new Date().toISOString() : null }
          : item,
      ),
    );
    try {
      const updated = archive
        ? await archiveSubmission(submissionId)
        : await unarchiveSubmission(submissionId);
      setItems((current) =>
        current.map((item) => (item.id === submissionId ? updated : item)),
      );
    } catch (error) {
      setItems(previous);
      setMessage(
        error instanceof Error ? error.message : "Abschließen fehlgeschlagen.",
      );
    }
  }

  // Optimistic-UI-Mutationen fuer Interview-Runden - ausgelagert in
  // lib/use-interview-mutations.ts, damit dieselbe Logik hier UND im
  // Interview-Panel der Stufen-Bearbeitung (stage-edit-modal.tsx) genutzt
  // wird, statt sie zu duplizieren. Gleiches Muster wie applyTransition/
  // updateClient oben: sofort im lokalen State aendern, bei Fehler
  // zurueckrollen und ueber die bestehende `message`-Zeile informieren.
  const { createInterviewOptimistic, updateInterviewOptimistic, deleteInterviewOptimistic } =
    useInterviewMutations(interviews, setInterviews, setMessage);

  /** Gemeinsame Statuswechsel-Logik fuer Drag&Drop (Desktop) UND die
   * explizite Stufenwechsel-Aktion auf Mobile (siehe die Buttons in
   * renderCard unten) - Ziehen ueber mehrere Spalten funktioniert auf Touch
   * schlecht, daher dort Buttons statt Drag&Drop (Nutzer-Vorgabe "Mobile"). */
  function changeStage(submissionId: string, targetStatus: SubmissionStatus) {
    const submission = items.find((item) => item.id === submissionId);
    if (!submission || submission.status === targetStatus) return;

    const allowed = allowedTransitions[submission.status] ?? [];
    if (!allowed.includes(targetStatus)) {
      setMessage(`Ungültiger Statuswechsel: ${submission.status} → ${targetStatus}. Der Statusautomat blockiert diesen Schritt.`);
      return;
    }
    if (targetStatus === "interview" && !submission.client_company_id) {
      setClientPrompt({ submissionId: submission.id, target: targetStatus });
      return;
    }
    void applyTransition(submission.id, targetStatus);
  }

  function moveToStatus(targetStatus: SubmissionStatus) {
    if (!draggedId) return;
    const id = draggedId;
    setDraggedId(null);
    changeStage(id, targetStatus);
  }

  function openCandidate(candidateId: string) {
    router.push(`/kandidaten/${candidateId}?from=prozesse`);
  }

  /** Eine Kanban-Karte, gemeinsam genutzt vom Desktop-Grid (mobile=false,
   * Drag&Drop, kompakte Icon-Buttons) und der neuen Mobile-Stufenliste
   * (mobile=true, KEIN Drag&Drop - Ziehen ueber mehrere Spalten funktioniert
   * auf Touch schlecht, siehe changeStage - und mindestens 44px
   * Trefferflaeche je Aktionssymbol, Nutzer-Vorgabe
   * "Mobile"). Als Closure statt eigener Komponente, damit sie ohne
   * Prop-Drilling auf den gesamten State/die Handler dieser Komponente
   * zugreifen kann. */
  function renderCard(item: CandidateSubmission, { mobile }: { mobile: boolean }) {
    const expanded = expandedIds.has(item.id);
    const dueFollowUp = isFollowUpDue(item);
    const iconBtnClass = mobile
      ? "flex size-11 shrink-0 items-center justify-center rounded-lg text-[#94A3B8]"
      : "rounded p-1 text-[#94A3B8]";
    const iconSize = mobile ? 18 : 12;
    const nextStages = allowedTransitions[item.status]?.filter((s) => s !== "cancelled") ?? [];

    return (
      <article
        key={item.id}
        draggable={!mobile}
        onDragStart={mobile ? undefined : () => setDraggedId(item.id)}
        onClick={() => openCandidate(item.candidate_id)}
        title="Zum Kandidatenprofil"
        className={cn(
          "cursor-pointer rounded-lg border p-2 shadow-[0_1px_1px_rgba(0,0,0,.03)]",
          !mobile && "active:cursor-grabbing",
          dueFollowUp
            ? "border-red-400/50 bg-red-950/20 hover:border-red-400/70"
            : "border-white/10 bg-[#12243A] hover:border-[#1F5FA8]/50",
        )}
      >
        {/* Name und Kanzlei je auf eigener Zeile, in einer eigenen Kopfzeile
         * ohne Konkurrenz um Breite mit Datum/Icons (die stehen jetzt in
         * einer eigenen Zeile darunter) - bei langen Kanzleinamen (z.B.
         * "GmbH & Co. KG Steuerberatungsgesellschaft") fielen beide vorher
         * in ein gemeinsames truncate, sodass selbst der Kandidatenname nur
         * noch als "Pascal-Arnold Sli…" sichtbar war. Volltitel via
         * title-Attribut bei Kanzlei-Truncation weiterhin per Hover
         * einsehbar. */}
        <div className="min-w-0">
          <p className={cn("truncate font-semibold hover:underline", mobile ? "text-sm" : "text-xs")}>{candidateName(item.candidate_id)}</p>
          <p
            className={cn("mt-0.5 truncate text-[#94A3B8]", mobile ? "text-xs" : "text-[10px]")}
            title={clientName(item.client_company_id)}
          >
            {clientName(item.client_company_id)}
          </p>
        </div>
        <div className="mt-1.5 flex items-center justify-between gap-2">
          <span className="shrink-0 text-[10px] text-[#94A3B8]">{formatDate(item.follow_up_at)}</span>
          <div className={cn("flex shrink-0 items-center", mobile ? "gap-1" : "gap-0.5")}>
            {isHot(item.status) && <span className="rounded-full bg-[#1F5FA8]/20 px-1.5 py-0.5 text-[9px] text-[#69A7EA]">Hot</span>}
            {item.archived_at && <span className="rounded-full bg-emerald-500/15 px-1.5 py-0.5 text-[9px] text-emerald-300">Abgeschlossen</span>}
            <button
              type="button"
              title="Kanzlei hinzufügen/ändern"
              onClick={(event) => { event.stopPropagation(); setClientPrompt({ submissionId: item.id }); }}
              className={cn(iconBtnClass, "hover:bg-white/10 hover:text-white")}
            >
              <Building2 size={iconSize} />
            </button>
            <button
              type="button"
              title="Kandidat seitlich anzeigen (Prozesse bleibt offen)"
              onClick={(event) => { event.stopPropagation(); setQuickViewCandidateId(item.candidate_id); }}
              className={cn(iconBtnClass, "hover:bg-white/10 hover:text-white")}
            >
              <Eye size={iconSize} />
            </button>
            <button
              type="button"
              title="Prozess abbrechen"
              onClick={(event) => { event.stopPropagation(); setCancelPrompt(item.id); }}
              className={cn(iconBtnClass, "hover:bg-red-950/40 hover:text-red-200")}
            >
              <Ban size={iconSize} />
            </button>
            {item.status === "interview" && (
              <button
                type="button"
                title="Interview planen"
                onClick={(event) => { event.stopPropagation(); setInterviewModal({ submissionId: item.id, interview: null }); }}
                className={cn(iconBtnClass, "hover:bg-white/10 hover:text-white")}
              >
                <CalendarPlus size={iconSize} />
              </button>
            )}
            {item.status === "placement" && !item.archived_at && (
              <button
                type="button"
                title="Prozess abschließen (verschwindet aus dem Kanban, Historie/KPIs/Rechnungsstatus bleiben erhalten)"
                onClick={(event) => { event.stopPropagation(); void toggleArchived(item.id, true); }}
                className={cn(iconBtnClass, "hover:bg-emerald-950/40 hover:text-emerald-300")}
              >
                <Archive size={iconSize} />
              </button>
            )}
            {item.status === "placement" && item.archived_at && (
              <button
                type="button"
                title="Abschluss zurücknehmen"
                onClick={(event) => { event.stopPropagation(); void toggleArchived(item.id, false); }}
                className={cn(iconBtnClass, "hover:bg-white/10 hover:text-white")}
              >
                <ArchiveRestore size={iconSize} />
              </button>
            )}
            <button
              type="button"
              title={expanded ? "Details ausblenden" : "Details anzeigen"}
              onClick={(event) => { event.stopPropagation(); toggleExpanded(item.id); }}
              className={cn(iconBtnClass, "hover:bg-white/10 hover:text-white")}
            >
              <ChevronDown size={iconSize} className={cn("transition-transform", expanded && "rotate-180")} />
            </button>
          </div>
        </div>
        {/* Stufenwechsel auf Mobile ueber eine explizite Aktion statt
         * Drag&Drop (Nutzer-Vorgabe "Mobile") - nur gezeigt, wenn es
         * ueberhaupt einen erlaubten naechsten Schritt gibt. */}
        {mobile && nextStages.length > 0 && (
          <div className="mt-2 flex flex-wrap gap-1.5 border-t border-white/10 pt-2" onClick={(event) => event.stopPropagation()}>
            {nextStages.map((stage) => (
              <button
                key={stage}
                type="button"
                onClick={() => changeStage(item.id, stage)}
                className="flex min-h-11 flex-1 items-center justify-center gap-1 rounded-lg border border-[#1F5FA8]/40 bg-[#1F5FA8]/10 px-2 text-xs text-[#69A7EA] hover:bg-[#1F5FA8]/20"
              >
                → {STAGE_LABELS[stage]}
              </button>
            ))}
          </div>
        )}
        {expanded && (
          <div className="mt-2 space-y-2 border-t border-white/10 pt-2" onClick={(event) => event.stopPropagation()}>
            {item.closing_status && <ClosingScoreBadge status={item.closing_status} probability={item.closing_probability} />}
            <ClosingScoreForm submissionId={item.id} />
            <div>
              <p className="text-[10px] uppercase tracking-wider text-[#94A3B8]">Nächster Schritt</p>
              <p className="mt-1 text-xs">{item.next_step ?? item.summary ?? "Follow-up festlegen"}</p>
            </div>
            {(interviewsBySubmission.get(item.id)?.length ?? 0) > 0 && (
              <div>
                <p className="text-[10px] uppercase tracking-wider text-[#94A3B8]">Interview-Runden</p>
                <div className="mt-1 flex flex-wrap gap-1">
                  {(interviewsBySubmission.get(item.id) ?? []).map((interview, index) => (
                    <button
                      key={interview.id}
                      type="button"
                      title={`${interview.interview_type} — ${formatChipDateTime(interview.scheduled_at)}`}
                      onClick={() => setInterviewModal({ submissionId: item.id, interview })}
                      className="flex items-center gap-1 rounded-full border border-white/10 bg-[#0D1B2E] px-2 py-1 text-[10px] text-[#CBD5E1] hover:border-[#1F5FA8]/50 hover:text-white"
                    >
                      <span className={`size-1.5 rounded-full ${interviewDotClass(interview)}`} />
                      R{index + 1} · {formatChipDateTime(interview.scheduled_at)}
                    </button>
                  ))}
                </div>
              </div>
            )}
            <div className="flex items-center justify-between border-t border-white/10 pt-2 text-[10px] text-[#A7ADB7]">
              {nextUpcomingInterview(item.id) ? (
                <span>Nächstes Interview: {formatChipDateTime(nextUpcomingInterview(item.id)!.scheduled_at)}</span>
              ) : (
                <span>Follow-up {formatDate(item.follow_up_at)}</span>
              )}
              <span>{expectedFee(item).toLocaleString("de-DE")} €</span>
            </div>
            {item.client_company_id ? null : (
              <button
                type="button"
                onClick={(event) => { event.stopPropagation(); setClientPrompt({ submissionId: item.id }); }}
                className="flex w-full items-center justify-center gap-1.5 rounded bg-[#7F1D1D]/40 px-2 py-1.5 text-[10px] text-red-100 hover:bg-[#7F1D1D]/60"
              >
                <Building2 size={11} />Ab Interview Kanzlei verknüpfen — jetzt hinzufügen
              </button>
            )}
          </div>
        )}
      </article>
    );
  }

  return (
    <>
      <div className="mb-4 flex flex-col justify-between gap-3 lg:flex-row lg:items-center">
        <div className="rounded-lg border border-white/10 bg-[#0D1B2E]/85 px-3 py-2 text-xs text-[#CBD5E1]">
          <strong className="text-[#D8DADF]">Prozesslogik:</strong> Ein Prozess entspricht einer CandidateSubmission und kann je Kandidat mehrfach vorkommen. Ab Interview ist eine Kanzlei zwingend verknüpft.
        </div>
        <div className="flex flex-wrap justify-end gap-2">
          <ExportActions filename="prozesse" rows={exportRows} />
          <Button size="sm" variant={view === "kanban" ? "dark" : "outline"} onClick={() => setView("kanban")}><Columns3 size={14} />Kanban</Button>
          <Button size="sm" variant={view === "table" ? "dark" : "outline"} onClick={() => setView("table")}><List size={14} />Tabelle</Button>
        </div>
      </div>
      <div className="mb-4 flex flex-col gap-2 lg:flex-row lg:items-center">
        <div className="flex-1">
          <FilterBar
            placeholder="Nach Kandidat, Kanzlei, Ansprechpartner oder Status suchen"
            value={search}
            onChange={setSearch}
            ownerFilter={{ mineOnly, onChange: setMineOnly }}
          />
        </div>
        <Button
          size="sm"
          variant={showArchived ? "dark" : "outline"}
          onClick={() => setShowArchived((current) => !current)}
          title="Abgeschlossene Placements sind standardmäßig ausgeblendet - Historie/KPIs/Rechnungsstatus bleiben davon unberührt."
        >
          <Archive size={14} />
          {showArchived ? "Abgeschlossene ausblenden" : "Abgeschlossene anzeigen"}
        </Button>
      </div>
      {stageFilter && (
        <div className="mb-3">
          <Badge tone="blue" className="gap-1.5">
            Nur Stufe: {STAGE_LABELS[stageFilter]}
            <button type="button" onClick={() => setStageFilter(null)} title="Filter entfernen" className="hover:text-white">
              <X size={12} />
            </button>
          </Badge>
        </div>
      )}
      {message && <div className="mb-4 flex items-center gap-2 rounded-lg border border-[#D8DADF]/20 bg-[#102A4C]/65 p-3 text-xs text-[#CBD5E1]"><ShieldAlert size={15} />{message}</div>}

      {clientPrompt && (
        <div className="mb-4 rounded-lg border border-[#1F5FA8]/30 bg-[#102A4C]/60 p-3 text-xs text-[#CBD5E1]">
          <p className="mb-2">
            {clientPrompt.target
              ? "Ab Interview muss eine Kanzlei verknüpft sein. Bitte auswählen:"
              : "Kanzlei für diesen Prozess auswählen:"}
          </p>
          <div className="flex flex-wrap items-center gap-2">
            <select
              className="rounded-md border border-white/10 bg-[#071426] px-2 py-1.5 text-xs text-[#F8FAFC]"
              defaultValue=""
              onChange={(event) => {
                if (!event.target.value) return;
                if (clientPrompt.target) {
                  void applyTransition(clientPrompt.submissionId, clientPrompt.target, {
                    client_company_id: event.target.value,
                  });
                } else {
                  void updateClient(clientPrompt.submissionId, event.target.value);
                }
                setClientPrompt(null);
              }}
            >
              <option value="" disabled>Kanzlei wählen…</option>
              {clients.filter((client) => client.status !== "blocked").map((client) => (
                <option key={client.id} value={client.id}>{client.name}</option>
              ))}
            </select>
            <Button size="sm" variant="outline" onClick={() => setClientPrompt(null)}>Abbrechen</Button>
          </div>
        </div>
      )}

      {cancelPrompt && (
        <div className="mb-4 rounded-lg border border-red-400/25 bg-red-950/30 p-3 text-xs text-red-100">
          <p className="mb-2">Prozess abbrechen — Grund auswählen:</p>
          <div className="flex flex-wrap items-center gap-2">
            {CANCELLATION_REASONS.map((reason) => (
              <Button
                key={reason.value}
                size="sm"
                variant="outline"
                onClick={() => {
                  void applyTransition(cancelPrompt, "cancelled", { cancellation_reason: reason.value });
                  setCancelPrompt(null);
                }}
              >
                {reason.label}
              </Button>
            ))}
            <span className="mx-1 h-4 w-px bg-red-400/25" />
            <Button
              size="sm"
              variant="outline"
              className="border-red-400/50 text-red-100 hover:bg-red-950/60"
              title="Löscht den Prozess vollständig - erscheint nicht unter Abgebrochen/Archiv. Für versehentlich angelegte oder aktivierte Prozesse."
              onClick={() => {
                void deleteErroneousSubmission(cancelPrompt);
                setCancelPrompt(null);
              }}
            >
              Fehler — Prozess löschen
            </Button>
            <Button size="sm" variant="ghost" onClick={() => setCancelPrompt(null)}>Zurück</Button>
          </div>
          <p className="mt-2 text-[11px] text-red-200/70">
            „Fehler“ löscht den Prozess unwiderruflich (kein Eintrag in „Abgebrochen“) — die anderen Gründe archivieren ihn stattdessen.
          </p>
        </div>
      )}

      {view === "kanban" ? (
        <div className="pb-4">
          {/* Mobile (<lg): Stufen-Auswahl + nur die Prozesse DIESER EINEN
           * Stufe darunter, statt sechs (meist leerer) Spalten/Bloecke
           * uebereinander - Nutzer-Vorgabe "Mobile". Ab lg identisches
           * Sechs-Spalten-Kanban wie zuvor, inkl. Drag&Drop. */}
          <div className="lg:hidden">
            <div className="scrollbar-subtle -mx-1 mb-3 flex gap-1.5 overflow-x-auto px-1 pb-1">
              {columns.map((column) => {
                const count = filteredItems.filter((s) => s.status === column.status).length;
                const active = mobileStage === column.status;
                return (
                  <button
                    key={column.status}
                    type="button"
                    onClick={() => setMobileStage(column.status)}
                    className={cn(
                      "flex min-h-11 shrink-0 items-center gap-1.5 rounded-full border px-3 text-xs font-medium",
                      active
                        ? "border-[#1F5FA8]/60 bg-[#1F5FA8]/25 text-white"
                        : "border-white/10 bg-[#0D1B2E] text-[#94A3B8]",
                    )}
                  >
                    {column.title}
                    <span
                      className={cn(
                        "grid size-5 place-items-center rounded-full text-[10px]",
                        active ? "bg-[#1F5FA8]/40 text-white" : "bg-[#12243A] text-[#CBD5E1]",
                      )}
                    >
                      {count}
                    </span>
                  </button>
                );
              })}
            </div>
            <div className="space-y-2 pb-4">
              {filteredItems.filter((s) => s.status === mobileStage).map((item) => renderCard(item, { mobile: true }))}
              {/* Leere Stufe kompakt statt als grosse leere Flaeche - Nutzer-
               * Vorgabe "Mobile". */}
              {filteredItems.filter((s) => s.status === mobileStage).length === 0 && (
                <p className="py-6 text-center text-xs text-[#94A3B8]">Keine Prozesse in dieser Stufe.</p>
              )}
            </div>
          </div>

          <div className="hidden lg:grid lg:grid-cols-3 lg:gap-3 xl:grid-cols-6">
            {columns.map((column) => {
              const columnItems = filteredItems.filter((submission) => submission.status === column.status);
              return (
                <section
                  key={column.status}
                  className="min-w-0 rounded-xl border border-white/10 bg-[#0D1B2E] p-2 shadow-[0_12px_30px_rgba(0,0,0,.18)]"
                  onDragOver={(event) => event.preventDefault()}
                  onDrop={() => moveToStatus(column.status)}
                >
                  <header className="flex items-center justify-between px-2 py-2">
                    <h2 className="truncate text-xs font-semibold text-[#F8FAFC]">{column.title}</h2>
                    <span className="grid size-5 shrink-0 place-items-center rounded-full border border-white/10 bg-[#12243A] text-[10px] text-[#CBD5E1]">{columnItems.length}</span>
                  </header>
                  <div className="scrollbar-subtle max-h-[calc(100vh-360px)] space-y-2 overflow-y-auto">
                    {columnItems.map((item) => renderCard(item, { mobile: false }))}
                    {columnItems.length === 0 && <div className="rounded-lg border border-dashed border-white/10 p-5 text-center text-[11px] text-[#94A3B8]">Keine Prozesse</div>}
                  </div>
                </section>
              );
            })}
          </div>
        </div>
      ) : (
        <>
        {/* Mobile (<lg): Karten statt der 10-spaltigen Tabellenansicht, siehe
         * candidates-table.tsx fuer denselben Fix + Begruendung (Nutzer-
         * Feedback "mobile Version nicht passend") - der Kanban-Modus oben
         * hat bereits eine eigene Mobile-Darstellung, diese alternative
         * "Tabelle"-Ansicht bisher nicht. */}
        <div className="space-y-2 lg:hidden">
          {filteredItems.map((item) => (
            <div
              key={item.id}
              onClick={() => openCandidate(item.candidate_id)}
              className="cursor-pointer rounded-lg border border-white/10 bg-[#12243A] p-3 active:bg-[#203A5A]/35"
            >
              <div className="flex items-start justify-between gap-2">
                <p className="min-w-0 truncate text-sm font-semibold text-[#D8DADF] hover:underline">{candidateName(item.candidate_id)}</p>
                <StatusPill status={item.status} />
              </div>
              <p className="mt-0.5 truncate text-xs text-[#94A3B8]">{clientName(item.client_company_id)}</p>
              <div className="mt-2 flex items-center justify-between text-[11px] text-[#8a9095]">
                <span>Follow-up {formatDate(item.follow_up_at)}</span>
                <span>{expectedFee(item).toLocaleString("de-DE")} €</span>
              </div>
              <p className="mt-1 truncate text-[11px] text-[#8a9095]">{item.next_step ?? "Nächster Schritt offen"}</p>
              <div className="mt-2 flex items-center gap-1" onClick={(event) => event.stopPropagation()}>
                <button
                  type="button"
                  title="Kanzlei hinzufügen/ändern"
                  onClick={() => setClientPrompt({ submissionId: item.id })}
                  className="flex size-11 items-center justify-center rounded-lg text-[#94A3B8] hover:bg-white/10 hover:text-white"
                >
                  <Building2 size={18} />
                </button>
                <button
                  type="button"
                  title="Kandidat seitlich anzeigen (Prozesse bleibt offen)"
                  onClick={() => setQuickViewCandidateId(item.candidate_id)}
                  className="flex size-11 items-center justify-center rounded-lg text-[#94A3B8] hover:bg-white/10 hover:text-white"
                >
                  <Eye size={18} />
                </button>
              </div>
            </div>
          ))}
          {filteredItems.length === 0 && (
            <p className="py-8 text-center text-xs text-[#94A3B8]">Keine Prozesse gefunden.</p>
          )}
        </div>
        <div className="hidden lg:block">
        <DataTable headers={["Kandidat", "Kanzlei", "Ansprechpartner", "Status", "Closing", "Versendet", "Follow-up", "Nächster Schritt", "Erwartete Fee", "Export"]}>
          {filteredItems.map((item) => (
            <tr key={item.id} className="cursor-pointer hover:bg-[#203A5A]/35" onClick={() => openCandidate(item.candidate_id)}>
              <td className="px-4 py-3.5 font-semibold hover:underline">{candidateName(item.candidate_id)}</td>
              <td className="px-4 py-3.5">{clientName(item.client_company_id)}</td>
              <td className="px-4 py-3.5">{contactPersonName(item.contact_person_id)}</td>
              <td className="px-4 py-3.5"><StatusPill status={item.status} /></td>
              <td className="px-4 py-3.5"><ClosingScoreBadge status={item.closing_status} probability={item.closing_probability} /></td>
              <td className="px-4 py-3.5">{formatDate(item.submitted_at)}</td>
              <td className="px-4 py-3.5">{formatDate(item.follow_up_at)}</td>
              <td className="px-4 py-3.5">{item.next_step ?? "—"}</td>
              <td className="px-4 py-3.5">{expectedFee(item).toLocaleString("de-DE")} €</td>
              <td className="px-4 py-3.5">
                <div className="flex items-center gap-2">
                  <button
                    type="button"
                    title="Kanzlei hinzufügen/ändern"
                    onClick={(event) => { event.stopPropagation(); setClientPrompt({ submissionId: item.id }); }}
                    className="rounded p-1 text-[#94A3B8] hover:bg-white/10 hover:text-white"
                  >
                    <Building2 size={13} />
                  </button>
                  <button
                    type="button"
                    title="Kandidat seitlich anzeigen (Prozesse bleibt offen)"
                    onClick={(event) => { event.stopPropagation(); setQuickViewCandidateId(item.candidate_id); }}
                    className="rounded p-1 text-[#94A3B8] hover:bg-white/10 hover:text-white"
                  >
                    <Eye size={13} />
                  </button>
                  <button
                    type="button"
                    title="Diese Zeile als CSV exportieren"
                    onClick={(event) => {
                      event.stopPropagation();
                      downloadCsv(`prozess-${candidateName(item.candidate_id).replaceAll(" ", "_")}`, [
                        {
                          Kandidat: candidateName(item.candidate_id),
                          Kanzlei: clientName(item.client_company_id),
                          Ansprechpartner: contactPersonName(item.contact_person_id),
                          Status: item.status,
                          Versendet: formatDate(item.submitted_at),
                          FollowUp: formatDate(item.follow_up_at),
                          NächsterSchritt: item.next_step ?? "—",
                          ErwarteteFee: expectedFee(item),
                        },
                      ]);
                    }}
                    className="rounded p-1 text-[#94A3B8] hover:bg-white/10 hover:text-white"
                  >
                    <Download size={14} />
                  </button>
                </div>
              </td>
            </tr>
          ))}
        </DataTable>
        </div>
        </>
      )}

      <CandidateQuickViewDrawer
        candidate={quickViewCandidateId ? candidateOf(quickViewCandidateId) ?? null : null}
        onClose={() => setQuickViewCandidateId(null)}
      />

      {interviewModal && (
        <InterviewModal
          interview={interviewModal.interview}
          onClose={() => setInterviewModal(null)}
          onCreate={(payload) => void createInterviewOptimistic(interviewModal.submissionId, payload)}
          onUpdate={(interview, payload) => void updateInterviewOptimistic(interview, payload)}
          onDelete={(interview) => void deleteInterviewOptimistic(interview)}
        />
      )}
    </>
  );
}
