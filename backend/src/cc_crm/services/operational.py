import re
import uuid
from datetime import UTC, date, datetime, timedelta
from statistics import mean, median

from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from cc_crm.core.errors import ConflictError, EntityNotFoundError
from cc_crm.core.time import naive_utc
from cc_crm.models.activity import Activity
from cc_crm.models.candidate import Candidate
from cc_crm.models.client_company import ClientCompany
from cc_crm.models.email_template import EmailTemplate
from cc_crm.models.enums import InvoiceStatus, SubmissionStatus, TaskStatus
from cc_crm.models.operational import Document, EmailDraftLog, SourcingMetric
from cc_crm.models.recruiting import Fee, Offer, Placement
from cc_crm.models.submission import CandidateSubmission
from cc_crm.models.task import Task
from cc_crm.repositories.candidate_pitch_logs import CandidatePitchLogRepository
from cc_crm.repositories.email_templates import EmailTemplateRepository
from cc_crm.repositories.operational import (
    DocumentRepository,
    EmailDraftRepository,
    SourcingMetricRepository,
)
from cc_crm.schemas.operational import (
    DocumentCreate,
    EmailDraftCreate,
    EmailTemplateUpdate,
    SourcingMetricCreate,
)
from cc_crm.services.base import CrudService
from cc_crm.services.recruiting import stage_reached_counts
from cc_crm.services.storage import has_generic_filename

# {candidate}, {candidate_number}, ... - erfasst jedes {wort} literal, keine
# verschachtelten/format-spec-Platzhalter (nicht gebraucht, siehe
# EmailTemplate-Docstring).
PLACEHOLDER_RE = re.compile(r"\{(\w+)\}")


class EmptyUpdate(BaseModel):
    pass


class DocumentService(CrudService[Document, DocumentCreate, EmptyUpdate]):
    def __init__(self, session: Session) -> None:
        repository = DocumentRepository(session)
        super().__init__(session, repository, "Document")
        self.documents = repository

    def create(self, payload: DocumentCreate) -> Document:
        values = payload.model_dump(exclude_none=True)
        values["has_generic_filename"] = has_generic_filename(payload.filename)
        try:
            entity = self.repository.create(values)
            self.session.commit()
            return entity
        except IntegrityError as exception:
            self.session.rollback()
            raise ConflictError(f"{self.entity_name} conflicts with existing data") from exception
        except Exception:
            self.session.rollback()
            raise


class SourcingMetricService(CrudService[SourcingMetric, SourcingMetricCreate, EmptyUpdate]):
    def __init__(self, session: Session) -> None:
        repository = SourcingMetricRepository(session)
        super().__init__(session, repository, "SourcingMetric")
        self.metrics = repository

    @staticmethod
    def _rate(numerator: int, denominator: int) -> float | None:
        return round(numerator / denominator * 100, 1) if denominator else None

    def totals_for_period(self, period_start: date, period_end: date) -> dict[str, object]:
        """Summiert alle manuell erfassten SourcingMetric-Datensaetze, deren
        Zeitraum sich mit [period_start, period_end] ueberschneidet. has_data
        ist False, solange noch keine einzige Erfassung vorliegt - die
        Analytics-Seite zeigt dann "Keine Daten erfasst" statt einer Zahl."""
        entries = self.metrics.in_period(period_start, period_end)
        pitches = sum(entry.pitches for entry in entries)
        responses = sum(entry.responses for entry in entries)
        positive_responses = sum(entry.positive_responses for entry in entries)
        qualification_calls = sum(entry.qualification_calls for entry in entries)
        return {
            "has_data": len(entries) > 0,
            "pitches": pitches,
            "responses": responses,
            "positive_responses": positive_responses,
            "qualification_calls": qualification_calls,
            "pitch_to_response_rate": self._rate(responses, pitches),
            "response_to_qualification_call_rate": self._rate(qualification_calls, responses),
        }


