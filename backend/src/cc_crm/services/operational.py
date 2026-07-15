import uuid
from datetime import UTC, date, datetime, timedelta

from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from cc_crm.core.errors import ConflictError
from cc_crm.core.time import naive_utc
from cc_crm.models.candidate import Candidate
from cc_crm.models.client_company import ClientCompany
from cc_crm.models.enums import InvoiceStatus, SubmissionStatus, TaskStatus
from cc_crm.models.operational import Document, EmailDraftLog, SourcingMetric
from cc_crm.models.recruiting import Fee, Offer, Placement
from cc_crm.models.submission import CandidateSubmission
from cc_crm.models.task import Task
from cc_crm.repositories.operational import (
    DocumentRepository,
    EmailDraftRepository,
    SourcingMetricRepository,
)
from cc_crm.schemas.operational import (
    DocumentCreate,
    EmailDraftCreate,
    SourcingMetricCreate,
)
from cc_crm.services.base import CrudService
from cc_crm.services.storage import has_generic_filename


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
    TEMPLATES = [
        ("candidate_submission", "Kandidat vorstellen", "Profil: {candidate} – {role}"),
        ("request_cv", "CV nachfordern", "Unterlagen zu Ihrem Profil"),
        ("profile_approval", "Kurzprofil freigeben", "Freigabe Ihres Kurzprofils"),
        ("submission_follow_up", "CV-Out nachfassen", "Feedback zu {candidate}"),
        ("interview_confirmation", "Interview bestätigen", "Interview bei {client}"),
        ("interview_feedback", "Interviewfeedback nachfassen", "Feedback zum Interview"),
        ("offer_follow_up", "Offer nachfassen", "Abstimmung zum Angebot"),
        ("candidate_rejection", "Absage Kandidat", "Rückmeldung zum Prozess"),
        ("client_rejection", "Absage Kunde", "Rückmeldung zu {candidate}"),
        ("send_terms", "AGB senden", "Zusammenarbeit mit CC"),
        ("placement_invoice", "Placement / Rechnung", "Erfolgreiche Besetzung"),
    ]

    def __init__(self, session: Session) -> None:
        self.session = session
        self.drafts = EmailDraftRepository(session)

    def templates(self) -> list[dict[str, object]]:
        placeholders = [
            "candidate",
            "client",
            "contact",
            "role",
            "salary",
            "notice_period",
            "short_profile",
            "next_step",
        ]
        return [
            {
                "key": key,
                "name": name,
                "subject": subject,
                "body": (
                    "Guten Tag {contact},\n\n{short_profile}\n\n"
                    "Nächster Schritt: {next_step}\n\nBeste Grüße"
                ),
                "placeholders": placeholders,
            }
            for key, name, subject in self.TEMPLATES
        ]

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

    def build(self, period: str) -> dict[str, object]:
        now = naive_utc(datetime.now(UTC))
        since = now - timedelta(days={"week": 7, "month": 30, "quarter": 90}.get(period, 7))
        due_soon = now + timedelta(days=1)
        submissions = list(self.session.scalars(select(CandidateSubmission)).all())
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
        # Nutzer-Feedback 2026-07-15). "Interviews" zaehlt deshalb jetzt den
        # echten, aktuellen Submission-Status - konsistent mit dem Kanban.
        interviews_in_progress = [
            item for item in submissions if item.status == SubmissionStatus.INTERVIEW
        ]
        reached_interview_stage = {
            SubmissionStatus.INTERVIEW,
            SubmissionStatus.OFFER,
            SubmissionStatus.PLACEMENT,
        }
        offers = [
            item
            for item in self.session.scalars(select(Offer)).all()
            if naive_utc(item.created_at) >= since
        ]
        placements = [
            item
            for item in self.session.scalars(select(Placement)).all()
            if naive_utc(item.created_at) >= since
        ]
        fees = [
            item
            for item in self.session.scalars(select(Fee)).all()
            if naive_utc(item.created_at) >= since
        ]
        period_submissions = [item for item in submissions if naive_utc(item.created_at) >= since]
        due_tasks = [
            task for task in tasks if task.due_at is None or naive_utc(task.due_at) <= due_soon
        ]
        hot_submissions = [item for item in submissions if item.status in self.HOT]

        # Namen fuer Kandidat/Kanzlei in einem Bulk-Query je Entitaet statt pro
        # Zeile nachzuladen (kein ORM relationship() in diesem Codebase, daher
        # kein selectinload moeglich - bulk IN-Query erreicht denselben Zweck:
        # konstante statt mit der Datenmenge wachsende Query-Anzahl).
        candidate_ids = {task.candidate_id for task in due_tasks if task.candidate_id} | {
            item.candidate_id for item in hot_submissions
        }
        client_ids = {task.client_company_id for task in due_tasks if task.client_company_id} | {
            item.client_company_id for item in hot_submissions if item.client_company_id
        }
        candidate_names = self._candidate_names(candidate_ids)
        client_names = self._client_names(client_ids)

        important = [
            {
                "kind": "task",
                "title": task.title,
                "detail": " — ".join(
                    filter(
                        None,
                        [
                            candidate_names.get(task.candidate_id) if task.candidate_id else None,
                            client_names.get(task.client_company_id)
                            if task.client_company_id
                            else None,
                            task.description or "Offene Aufgabe",
                        ],
                    )
                ),
                "due_at": task.due_at,
                "candidate_id": task.candidate_id,
                "client_company_id": task.client_company_id,
                "submission_id": task.candidate_submission_id,
                "priority": task.priority.value,
            }
            for task in due_tasks
        ]
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
        paid = sum(1 for fee in fees if fee.invoice_status == InvoiceStatus.PAID)
        expected = sum(float(item.expected_fee or 0) for item in submissions)
        realized = sum(
            float(fee.amount_net) for fee in fees if fee.invoice_status == InvoiceStatus.PAID
        )
        cv_count = (
            self.session.scalar(
                select(func.count())
                .select_from(Candidate)
                .where(Candidate.cv_in_recorded_at.isnot(None))
            )
            or 0
        )
        reached_interview_in_period = [
            item for item in period_submissions if item.status in reached_interview_stage
        ]
        sourcing = SourcingMetricService(self.session).totals_for_period(since.date(), now.date())
        return {
            "period": period,
            "important": important,
            "hot_processes": hot,
            "sourcing": sourcing,
            "kpis": {
                "qualification_calls": len(period_submissions),
                "cv_available": cv_count,
                "submissions": len(period_submissions),
                "interviews": len(interviews_in_progress),
                "offers": len(offers),
                "placements": len(placements),
                "expected_fees": expected,
                "realized_fees": realized,
            },
            "rates": {
                "submission_to_interview": self._rate(
                    len(reached_interview_in_period), len(period_submissions)
                ),
                "interview_to_offer": self._rate(len(offers), len(reached_interview_in_period)),
                "offer_to_placement": self._rate(len(placements), len(offers)),
                "placement_to_paid": self._rate(paid, len(placements)),
            },
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
