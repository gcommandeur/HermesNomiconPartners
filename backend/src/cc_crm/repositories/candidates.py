import uuid
from collections.abc import Sequence
from datetime import date, datetime
from typing import Any

from sqlalchemy import ColumnElement, Integer, cast, func, or_, select
from sqlalchemy.orm import Session

from cc_crm.models.candidate import Candidate
from cc_crm.models.enums import CandidateStatus, SubmissionCancellationReason
from cc_crm.models.submission import CandidateSubmission
from cc_crm.repositories.base import SQLAlchemyRepository

# Dieselben Spalten wie SORT_ACCESSORS in candidates-table.tsx - Sortierung
# muss ueber den gesamten Bestand laufen (ORDER BY), nicht nur ueber die
# aktuell geladene Seite (siehe Kandidaten-Sortier-Bug: bei 30k+ Kandidaten
# sortierte ein Klick auf "Name" bislang nur innerhalb der sichtbaren Zeile).
# candidate_number wird auf Integer gecastet, damit "99" vor "100" einsortiert
# wird statt lexikografisch danach - Kandidatennummern sind durchgehend
# numerische Strings (siehe models/candidate.py::candidate_number).
_SORT_COLUMNS: dict[str, Any] = {
    "candidate_number": cast(Candidate.candidate_number, Integer),
    "name": (Candidate.last_name, Candidate.first_name),
    "job_title": Candidate.job_title,
    "city": func.coalesce(Candidate.city, Candidate.postal_code),
    "salary_expectation": Candidate.salary_expectation,
    "status": Candidate.status,
}


def _order_by_clauses(sort_by: str | None, sort_dir: str) -> list[ColumnElement[Any]]:
    descending = sort_dir == "desc"
    columns: Any = _SORT_COLUMNS.get(sort_by) if sort_by else None
    resolved: tuple[Any, ...]
    if columns is None:
        resolved = (Candidate.last_name, Candidate.first_name)
    elif isinstance(columns, tuple):
        resolved = columns
    else:
        resolved = (columns,)
    return [column.desc() if descending else column.asc() for column in resolved]


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
        sort_by: str | None = None,
        sort_dir: str = "asc",
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
            .order_by(*_order_by_clauses(sort_by, sort_dir))
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
