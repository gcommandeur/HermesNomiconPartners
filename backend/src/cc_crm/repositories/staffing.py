# NOMICON: Arbeitnehmerueberlassung - nur in der Nomicon-Kopie.
"""Abfragen der Arbeitnehmerueberlassung. Namen (Kandidat, Kunde) und Checklisten-Zaehler werden
per JOIN/Unterabfrage mitgeladen, damit Listen keine N+1-Abfragen ausloesen."""

import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date
from typing import Any, cast

from sqlalchemy import Select, func, select
from sqlalchemy.orm import Session

from cc_crm.models.candidate import Candidate
from cc_crm.models.client_company import ClientCompany
from cc_crm.models.staffing import (
    StaffingAssignment,
    StaffingAssignmentStatus,
    StaffingChecklistItem,
    StaffingContract,
    StaffingLicense,
    StaffingWorker,
    StaffingWorkerStatus,
)
from cc_crm.repositories.base import SQLAlchemyRepository


def candidate_display_name(first_name: str | None, last_name: str | None) -> str:
    return f"{first_name or ''} {last_name or ''}".strip() or "Unbekannt"


@dataclass
class WorkerRow:
    worker: StaffingWorker
    candidate_name: str
    candidate_number: str | None


@dataclass
class ContractRow:
    contract: StaffingContract
    client_name: str


@dataclass
class AssignmentRow:
    assignment: StaffingAssignment
    worker_name: str
    client_name: str
    checklist_done: int
    checklist_total: int


class StaffingWorkerRepository(SQLAlchemyRepository[StaffingWorker]):
    def __init__(self, session: Session) -> None:
        super().__init__(session, StaffingWorker)

    @staticmethod
    def _rows_statement() -> Select[Any]:
        return cast(
            "Select[Any]",
            select(
                StaffingWorker,
                Candidate.first_name,
                Candidate.last_name,
                Candidate.candidate_number,
            ).join(Candidate, Candidate.id == StaffingWorker.candidate_id),
        )

    def row(self, worker_id: uuid.UUID) -> WorkerRow | None:
        found = self.session.execute(
            self._rows_statement().where(StaffingWorker.id == worker_id)
        ).first()
        if found is None:
            return None
        return WorkerRow(found[0], candidate_display_name(found[1], found[2]), found[3])

    def rows(
        self, *, status: StaffingWorkerStatus | None = None, offset: int = 0, limit: int = 200
    ) -> list[WorkerRow]:
        statement = self._rows_statement()
        if status is not None:
            statement = statement.where(StaffingWorker.status == status)
        statement = (
            statement.order_by(Candidate.last_name, Candidate.first_name)
            .offset(offset)
            .limit(limit)
        )
        return [
            WorkerRow(r[0], candidate_display_name(r[1], r[2]), r[3])
            for r in self.session.execute(statement).all()
        ]

    def by_candidate(self, candidate_id: uuid.UUID) -> StaffingWorker | None:
        return self.session.scalar(
            select(StaffingWorker).where(StaffingWorker.candidate_id == candidate_id)
        )


class StaffingContractRepository(SQLAlchemyRepository[StaffingContract]):
    def __init__(self, session: Session) -> None:
        super().__init__(session, StaffingContract)

    def row(self, contract_id: uuid.UUID) -> ContractRow | None:
        found = self.session.execute(
            select(StaffingContract, ClientCompany.name)
            .join(ClientCompany, ClientCompany.id == StaffingContract.client_company_id)
            .where(StaffingContract.id == contract_id)
        ).first()
        return None if found is None else ContractRow(found[0], found[1])

    def rows(
        self, *, client_company_id: uuid.UUID | None = None, offset: int = 0, limit: int = 200
    ) -> list[ContractRow]:
        statement = select(StaffingContract, ClientCompany.name).join(
            ClientCompany, ClientCompany.id == StaffingContract.client_company_id
        )
        if client_company_id is not None:
            statement = statement.where(StaffingContract.client_company_id == client_company_id)
        statement = (
            statement.order_by(ClientCompany.name, StaffingContract.valid_from.desc())
            .offset(offset)
            .limit(limit)
        )
        return [ContractRow(r[0], r[1]) for r in self.session.execute(statement).all()]


