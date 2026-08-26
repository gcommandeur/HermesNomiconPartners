import uuid
from collections.abc import Sequence

from sqlalchemy import and_, or_, select
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

    def list_recent(self, *, offset: int = 0, limit: int = 200) -> Sequence[AuditLog]:
        """Neueste Eintraege zuerst - Grundlage der einfachen, chronologischen
        Admin-Log-Ansicht (siehe api/v1/audit_logs.py), keine Filterung noetig."""
        statement = (
            select(AuditLog).order_by(AuditLog.changed_at.desc()).offset(offset).limit(limit)
        )
        return self.session.scalars(statement).all()

    def list_for_candidate(
        self, candidate_id: uuid.UUID, submission_ids: Sequence[uuid.UUID]
    ) -> Sequence[AuditLog]:
        """Aenderungshistorie fuer die Kandidat-Detailseite (Nutzer-Feedback
        "Änderungshistorie im Kandidatenprofil sichtbar machen") - deckt
        sowohl direkt am Kandidaten geloggte Aktionen (entity_type=
        "candidate", z.B. "deleted"/"anonymized") als auch Aktionen an ALLEN
        Prozessen des Kandidaten ab (entity_type="candidate_submission", z.B.
        "status_changed"/"archived") - ohne Letzteres wuerden Statuswechsel,
        die den grossen Teil der Historie ausmachen, komplett fehlen. Neueste
        zuerst."""
        candidate_filter = and_(
            AuditLog.entity_type == "candidate", AuditLog.entity_id == candidate_id
        )
        if submission_ids:
            submission_filter = and_(
                AuditLog.entity_type == "candidate_submission",
                AuditLog.entity_id.in_(submission_ids),
            )
            entity_filter = or_(candidate_filter, submission_filter)
        else:
            entity_filter = candidate_filter
        statement = select(AuditLog).where(entity_filter).order_by(AuditLog.changed_at.desc())
        return self.session.scalars(statement).all()
