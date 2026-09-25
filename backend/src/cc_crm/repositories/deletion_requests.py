"""Repository fuer die Loeschanfragen-Nachverfolgung (Art. 17 DSGVO,
Punkt 3 des Auftrags "5 Hoch-Punkte umsetzen") - siehe
services/deletion_requests.py fuer die eigentliche Logik."""

from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.orm import Session

from cc_crm.models.deletion_request import DeletionRequest
from cc_crm.repositories.base import SQLAlchemyRepository


class DeletionRequestRepository(SQLAlchemyRepository[DeletionRequest]):
    def __init__(self, session: Session) -> None:
        super().__init__(session, DeletionRequest)

    def list_open(self) -> Sequence[DeletionRequest]:
        """Offene (noch nicht erledigte) Loeschanfragen, nach Deadline
        aufsteigend sortiert - Grundlage der Admin-Liste "X Tage
        verbleibend"/ueberfaellig, dringendste zuerst."""
        statement = (
            select(DeletionRequest)
            .where(DeletionRequest.completed_at.is_(None))
            .order_by(DeletionRequest.deadline.asc())
        )
        return self.session.scalars(statement).all()

    def list_all(self) -> Sequence[DeletionRequest]:
        statement = select(DeletionRequest).order_by(DeletionRequest.requested_at.desc())
        return self.session.scalars(statement).all()