class StaffingAssignmentRepository(SQLAlchemyRepository[StaffingAssignment]):
    def __init__(self, session: Session) -> None:
        super().__init__(session, StaffingAssignment)

    def _rows_statement(self) -> Select[Any]:
        total = (
            select(func.count(StaffingChecklistItem.id))
            .where(StaffingChecklistItem.assignment_id == StaffingAssignment.id)
            .correlate(StaffingAssignment)
            .scalar_subquery()
        )
        done = (
            select(func.count(StaffingChecklistItem.id))
            .where(
                StaffingChecklistItem.assignment_id == StaffingAssignment.id,
                StaffingChecklistItem.done.is_(True),
            )
            .correlate(StaffingAssignment)
            .scalar_subquery()
        )
        return (
            select(
                StaffingAssignment,
                Candidate.first_name,
                Candidate.last_name,
                ClientCompany.name,
                done,
                total,
            )
            .join(StaffingWorker, StaffingWorker.id == StaffingAssignment.worker_id)
            .join(Candidate, Candidate.id == StaffingWorker.candidate_id)
            .join(ClientCompany, ClientCompany.id == StaffingAssignment.client_company_id)
        )

    @staticmethod
    def _row(found: Sequence[object]) -> AssignmentRow:
        return AssignmentRow(
            assignment=found[0],  # type: ignore[arg-type]
            worker_name=candidate_display_name(found[1], found[2]),  # type: ignore[arg-type]
            client_name=str(found[3]),
            checklist_done=int(found[4] or 0),  # type: ignore[call-overload]
            checklist_total=int(found[5] or 0),  # type: ignore[call-overload]
        )

    def row(self, assignment_id: uuid.UUID) -> AssignmentRow | None:
        found = self.session.execute(
            self._rows_statement().where(StaffingAssignment.id == assignment_id)
        ).first()
        return None if found is None else self._row(found)

    def rows(
        self,
        *,
        owner_scope: list[uuid.UUID] | None = None,
        status: StaffingAssignmentStatus | None = None,
        worker_id: uuid.UUID | None = None,
        client_company_id: uuid.UUID | None = None,
        offset: int = 0,
        limit: int = 200,
    ) -> list[AssignmentRow]:
        """`owner_scope=None` = alles (Admin); sonst nur Einsaetze der genannten Disponenten.
        Einsaetze ohne Disponent sind fuer Nicht-Admins unsichtbar (wie bei Prozessen)."""
        statement = self._rows_statement()
        if owner_scope is not None:
            statement = statement.where(StaffingAssignment.owner_user_id.in_(owner_scope))
        if status is not None:
            statement = statement.where(StaffingAssignment.status == status)
        if worker_id is not None:
            statement = statement.where(StaffingAssignment.worker_id == worker_id)
        if client_company_id is not None:
            statement = statement.where(StaffingAssignment.client_company_id == client_company_id)
        statement = (
            statement.order_by(StaffingAssignment.start_date.desc(), StaffingAssignment.id)
            .offset(offset)
            .limit(limit)
        )
        return [self._row(r) for r in self.session.execute(statement).all()]

    def for_pair(
        self, worker_id: uuid.UUID, client_company_id: uuid.UUID
    ) -> Sequence[StaffingAssignment]:
        """Alle nicht abgebrochenen Einsaetze eines Paares (Grundlage der Fristenberechnung)."""
        return self.session.scalars(
            select(StaffingAssignment)
            .where(
                StaffingAssignment.worker_id == worker_id,
                StaffingAssignment.client_company_id == client_company_id,
                StaffingAssignment.status != StaffingAssignmentStatus.ABORTED,
            )
            .order_by(StaffingAssignment.start_date)
        ).all()

    def checklist(self, assignment_id: uuid.UUID) -> Sequence[StaffingChecklistItem]:
        return self.session.scalars(
            select(StaffingChecklistItem).where(
                StaffingChecklistItem.assignment_id == assignment_id
            )
        ).all()


class StaffingLicenseRepository(SQLAlchemyRepository[StaffingLicense]):
    def __init__(self, session: Session) -> None:
        super().__init__(session, StaffingLicense)

    def ordered(self) -> Sequence[StaffingLicense]:
        return self.session.scalars(
            select(StaffingLicense).order_by(StaffingLicense.valid_from.desc())
        ).all()

    def covering(self, start: date, end: date | None) -> StaffingLicense | None:
        """Erlaubnis, die den gesamten Zeitraum [start, end] abdeckt (end=None: ab start
        offen, dann muss die Erlaubnis unbefristet sein)."""
        for lic in self.ordered():
            if lic.valid_from > start:
                continue
            if lic.valid_to is None:
                return lic
            if end is not None and lic.valid_to >= end:
                return lic
        return None