class EmailWorkflowService:
    """Mail-Vorlagen wurden aus dieser Klasse in die DB-Tabelle
    `email_templates` verlagert (Auftrag "Mailvorlagen editierbar machen",
    Alembic-Revision d4e5f6a7b8c9), damit Name/Betreff/Text ohne Deploy im CRM
    bearbeitet werden koennen - siehe models/email_template.py::EmailTemplate.
    Die vormals hier hartcodierte TEMPLATES-Liste (13 Vorlagen) wurde 1:1 in
    die Migration als Seed-Daten uebernommen; `templates()` liest jetzt aus
    `self.templates_repo` statt aus einer Python-Konstante."""

    def __init__(self, session: Session) -> None:
        self.session = session
        self.drafts = EmailDraftRepository(session)
        self.templates_repo = EmailTemplateRepository(session)

    @staticmethod
    def extract_placeholders(subject: str, body: str) -> list[str]:
        """Liest die tatsaechlich verwendeten {token}-Platzhalter aus subject+
        body (Reihenfolge des ersten Vorkommens, keine Duplikate) - ersetzt
        die vorherige statische, fuer alle Vorlagen identische Liste, die
        Platzhalter zeigte, die eine Vorlage gar nicht benutzte."""
        seen: dict[str, None] = {}
        for match in PLACEHOLDER_RE.findall(f"{subject}\n{body}"):
            seen.setdefault(match, None)
        return list(seen)

    def templates(self) -> list[dict[str, object]]:
        return [
            {
                "key": template.key,
                "name": template.name,
                "subject": template.subject,
                "body": template.body,
                "placeholders": self.extract_placeholders(template.subject, template.body),
            }
            for template in self.templates_repo.list_all()
        ]

    def update_template(self, key: str, payload: EmailTemplateUpdate) -> EmailTemplate:
        """PATCH /operational/email-templates/{key} - `key` selbst ist bewusst
        nicht Teil von EmailTemplateUpdate (siehe dortiger Docstring) und
        bleibt deshalb unveraendert, auch wenn Name/Betreff/Text bearbeitet
        werden."""
        template = self.templates_repo.get_by_key(key)
        if template is None:
            raise EntityNotFoundError(f"Mail-Vorlage '{key}' nicht gefunden")
        for field, value in payload.model_dump(exclude_unset=True).items():
            setattr(template, field, value)
        self.session.commit()
        self.session.refresh(template)
        return template

    def create_draft(self, payload: EmailDraftCreate) -> EmailDraftLog:
        draft = self.drafts.create(
            {
                **payload.model_dump(exclude_none=True),
                "provider": "outlook",
                "drafted_at": datetime.now(UTC),
            }
        )
        self.session.commit()
        return draft


