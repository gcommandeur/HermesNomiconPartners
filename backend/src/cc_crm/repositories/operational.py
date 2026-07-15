import uuid
from collections.abc import Sequence
from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from cc_crm.models.operational import Document, EmailDraftLog, SourcingMetric
from cc_crm.repositories.base import SQLAlchemyRepository


class DocumentRepository(SQLAlchemyRepository[Document]):
    def __init__(self, session: Session) -> None:
        super().__init__(session, Document)

    def filtered(
        self,
        *,
        owner_type: str | None = None,
        owner_id: uuid.UUID | None = None,
        offset: int = 0,
        limit: int = 100,
    ) -> Sequence[Document]:
        filters = []
        if owner_type is not None:
            filters.append(Document.owner_type == owner_type)
        if owner_id is not None:
            filters.append(Document.owner_id == owner_id)
        statement = (
            select(Document)
            .where(*filters)
            .order_by(Document.created_at.desc())
            .offset(offset)
            .limit(limit)
        )
        return self.session.scalars(statement).all()


class SourcingMetricRepository(SQLAlchemyRepository[SourcingMetric]):
    def __init__(self, session: Session) -> None:
        super().__init__(session, SourcingMetric)

    def in_period(self, period_start: date, period_end: date) -> Sequence[SourcingMetric]:
        """Alle Erfassungen, deren Zeitraum den angefragten Zeitraum
        ueberschneidet (Basis fuer die Funnel-Aggregation)."""
        statement = select(SourcingMetric).where(
            SourcingMetric.period_start <= period_end,
            SourcingMetric.period_end >= period_start,
        )
        return self.session.scalars(statement).all()


class EmailDraftRepository(SQLAlchemyRepository[EmailDraftLog]):
    def __init__(self, session: Session) -> None:
        super().__init__(session, EmailDraftLog)
