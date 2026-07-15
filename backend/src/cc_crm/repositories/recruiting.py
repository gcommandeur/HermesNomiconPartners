import uuid
from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.orm import Session

from cc_crm.models.base import Base
from cc_crm.models.recruiting import (
    AuditLog,
    Fee,
    Interview,
    Offer,
    Placement,
    SubmissionFeedback,
)
from cc_crm.repositories.base import SQLAlchemyRepository


def _list_for_submission[ModelT: Base](
    session: Session, model: type[ModelT], submission_id: uuid.UUID
) -> Sequence[ModelT]:
    statement = select(model).where(
        model.submission_id == submission_id  # type: ignore[attr-defined]
    )
    return session.scalars(statement).all()


class FeedbackRepository(SQLAlchemyRepository[SubmissionFeedback]):
    def __init__(self, session: Session) -> None:
        super().__init__(session, SubmissionFeedback)

    def list_for_submission(self, submission_id: uuid.UUID) -> Sequence[SubmissionFeedback]:
        return _list_for_submission(self.session, SubmissionFeedback, submission_id)


class InterviewRepository(SQLAlchemyRepository[Interview]):
    def __init__(self, session: Session) -> None:
        super().__init__(session, Interview)

    def list_for_submission(self, submission_id: uuid.UUID) -> Sequence[Interview]:
        return _list_for_submission(self.session, Interview, submission_id)


class OfferRepository(SQLAlchemyRepository[Offer]):
    def __init__(self, session: Session) -> None:
        super().__init__(session, Offer)

    def list_for_submission(self, submission_id: uuid.UUID) -> Sequence[Offer]:
        return _list_for_submission(self.session, Offer, submission_id)


class PlacementRepository(SQLAlchemyRepository[Placement]):
    def __init__(self, session: Session) -> None:
        super().__init__(session, Placement)

    def list_for_submission(self, submission_id: uuid.UUID) -> Sequence[Placement]:
        return _list_for_submission(self.session, Placement, submission_id)

    def for_submission(self, submission_id: uuid.UUID) -> Placement | None:
        return self.session.scalar(
            select(Placement).where(Placement.submission_id == submission_id)
        )


class FeeRepository(SQLAlchemyRepository[Fee]):
    def __init__(self, session: Session) -> None:
        super().__init__(session, Fee)


class AuditLogRepository(SQLAlchemyRepository[AuditLog]):
    def __init__(self, session: Session) -> None:
        super().__init__(session, AuditLog)