class CockpitService:
    HOT = {
        SubmissionStatus.INTERVIEW,
        SubmissionStatus.OFFER,
        SubmissionStatus.PLACEMENT,
    }

    def __init__(self, session: Session) -> None:
        self.session = session

    @staticmethod
    def _rate(numerator: int, denominator: int) -> float:
        return round(numerator / denominator * 100, 1) if denominator else 0.0

    def _candidate_names(self, candidate_ids: set[uuid.UUID]) -> dict[uuid.UUID, str]:
        if not candidate_ids:
            return {}
        rows = self.session.execute(
            select(Candidate.id, Candidate.first_name, Candidate.last_name).where(
                Candidate.id.in_(candidate_ids)
            )
        ).all()
        return {row.id: f"{row.first_name} {row.last_name}" for row in rows}

    def _client_names(self, client_ids: set[uuid.UUID]) -> dict[uuid.UUID, str]:
        if not client_ids:
            return {}
        rows = self.session.execute(
            select(ClientCompany.id, ClientCompany.name).where(ClientCompany.id.in_(client_ids))
        ).all()
        return {row.id: row.name for row in rows}

    @staticmethod
    def _hot_title(
        submission: CandidateSubmission,
        candidate_names: dict[uuid.UUID, str],
        client_names: dict[uuid.UUID, str],
    ) -> str:
        """z.B. "Interview — Max Mustermann bei ACME GmbH" statt nur "Interview"."""
        status_label = submission.status.value.replace("_", " ").title()
        candidate_name = candidate_names.get(submission.candidate_id)
        if candidate_name is None:
            return status_label
        client_name = (
            client_names.get(submission.client_company_id) if submission.client_company_id else None
        )
        who = f"{candidate_name} bei {client_name}" if client_name else candidate_name
        return f"{status_label} — {who}"

    def build(
        self, period: str, owner_user_ids: list[uuid.UUID] | None = None
    ) -> dict[str, object]:
        now = naive_utc(datetime.now(UTC))
        since = now - timedelta(days={"week": 7, "month": 30, "quarter": 90}.get(period, 7))
        due_soon = now + timedelta(days=1)
        # Neuer Nutzerfilter oben in der Analytics-Seite (Nutzer-Vorgabe:
        # "oben koennen mehrere user angewaehlt werden... standardauswahl
        # sind alle user") - filtert nach Candidate.owner_user_id (gleiches
        # Feld wie der bestehende "Meine Kandidaten"-Komfort-Filter), NICHT
        # nach dem Ersteller von Submission/Offer/Placement/Fee, da diese
        # Objekte kein eigenes owner_user_id-Feld mit derselben Bedeutung
        # fuehren. `owner_user_ids=None` bedeutet "kein Filter aktiv" (alle
        # Nutzer) - eine leere Liste (theoretisch: alle Checkboxen manuell
        # abgewaehlt) filtert auf 0 Kandidaten statt auf "alle", damit die UI
        # dem tatsaechlichen Auswahlzustand entspricht.
        owner_filter_active = owner_user_ids is not None
        filtered_candidate_ids: set[uuid.UUID] | None = None
        if owner_filter_active:
            filtered_candidate_ids = set(
                self.session.scalars(
                    select(Candidate.id).where(Candidate.owner_user_id.in_(owner_user_ids or []))
                ).all()
            )
        submissions = list(self.session.scalars(select(CandidateSubmission)).all())
        if filtered_candidate_ids is not None:
            submissions = [
                item for item in submissions if item.candidate_id in filtered_candidate_ids
            ]
        submission_ids_for_owner_filter = {item.id for item in submissions}
        tasks = list(
            self.session.scalars(
                select(Task).where(Task.status.in_([TaskStatus.OPEN, TaskStatus.IN_PROGRESS]))
            ).all()
        )
        # KEIN select(Interview) hier - die separate Interview-Tabelle
        # (Termin-/Feedback-Verwaltung, siehe services/recruiting.py) wird in
        # der Praxis nicht gepflegt und blieb deshalb dauerhaft leer, obwohl
        # das Kanban laengst Submissions mit Status INTERVIEW zeigte
        # ("Interviews: 0" in Analytics vs. echte Prozesse im Kanban - siehe
        # Nutzer-Feedback 2026-07-15). "Interviews" zaehlt daher weiterhin
        # NICHT ueber die Interview-Tabelle, sondern (seit Punkt 3c) ueber
        # die im Zeitraum tatsaechlich erreichte INTERVIEW-Transition
        # (siehe reached_since/stage_reached_counts unten) - das behebt
        # zusaetzlich die vorherige Inkonsistenz, dass "interviews" (anders
        # als offers/placements) den period-Zeitraum ignorierte.
        reached_interview_stage = {
            SubmissionStatus.INTERVIEW,
            SubmissionStatus.OFFER,
            SubmissionStatus.PLACEMENT,
        }
        offers = [
            item
            for item in self.session.scalars(select(Offer)).all()
            if naive_utc(item.created_at) >= since
            and (
                filtered_candidate_ids is None
                or item.submission_id in submission_ids_for_owner_filter
            )
        ]
        all_placements = list(self.session.scalars(select(Placement)).all())
        # Ungefiltert (nicht auf `since` beschraenkt) - eine Fee kann neuer
        # sein als das zugehoerige Placement (nachtraegliche Teilrechnung),
        # daher muss die Owner-Zuordnung unabhaengig vom Placement-Zeitraum
        # aufgeloest werden koennen.
        placement_ids_for_owner_filter = {
            item.id
            for item in all_placements
            if filtered_candidate_ids is None
            or item.submission_id in submission_ids_for_owner_filter
        }
        placements = [
            item
            for item in all_placements
            if naive_utc(item.created_at) >= since and item.id in placement_ids_for_owner_filter
        ]
        fees = [
            item
            for item in self.session.scalars(select(Fee)).all()
            if naive_utc(item.created_at) >= since
            and (
                filtered_candidate_ids is None
                or item.placement_id in placement_ids_for_owner_filter
            )
        ]
        period_submissions = [item for item in submissions if naive_utc(item.created_at) >= since]
        due_tasks = [
            task
            for task in tasks
            if (task.due_at is None or naive_utc(task.due_at) <= due_soon)
            # Zurueckgestellte Tasks (POST /tasks/{id}/snooze) bleiben bis zum
            # Ablauf der Frist aus der Dashboard-To-Do-Sektion draussen -
            # gleiche Regel wie bei GET /tasks?status=open (siehe
            # repositories/tasks.py::filtered(exclude_snoozed=...)).
            and (task.snoozed_until is None or naive_utc(task.snoozed_until) <= now)
        ]
        # Archivierte Placements ("Placement abschliessen", siehe
        # SubmissionService.archive()) sollen aus den beiden Action-Listen
        # verschwinden (wie schon im Kanban), aber NICHT aus den KPI-Zahlen
        # weiter unten (kpis/rates nutzen weiterhin die ungefilterte
        # `submissions`-Liste) - Nutzer-Vorgabe: die Kennzahlen sollen
        # archivierte Placements weiterhin mitzaehlen, nur die
        # "Heisse Prozesse"/"Datenluecken"-Listen sollen sie ausblenden.
        hot_submissions = [
            item for item in submissions if item.status in self.HOT and item.archived_at is None
        ]
        # Prozesse im Status OFFER/PLACEMENT OHNE zugehoerigen Offer-/
        # Placement-Datensatz - unfertige Erfassungen (Kanban-Drag ohne
        # ausgefuelltes Formular), siehe CockpitRead.data_gaps. UEBER DEN
        # GESAMTEN BESTAND geprueft (nicht period-beschraenkt), eine
        # unfertige Erfassung bleibt unfertig, unabhaengig vom gewaehlten
        # Cockpit-Zeitraum.
        offer_submission_ids = set(self.session.scalars(select(Offer.submission_id)).all())
        placement_submission_ids = set(self.session.scalars(select(Placement.submission_id)).all())
        gap_submissions = [
            item
            for item in submissions
            if item.archived_at is None
            and (
                (item.status == SubmissionStatus.OFFER and item.id not in offer_submission_ids)
                or (
                    item.status == SubmissionStatus.PLACEMENT
                    and item.id not in placement_submission_ids
                )
            )
        ]
        # Aeltere Task-Zeilen (vor Einfuehrung von candidate_id/client_company_id
        # auf automatischen Follow-ups) haben diese Spalten leer, obwohl die
        # verknuepfte Submission Kandidat/Kanzlei kennt - als Fallback ueber
        # candidate_submission_id aufloesen, statt auf der Uebersicht
        # namenlose Eintraege ("Automatisch aus dem Prozessstatus erzeugtes
        # Follow-up" ohne Kandidat/Kanzlei davor) anzuzeigen.
        submissions_by_id = {item.id: item for item in submissions}

        def _task_submission(task: Task) -> CandidateSubmission | None:
            if task.candidate_submission_id is None:
                return None
            return submissions_by_id.get(task.candidate_submission_id)

        def _task_candidate_id(task: Task) -> uuid.UUID | None:
            if task.candidate_id:
                return task.candidate_id
            submission = _task_submission(task)
            return submission.candidate_id if submission else None

        def _task_client_id(task: Task) -> uuid.UUID | None:
            if task.client_company_id:
                return task.client_company_id
            submission = _task_submission(task)
            return submission.client_company_id if submission else None

        task_candidate_ids = {task.id: _task_candidate_id(task) for task in due_tasks}
        task_client_ids = {task.id: _task_client_id(task) for task in due_tasks}

        # Namen fuer Kandidat/Kanzlei in einem Bulk-Query je Entitaet statt pro
        # Zeile nachzuladen (kein ORM relationship() in diesem Codebase, daher
        # kein selectinload moeglich - bulk IN-Query erreicht denselben Zweck:
        # konstante statt mit der Datenmenge wachsende Query-Anzahl).
        candidate_ids = {value for value in task_candidate_ids.values() if value} | {
            item.candidate_id for item in hot_submissions
        } | {item.candidate_id for item in gap_submissions}
        client_ids = (
            {value for value in task_client_ids.values() if value}
            | {item.client_company_id for item in hot_submissions if item.client_company_id}
            | {item.client_company_id for item in gap_submissions if item.client_company_id}
        )
        candidate_names = self._candidate_names(candidate_ids)
        client_names = self._client_names(client_ids)

        def _task_names(task: Task) -> tuple[str | None, str | None]:
            candidate_id = task_candidate_ids[task.id]
            client_id = task_client_ids[task.id]
            candidate_name = candidate_names.get(candidate_id) if candidate_id else None
            client_name = client_names.get(client_id) if client_id else None
            return candidate_name, client_name

        important = []
        for task in due_tasks:
            candidate_name, client_name = _task_names(task)
            important.append(
                {
                    "kind": "task",
                    "title": task.title,
                    "detail": " — ".join(
                        filter(
                            None,
                            [candidate_name, client_name, task.description or "Offene Aufgabe"],
                        )
                    ),
                    "due_at": task.due_at,
                    "candidate_id": task_candidate_ids[task.id],
                    "client_company_id": task_client_ids[task.id],
                    "submission_id": task.candidate_submission_id,
                    "priority": task.priority.value,
                    "task_id": task.id,
                }
            )
        hot = [
            {
                "kind": "submission",
                "title": self._hot_title(item, candidate_names, client_names),
                "detail": item.next_step or "Nächsten Schritt abstimmen",
                "due_at": item.follow_up_at,
                "candidate_id": item.candidate_id,
                "client_company_id": item.client_company_id,
                "submission_id": item.id,
                "priority": "high",
            }
            for item in hot_submissions
        ]
        data_gaps = [
            {
                "kind": "submission",
                "title": self._hot_title(item, candidate_names, client_names),
                "detail": (
                    "Status 'Offer' ohne erfasstes Angebot (Gehalt/Fee fehlt)"
                    if item.status == SubmissionStatus.OFFER
                    else "Status 'Placement' ohne erfasstes Placement (Gehalt/Fee fehlt)"
                ),
                "due_at": item.follow_up_at,
                "candidate_id": item.candidate_id,
                "client_company_id": item.client_company_id,
                "submission_id": item.id,
                "priority": "normal",
            }
            for item in gap_submissions
        ]
        paid = sum(1 for fee in fees if fee.invoice_status == InvoiceStatus.PAID)
        expected = sum(float(item.expected_fee or 0) for item in submissions)
        realized = sum(
            float(fee.amount_net) for fee in fees if fee.invoice_status == InvoiceStatus.PAID
        )
        cv_count_query = select(func.count()).select_from(Candidate).where(
            Candidate.cv_in_recorded_at.isnot(None)
        )
        if filtered_candidate_ids is not None:
            cv_count_query = cv_count_query.where(Candidate.id.in_(filtered_candidate_ids))
        cv_count = self.session.scalar(cv_count_query) or 0
        # UEBER DEN GESAMTEN BESTAND (nicht auf `period` beschraenkt wie die
        # `fees`-Liste oben) - eine seit Monaten offene Rechnung bleibt
        # "offen", unabhaengig vom gewaehlten Cockpit-Zeitraum. Zaehlt
        # DISTINCT Placements (nicht Fees): ein Placement mit mehreren
        # offenen Teilrechnungen soll trotzdem nur einmal auftauchen.
        open_invoice_placement_count = len(
            {
                fee.placement_id
                for fee in self.session.scalars(select(Fee)).all()
                if fee.invoice_status not in (InvoiceStatus.PAID, InvoiceStatus.CANCELLED)
                and (
                    filtered_candidate_ids is None
                    or fee.placement_id in placement_ids_for_owner_filter
                )
            }
        )
        reached_interview_in_period = [
            item for item in period_submissions if item.status in reached_interview_stage
        ]
        sourcing = SourcingMetricService(self.session).totals_for_period(since.date(), now.date())
        # PITCH/INMAIL (Stufe 1 der 7-stufigen Pipeline, siehe
        # CandidatePitchLog-Docstring) - unabhaengig von SourcingMetric
        # (Nutzer-Entscheidung "Ersetzen": die manuell erfassten
        # Pitches/Antworten-Zahlen aus dem Sourcing-Formular werden hier NICHT
        # mehr verwendet, `sourcing` oben bleibt nur fuer die uebrigen
        # SourcingFunnel-Felder erhalten).
        pitch_candidate_ids = filtered_candidate_ids if owner_filter_active else None
        pitches_in_period = [
            item
            for item in CandidatePitchLogRepository(self.session).list_all(
                candidate_ids=list(pitch_candidate_ids) if pitch_candidate_ids is not None else None
            )
            if naive_utc(item.occurred_at) >= since
        ]
        # PIPELINE-Kennzahlen: aus der echten Statuswechsel-Historie
        # (AuditLog), nicht aus Anlagezeitpunkt oder aktuellem Status - siehe
        # services/recruiting.py::stage_reached_counts fuer die ausfuehrliche
        # Begruendung (Nutzer-Entscheidung "KPIs stimmen nicht", Punkt 3).
        # UEBER ALLE Submissions prueft (nicht nur period_submissions), da
        # eine im Zeitraum erreichte Stufe nicht voraussetzt, dass die
        # Submission selbst auch in diesem Zeitraum ANGELEGT wurde.
        all_submission_ids = [item.id for item in submissions]
        reached_since = stage_reached_counts(self.session, all_submission_ids, since=since)
        return {
            "period": period,
            "important": important,
            "hot_processes": hot,
            "data_gaps": data_gaps,
            "sourcing": sourcing,
            "recruiting_kpis": self._recruiting_kpis(),
            "kpis": {
                "qualification_calls": len(period_submissions),
                "cv_available": cv_count,
                "submissions": len(period_submissions),
                "cv_outs_reached_count": len(reached_since[SubmissionStatus.CV_OUT]),
                "interviews": len(reached_since[SubmissionStatus.INTERVIEW]),
                "offers": len(offers),
                "offer_stage_reached_count": len(reached_since[SubmissionStatus.OFFER]),
                "placements": len(placements),
                "placement_stage_reached_count": len(reached_since[SubmissionStatus.PLACEMENT]),
                "expected_fees": expected,
                "realized_fees": realized,
                "open_invoice_placement_count": open_invoice_placement_count,
                "pitches": len(pitches_in_period),
            },
            "rates": {
                "pitch_to_qualification_call_rate": self._rate(
                    len(period_submissions), len(pitches_in_period)
                ),
                "submission_to_interview": self._rate(
                    len(reached_interview_in_period), len(period_submissions)
                ),
                "interview_to_offer": self._rate(len(offers), len(reached_interview_in_period)),
                "offer_to_placement": self._rate(len(placements), len(offers)),
                "placement_to_paid": self._rate(paid, len(placements)),
            },
        }

    def _recruiting_kpis(self) -> dict[str, float | None]:
        """Etablierte Standard-Recruiting-Kennzahlen ueber den GESAMTEN
        historischen Bestand (nicht auf den period-Zeitraum beschraenkt -
        ein Median ueber nur eine Woche/einen Monat haette zu wenige
        Datenpunkte, um aussagekraeftig zu sein)."""
        all_submissions = {
            row.id: row for row in self.session.scalars(select(CandidateSubmission)).all()
        }
        placements = list(self.session.scalars(select(Placement)).all())

        fill_days = [
            (naive_utc(placement.created_at) - naive_utc(submission.created_at)).days
            for placement in placements
            if (submission := all_submissions.get(placement.submission_id)) is not None
        ]

        # Time-to-Interview: Submission-Erstellung bis zum Activity-Eintrag,
        # der den Uebergang IN "interview" protokolliert (siehe
        # services/submissions.py::transition(), Activity.details ist immer
        # "{alter_status} -> {neuer_status}" mit optionalem ": {grund}"-
        # Suffix nur bei Abbruch/Storno-Transitionen).
        interview_activities = list(
            self.session.scalars(
                select(Activity).where(
                    Activity.activity_type == "submission_status_changed",
                    Activity.details.like("%-> interview"),
                )
            ).all()
        )
        interview_days = [
            (naive_utc(activity.occurred_at) - naive_utc(submission.created_at)).days
            for activity in interview_activities
            if activity.candidate_submission_id is not None
            and (submission := all_submissions.get(activity.candidate_submission_id)) is not None
        ]

        fees = [float(placement.calculated_fee) for placement in placements]

        return {
            "time_to_fill_days": median(fill_days) if fill_days else None,
            "time_to_interview_days": median(interview_days) if interview_days else None,
            "average_fee_per_placement": round(mean(fees), 2) if fees else None,
        }

    def profile_suggestion(self, candidate_id: uuid.UUID) -> str:
        candidate = self.session.get(Candidate, candidate_id)
        if candidate is None:
            from cc_crm.core.errors import EntityNotFoundError

            raise EntityNotFoundError("Candidate not found")
        role = candidate.job_title or "qualifizierte Fachkraft"
        region = candidate.city or candidate.postal_code or "Deutschland"
        parts = [
            f"{candidate.first_name} {candidate.last_name} ist als {role} tätig.",
            f"Der regionale Fokus liegt auf {region}.",
        ]
        if candidate.qualification:
            parts.append(f"Qualifikation: {candidate.qualification}.")
        if candidate.summary:
            parts.append(candidate.summary)
        return " ".join(parts)
