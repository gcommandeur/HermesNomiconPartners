import uuid
from collections.abc import Sequence
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from cc_crm.models.enums import SubmissionStatus
from cc_crm.models.submission import CandidateSubmission
from cc_crm.repositories.base import SQLAlchemyRepository

ACTIVE_SUBMISSION_STATUSES = {
    SubmissionStatus.QUALIFICATION_CALL,
    SubmissionStatus.CV_IN,
    SubmissionStatus.CV_OUT,
    SubmissionStatus.INTERVIEW,
    SubmissionStatus.OFFER,
}


class CandidateSubmissionRepository(SQLAlchemyRepository[CandidateSubmission]):
    def __init__(self, session: Session) -> None:
        super().__init__(session, CandidateSubmission)

    def list_for_candidate(
        self,
        candidate_id: uuid.UUID,
        *,
        offset: int = 0,
        limit: int = 100,
    ) -> Sequence[CandidateSubmission]:
        statement = (
            select(CandidateSubmission)
            .where(CandidateSubmission.candidate_id == candidate_id)
            .offset(offset)
            .limit(limit)
        )
        return self.session.scalars(statement).all()

    def find_active_duplicate(
        self,
        *,
        candidate_id: uuid.UUID,
        client_company_id: uuid.UUID | None,
        job_mandate_id: uuid.UUID | None,
    ) -> CandidateSubmission | None:
        statement = select(CandidateSubmission).where(
            CandidateSubmission.candidate_id == candidate_id,
            CandidateSubmission.status.in_(ACTIVE_SUBMISSION_STATUSES),
        )
        if client_company_id is None:
            statement = statement.where(CandidateSubmission.client_company_id.is_(None))
        else:
            statement = statement.where(CandidateSubmission.client_company_id == client_company_id)
        if job_mandate_id is None:
            statement = statement.where(CandidateSubmission.job_mandate_id.is_(None))
        else:
            statement = statement.where(CandidateSubmission.job_mandate_id == job_mandate_id)
        return self.session.scalar(statement.limit(1))

    def priority_candidates(self) -> Sequence[CandidateSubmission]:
        """Offene Prozesse mit bereits berechnetem Closing-Score, sortiert nach
        closing_probability * erwartetem Honorar (absteigend) - Basis der
        Prioritaetsansicht."""
        statement = select(CandidateSubmission).where(
            CandidateSubmission.status.in_(ACTIVE_SUBMISSION_STATUSES),
            CandidateSubmission.closing_probability.isnot(None),
        )
        submissions = self.session.scalars(statement).all()

        def score(submission: CandidateSubmission) -> float:
            probability = submission.closing_probability or 0.0
            fee = float(submission.expected_fee or 0)
            return probability * fee

        return sorted(submissions, key=score, reverse=True)

    def filtered(
        self,
        *,
        status: SubmissionStatus | None = None,
        candidate_id: uuid.UUID | None = None,
        client_id: uuid.UUID | None = None,
        job_id: uuid.UUID | None = None,
        owner_user_id: uuid.UUID | None = None,
        created_from: datetime | None = None,
        created_to: datetime | None = None,
        offset: int = 0,
        limit: int = 100,
    ) -> tuple[Sequence[CandidateSubmission], int]:
        filters = []
        if status is not None:
            filters.append(CandidateSubmission.status == status)
        if candidate_id is not None:
            filters.append(CandidateSubmission.candidate_id == candidate_id)
        if client_id is not None:
            filters.append(CandidateSubmission.client_company_id == client_id)
        if job_id is not None:
            filters.append(CandidateSubmission.job_mandate_id == job_id)
        if owner_user_id is not None:
            filters.append(CandidateSubmission.owner_user_id == owner_user_id)
        if created_from is not None:
            filters.append(CandidateSubmission.created_at >= created_from)
        if created_to is not None:
            filters.append(CandidateSubmission.created_at <= created_to)
        statement = (
            select(CandidateSubmission)
            .where(*filters)
            .order_by(CandidateSubmission.created_at.desc())
            .offset(offset)
            .limit(limit)
        )
        count_statement = select(func.count()).select_from(CandidateSubmission).where(*filters)
        return self.session.scalars(statement).all(), int(self.session.scalar(count_statement) or 0)
