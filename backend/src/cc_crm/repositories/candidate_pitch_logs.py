import uuid
from collections.abc import Sequence
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from cc_crm.models.candidate_pitch_log import CandidatePitchLog
from cc_crm.repositories.base import SQLAlchemyRepository


class CandidatePitchLogRepository(SQLAlchemyRepository[CandidatePitchLog]):
    def __init__(self, session: Session) -> None:
        super().__init__(session, CandidatePitchLog)

    def list_for_candidate(self, candidate_id: uuid.UUID) -> Sequence[CandidatePitchLog]:
        return self.session.scalars(
            select(CandidatePitchLog)
            .where(CandidatePitchLog.candidate_id == candidate_id)
            .order_by(CandidatePitchLog.occurred_at.desc())
        ).all()

    def count_for_candidate(self, candidate_id: uuid.UUID) -> int:
        return (
            self.session.scalar(
                select(func.count())
                .select_from(CandidatePitchLog)
                .where(CandidatePitchLog.candidate_id == candidate_id)
            )
            or 0
        )

    def list_all(
        self,
        *,
        candidate_ids: Sequence[uuid.UUID] | None = None,
    ) -> Sequence[CandidatePitchLog]:
        """Fuer die Analytics-Seite - der Aufrufer (CockpitService.build)
        filtert per naive_utc(item.occurred_at) >= since selbst weiter,
        gleiches Muster wie dort bereits fuer offers/placements/fees.
        `candidate_ids=None` bedeutet "kein Nutzerfilter aktiv" (alle
        Kandidaten), NICHT "keine Kandidaten" - eine leere Sequence wuerde
        stattdessen 0 Ergebnisse liefern, daher die explizite None-
        Unterscheidung."""
        filters = []
        if candidate_ids is not None:
            if not candidate_ids:
                return []
            filters.append(CandidatePitchLog.candidate_id.in_(candidate_ids))
        return self.session.scalars(select(CandidatePitchLog).where(*filters)).all()

    def create_for_candidate(
        self,
        candidate_id: uuid.UUID,
        *,
        occurred_at: datetime,
        notes_text: str | None,
        next_step: str | None,
    ) -> CandidatePitchLog:
        return self.create(
            {
                "candidate_id": candidate_id,
                "occurred_at": occurred_at,
                "notes_text": notes_text,
                "next_step": next_step,
            }
        )
