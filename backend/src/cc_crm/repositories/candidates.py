import uuid
from collections.abc import Sequence
from datetime import date, datetime

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from cc_crm.models.candidate import Candidate
from cc_crm.models.enums import CandidateStatus, SubmissionCancellationReason
from cc_crm.models.submission import CandidateSubmission
from cc_crm.repositories.base import SQLAlchemyRepository


class CandidateRepository(SQLAlchemyRepository[Candidate]):
    def __init__(self, session: Session) -> None:
        super().__init__(session, Candidate)

    def filtered(
        self,
        *,
        status: CandidateStatus | None = None,
        role: str | None = None,
        region: str | None = None,
        search: str | None = None,
        owner_user_id: uuid.UUID | None = None,
        created_from: datetime | None = None,
        created_to: datetime | None = None,
        offset: int = 0,
        limit: int = 100,
    ) -> tuple[Sequence[Candidate], int]:
        filters = []
        if status is not None:
            filters.append(Candidate.status == status)
        if owner_user_id is not None:
            filters.append(Candidate.owner_user_id == owner_user_id)
        if role:
            filters.append(Candidate.job_title.ilike(f"%{role}%"))
        if region:
            filters.append(
                or_(Candidate.city.ilike(f"%{region}%"), Candidate.postal_code.ilike(f"%{region}%"))
            )
        if search:
            term = f"%{search}%"
            filters.append(
                or_(
                    Candidate.first_name.ilike(term),
                    Candidate.last_name.ilike(term),
                    Candidate.email.ilike(term),
                    Candidate.job_title.ilike(term),
                    Candidate.candidate_number.ilike(term),
                )
            )
        if created_from:
            filters.append(Candidate.created_at >= created_from)
        if created_to:
            filters.append(Candidate.created_at <= created_to)
        query = (
            select(Candidate)
            .where(*filters)
            .order_by(Candidate.last_name, Candidate.first_name)
            .offset(offset)
            .limit(limit)
        )
        count = select(func.count()).select_from(Candidate).where(*filters)
        return self.session.scalars(query).all(), int(self.session.scalar(count) or 0)

    def ghosting_candidate_ids(self, candidate_ids: Sequence[uuid.UUID]) -> set[uuid.UUID]:
        """IDs aus candidate_ids, die mindestens eine mit candidate_ghosting
        abgebrochene Submission haben (Basis für den Ghosting-Badge)."""
        if not candidate_ids:
            return set()
        rows = self.session.scalars(
            select(CandidateSubmission.candidate_id)
            .where(
                CandidateSubmission.candidate_id.in_(candidate_ids),
                CandidateSubmission.cancellation_reason
                == SubmissionCancellationReason.CANDIDATE_GHOSTING,
            )
            .distinct()
        ).all()
        return set(rows)

    def stale_contacts(self, threshold_date: date) -> Sequence[Candidate]:
        """Kandidaten mit einem gesetzten last_contact_at, das älter als
        threshold_date ist, sortiert nach längster Inaktivität zuerst -
        Grundlage der Reaktivierungsliste."""
        query = (
            select(Candidate)
            .where(
                Candidate.last_contact_at.isnot(None),
                Candidate.last_contact_at < threshold_date,
            )
            .order_by(Candidate.last_contact_at.asc())
        )
        return self.session.scalars(query).all()
