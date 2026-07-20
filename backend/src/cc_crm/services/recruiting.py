import logging
import uuid
from datetime import UTC, datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal
from typing import TypeVar

from pydantic import BaseModel
from sqlalchemy.orm import Session

from cc_crm.core.config import get_settings
from cc_crm.core.errors import BusinessRuleError, ConflictError, EntityNotFoundError
from cc_crm.models.base import Base
from cc_crm.models.calendar_event import CalendarEvent
from cc_crm.models.candidate import Candidate
from cc_crm.models.client_company import ClientCompany
from cc_crm.models.enums import CalendarEventType, SubmissionStatus
from cc_crm.models.recruiting import Fee, Interview, Offer, Placement, SubmissionFeedback
from cc_crm.models.submission import CandidateSubmission
from cc_crm.models.user import User
from cc_crm.repositories.activities import ActivityRepository
from cc_crm.repositories.base import SQLAlchemyRepository
from cc_crm.repositories.calendar_events import CalendarEventRepository
from cc_crm.repositories.clients import ClientCompanyRepository
from cc_crm.repositories.recruiting import (
    AuditLogRepository,
    FeedbackRepository,
    FeeRepository,
    InterviewRepository,
    OfferRepository,
    PlacementRepository,
)
from cc_crm.repositories.tasks import TaskRepository
from cc_crm.schemas.recruiting import (
    FeeCreate,
    FeedbackCreate,
    InterviewCreate,
    InterviewUpdate,
    OfferCreate,
    PlacementCreate,
)
from cc_crm.services.submissions import CandidateSubmissionService
from cc_crm.services.warranty import WarrantyService

logger = logging.getLogger(__name__)

MONEY = Decimal("0.01")
INTERVIEW_FOLLOW_UP_TITLE = "Interviewfeedback nachfassen"
# Interviews brauchen in der Regel mehr Vorlauf als ein allgemeiner Termin
# (Unterlagen/Notizen des Kandidaten nochmal durchgehen, Fragen vorbereiten)
# - deshalb 60 statt der sonst ueblichen 30 Minuten Standard-Erinnerung
# (siehe models/calendar_event.py::reminder_minutes_before).
INTERVIEW_CALENDAR_REMINDER_MINUTES = 60
ChildT = TypeVar("ChildT", bound=Base)


