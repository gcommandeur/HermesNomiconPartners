import uuid
from datetime import UTC, datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal
from typing import TypeVar

from pydantic import BaseModel
from sqlalchemy.orm import Session

from cc_crm.core.config import get_settings
from cc_crm.core.errors import BusinessRuleError, ConflictError, EntityNotFoundError
from cc_crm.models.base import Base
from cc_crm.models.enums import SubmissionStatus
from cc_crm.models.recruiting import Fee, Interview, Offer, Placement, SubmissionFeedback
from cc_crm.models.submission import CandidateSubmission
from cc_crm.repositories.activities import ActivityRepository
from cc_crm.repositories.base import SQLAlchemyRepository
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
    OfferCreate,
    PlacementCreate,
)
from cc_crm.services.submissions import CandidateSubmissionService
from cc_crm.services.warranty import WarrantyService

MONEY = Decimal("0.01")
INTERVIEW_FOLLOW_UP_TITLE = "Interviewfeedback nachfassen"
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

    def create_interview(self, submission_id: uuid.UUID, payload: InterviewCreate) -> Interview:
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
        return interview

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