class RecruitingProcessService:
    def __init__(self, session: Session) -> None:
        self.session = session
        self.submissions = CandidateSubmissionService(session)
        self.feedback = FeedbackRepository(session)
        self.interviews = InterviewRepository(session)
        self.offers = OfferRepository(session)
        self.placements = PlacementRepository(session)
        self.fees = FeeRepository(session)
        self.activities = ActivityRepository(session)
        self.audit = AuditLogRepository(session)
        self.tasks = TaskRepository(session)
        self.clients = ClientCompanyRepository(session)
        self.warranty = WarrantyService(session)
        self.calendar_events = CalendarEventRepository(session)

    def list_feedback(self, submission_id: uuid.UUID) -> list[SubmissionFeedback]:
        self.submissions.get(submission_id)
        return list(self.feedback.list_for_submission(submission_id))

    def create_feedback(
        self, submission_id: uuid.UUID, payload: FeedbackCreate
    ) -> SubmissionFeedback:
        submission = self.submissions.get(submission_id)
        return self._create_child(
            self.feedback,
            submission,
            payload,
            "feedback_received",
            "Feedback received",
        )

    def list_interviews(self, submission_id: uuid.UUID) -> list[Interview]:
        self.submissions.get(submission_id)
        return list(self.interviews.list_for_submission(submission_id))

    def create_interview(
        self, submission_id: uuid.UUID, payload: InterviewCreate, current_user: User
    ) -> Interview:
        submission = self.submissions.get(submission_id)
        if submission.status != SubmissionStatus.INTERVIEW:
            raise BusinessRuleError("Interview requires the process to be in interview status")
        interview = self._create_child(
            self.interviews,
            submission,
            payload,
            "interview_scheduled",
            "Interview scheduled",
        )
        self._align_interview_follow_up(submission, payload.scheduled_at)
        # Das Interview ist die primaere, wichtige Aktion und ist an dieser
        # Stelle bereits committet - ein Fehler beim (rein begleitenden)
        # Kalendereintrag darf die Interview-Erstellung nicht nachtraeglich
        # scheitern lassen (Nutzer-Vorgabe), deshalb bewusst breit gefangen
        # und nur geloggt statt weitergereicht.
        try:
            self._create_calendar_event_for_interview(interview, submission, current_user)
        except Exception:
            logger.exception(
                "Automatische Kalender-Erstellung fuer Interview %s fehlgeschlagen", interview.id
            )
            self.session.rollback()
        return interview

    def _get_interview(self, submission_id: uuid.UUID, interview_id: uuid.UUID) -> Interview:
        self.submissions.get(submission_id)
        interview = self.interviews.get(interview_id)
        if interview is None or interview.submission_id != submission_id:
            raise EntityNotFoundError("Interview not found")
        return interview

    def update_interview(
        self,
        submission_id: uuid.UUID,
        interview_id: uuid.UUID,
        payload: InterviewUpdate,
    ) -> Interview:
        interview = self._get_interview(submission_id, interview_id)
        values = payload.model_dump(exclude_unset=True)
        updated = self.interviews.update(interview, values)
        self.session.commit()
        # Kalender-Sync-Fehler duerfen die eigentliche Interview-Aktion nicht
        # verhindern (Nutzer-Vorgabe, gleiches Prinzip wie bei create_interview
        # oben) - das Interview-Update selbst ist an dieser Stelle bereits
        # committet.
        if {"scheduled_at", "location_or_link", "notes"} & values.keys():
            try:
                self._sync_calendar_event_for_interview(updated)
            except Exception:
                logger.exception(
                    "Kalender-Sync fuer Interview %s (Update) fehlgeschlagen", updated.id
                )
                self.session.rollback()
        return updated

    def _sync_calendar_event_for_interview(self, interview: Interview) -> None:
        event = self.calendar_events.for_source_interview(interview.id)
        if event is None:
            return
        self.calendar_events.update(
            event,
            {
                "start_at": interview.scheduled_at,
                "location": interview.location_or_link,
                "notes": interview.notes,
            },
        )
        self.session.commit()

    def delete_interview(self, submission_id: uuid.UUID, interview_id: uuid.UUID) -> None:
        interview = self._get_interview(submission_id, interview_id)
        # Verknuepften Kalendereintrag explizit mitloeschen, statt mich allein
        # auf die DB-seitige ON DELETE CASCADE-FK zu verlassen: SQLite (lokale
        # Entwicklung) erzwingt Foreign-Key-Constraints nur bei aktivierter
        # PRAGMA foreign_keys, die hier nicht gesetzt ist (siehe
        # infrastructure/database/session.py) - auf Postgres (Produktion)
        # greift zusaetzlich die FK-Cascade als zweite Absicherung. Gleicher
        # Fehler-Isolations-Grundsatz wie beim Erstellen/Aktualisieren.
        try:
            linked_event = self.calendar_events.for_source_interview(interview.id)
            if linked_event is not None:
                self.calendar_events.delete(linked_event)
                self.session.commit()
        except Exception:
            logger.exception(
                "Loeschen des verknuepften Kalendereintrags fuer Interview %s fehlgeschlagen",
                interview.id,
            )
            self.session.rollback()
        self.interviews.delete(interview)
        self.session.commit()

    def _create_calendar_event_for_interview(
        self, interview: Interview, submission: CandidateSubmission, current_user: User
    ) -> None:
        candidate = self.session.get(Candidate, submission.candidate_id)
        candidate_name = (
            f"{candidate.first_name} {candidate.last_name}" if candidate else "Unbekannt"
        )
        client_name = None
        if submission.client_company_id is not None:
            client = self.session.get(ClientCompany, submission.client_company_id)
            client_name = client.name if client else None
        title = f"Interview: {candidate_name}" + (f" – {client_name}" if client_name else "")

        calendar_event = CalendarEvent(
            title=title,
            event_type=CalendarEventType.INTERVIEW,
            start_at=interview.scheduled_at,
            location=interview.location_or_link,
            notes=interview.notes,
            owner_user_id=current_user.id,
            created_by_user_id=current_user.id,
            candidate_id=submission.candidate_id,
            client_company_id=submission.client_company_id,
            candidate_submission_id=submission.id,
            source_interview_id=interview.id,
            reminder_minutes_before=INTERVIEW_CALENDAR_REMINDER_MINUTES,
        )
        self.session.add(calendar_event)
        self.session.commit()

    def _align_interview_follow_up(
        self, submission: CandidateSubmission, scheduled_at: datetime
    ) -> None:
        """Move the interview follow-up to one day after the actual interview.

        The transition to 'interview' status creates a provisional follow-up
        task dated from the status change, but the interview itself is often
        scheduled days later. Once we know the real scheduled_at, the
        follow-up must move to scheduled_at + 1 day instead.
        """
        due_at = scheduled_at + timedelta(days=1)
        self.submissions.submissions.update(submission, {"follow_up_at": due_at})
        open_task = self.tasks.find_open_by_submission_and_title(
            submission.id, INTERVIEW_FOLLOW_UP_TITLE
        )
        if open_task is not None:
            self.tasks.update(open_task, {"due_at": due_at})
        self.session.commit()

    def list_offers(self, submission_id: uuid.UUID) -> list[Offer]:
        self.submissions.get(submission_id)
        return list(self.offers.list_for_submission(submission_id))

    def create_offer(self, submission_id: uuid.UUID, payload: OfferCreate) -> Offer:
        submission = self.submissions.get(submission_id)
        if submission.status != SubmissionStatus.OFFER:
            raise BusinessRuleError("Offer requires the process to be in offer status")
        return self._create_child(
            self.offers,
            submission,
            payload,
            "offer_received",
            "Offer received",
        )

    def get_placement(self, submission_id: uuid.UUID) -> Placement:
        self.submissions.get(submission_id)
        placement = self.placements.for_submission(submission_id)
        if placement is None:
            raise EntityNotFoundError("Placement not found")
        return placement

    def create_placement(self, submission_id: uuid.UUID, payload: PlacementCreate) -> Placement:
        submission = self.submissions.get(submission_id)
        if submission.status != SubmissionStatus.PLACEMENT:
            raise BusinessRuleError("Placement requires the process to be in placement status")
        if self.placements.for_submission(submission_id) is not None:
            raise ConflictError("Placement already exists")
        fee_percentage = self._resolve_fee_percentage(submission, payload.fee_percentage)
        calculated_fee = (payload.final_salary * fee_percentage / Decimal("100")).quantize(
            MONEY, rounding=ROUND_HALF_UP
        )
        values = payload.model_dump()
        values.update(
            submission_id=submission_id,
            fee_percentage=fee_percentage,
            calculated_fee=calculated_fee,
        )
        placement = self.placements.create(values)
        self.warranty.schedule_follow_up(placement, submission)
        self._event(
            submission,
            "placement_created",
            "Placement created",
            {"fee_percentage": str(fee_percentage), "calculated_fee": str(calculated_fee)},
        )
        self.session.commit()
        return placement

    def _resolve_fee_percentage(
        self, submission: CandidateSubmission, requested: Decimal | None
    ) -> Decimal:
        """Fee percentage precedence: explicit request > submission-level
        override (e.g. individually negotiated) > the Kanzlei's own default
        (ClientCompany.fee_percentage, 27% unless overridden). This is what
        keeps the 27%-Kanzleihonorar flowing through to Placement without
        every caller having to know and repeat it.
        """
        if requested is not None:
            return requested
        if submission.fee_percentage is not None:
            return submission.fee_percentage
        if submission.client_company_id is not None:
            client = self.clients.get(submission.client_company_id)
            if client is not None:
                return client.fee_percentage
        raise BusinessRuleError(
            "fee_percentage was not provided and no Kanzlei default is available"
        )

    def create_fee(self, placement_id: uuid.UUID, payload: FeeCreate) -> Fee:
        placement = self.placements.get(placement_id)
        if placement is None:
            raise EntityNotFoundError("Placement not found")
        vat_rate = payload.vat_rate
        if vat_rate is None:
            vat_rate = get_settings().default_vat_rate
        amount_gross = (payload.amount_net * (Decimal("1") + vat_rate / Decimal("100"))).quantize(
            MONEY, rounding=ROUND_HALF_UP
        )
        values = payload.model_dump(exclude={"vat_rate"})
        values.update(
            placement_id=placement_id,
            vat_rate=vat_rate,
            amount_gross=amount_gross,
        )
        fee = self.fees.create(values)
        submission = self.submissions.get(placement.submission_id)
        self._event(
            submission,
            "fee_calculated",
            "Fee calculated",
            {"amount_net": str(fee.amount_net), "amount_gross": str(amount_gross)},
        )
        self.session.commit()
        return fee

    def _create_child(
        self,
        repository: SQLAlchemyRepository[ChildT],
        submission: CandidateSubmission,
        payload: BaseModel,
        activity_type: str,
        subject: str,
        *,
        commit: bool = True,
    ) -> ChildT:
        values = payload.model_dump()
        values["submission_id"] = submission.id
        entity = repository.create(values)
        self._event(submission, activity_type, subject, {})
        if commit:
            self.session.commit()
        return entity

    def _event(
        self,
        submission: CandidateSubmission,
        activity_type: str,
        subject: str,
        new_values: dict[str, object],
    ) -> None:
        now = datetime.now(UTC)
        self.activities.create(
            {
                "candidate_id": submission.candidate_id,
                "client_company_id": submission.client_company_id,
                "candidate_submission_id": submission.id,
                "activity_type": activity_type,
                "subject": subject,
                "occurred_at": now,
            }
        )
        self.audit.create(
            {
                "entity_type": "candidate_submission",
                "entity_id": submission.id,
                "action": activity_type,
                "changed_at": now,
                "new_values": new_values,
            }
        )
