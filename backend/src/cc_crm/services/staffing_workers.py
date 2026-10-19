# NOMICON: Arbeitnehmerüberlassung - nur in der Nomicon-Kopie.
"""Leiharbeitnehmer: ein bestehender Kandidat mit zusätzlichem AÜG-Profil (1:1)."""

import uuid
from datetime import date

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from cc_crm.core.errors import BusinessRuleError, ConflictError, EntityNotFoundError
from cc_crm.models.candidate import Candidate
from cc_crm.models.staffing import StaffingWorker, StaffingWorkerStatus
from cc_crm.models.user import User
from cc_crm.repositories.staffing import StaffingWorkerRepository, WorkerRow
from cc_crm.schemas.staffing import (
    StaffingWorkerCreate,
    StaffingWorkerRead,
    StaffingWorkerUpdate,
)
from cc_crm.services import staffing_audit as audit
from cc_crm.services.engagement_status import require_channel_open  # NOMICON


def worker_read(row: WorkerRow) -> StaffingWorkerRead:
    worker = row.worker
    return StaffingWorkerRead(
        id=worker.id,
        created_at=worker.created_at,
        updated_at=worker.updated_at,
        candidate_id=worker.candidate_id,
        candidate_name=row.candidate_name,
        candidate_number=row.candidate_number,
        status=worker.status,
        entry_date=worker.entry_date,
        exit_date=worker.exit_date,
        hourly_wage=worker.hourly_wage,
        pay_grade=worker.pay_grade,
        weekly_hours=worker.weekly_hours,
        work_permit_valid_until=worker.work_permit_valid_until,
        notes=worker.notes,
    )


def check_status_rule(status: StaffingWorkerStatus, entry_date: date | None, today: date) -> None:
    """Statusregel: Aktiv gibt es erst ab Eintritt/Einsatzbeginn, nie in der Zukunft. Vorher ist die
    Person "In Auswahl" (siehe docs/UEBERLASSUNG.md, Abschnitt "Status eines Leiharbeitnehmers")."""
    if status == StaffingWorkerStatus.ACTIVE and entry_date is not None and entry_date > today:
        raise BusinessRuleError(
            "Ein aktiver Leiharbeitnehmer kann nicht in der Zukunft beginnen. "
            "Bis zum ersten Einsatz bleibt die Person „In Auswahl“."
        )


class StaffingWorkerService:
    def __init__(self, session: Session) -> None:
        self.session = session
        self.workers = StaffingWorkerRepository(session)

    def get_row(self, worker_id: uuid.UUID) -> WorkerRow:
        row = self.workers.row(worker_id)
        if row is None:
            raise EntityNotFoundError("Leiharbeitnehmer nicht gefunden")
        return row

    def row_for_candidate(self, candidate_id: uuid.UUID) -> WorkerRow | None:
        worker = self.workers.by_candidate(candidate_id)
        return None if worker is None else self.workers.row(worker.id)

    def create(self, payload: StaffingWorkerCreate, actor: User) -> WorkerRow:
        candidate = self.session.get(Candidate, payload.candidate_id)
        if candidate is None:
            raise EntityNotFoundError("Kandidat nicht gefunden")
        if candidate.anonymized_at is not None:
            raise BusinessRuleError("Ein anonymisierter Kandidat kann kein Leiharbeitnehmer sein.")
        if self.workers.by_candidate(candidate.id) is not None:
            raise ConflictError("Dieser Kandidat ist bereits als Leiharbeitnehmer angelegt.")
        # NOMICON: Kanal-Freigabe beim Kandidaten (Einwilligung Überlassung)
        require_channel_open(self.session, candidate.id, "staffing")
        values = payload.model_dump()
        check_status_rule(
            values.get("status") or StaffingWorkerStatus.APPLICANT,
            values.get("entry_date"),
            date.today(),
        )
        try:
            worker = self.workers.create(values)
            audit.log_created(self.session, audit.ENTITY_WORKER, worker.id, values, actor.email)
            self.session.commit()
        except IntegrityError as exception:
            self.session.rollback()
            raise ConflictError("Leiharbeitnehmer existiert bereits.") from exception
        return self.get_row(worker.id)

    def update(self, worker_id: uuid.UUID, payload: StaffingWorkerUpdate, actor: User) -> WorkerRow:
        worker = self.get_row(worker_id).worker
        values = payload.model_dump(exclude_unset=True)
        merged_entry = values.get("entry_date", worker.entry_date)
        merged_exit = values.get("exit_date", worker.exit_date)
        if merged_entry and merged_exit and merged_exit < merged_entry:
            raise BusinessRuleError("Austritt liegt vor dem Eintritt.")
        if values.get("status") is None:
            values.pop("status", None)
        check_status_rule(values.get("status", worker.status), merged_entry, date.today())
        audit.log_updated(self.session, audit.ENTITY_WORKER, worker, worker.id, values, actor.email)
        self.workers.update(worker, values)
        self.session.commit()
        return self.get_row(worker.id)

    def rows(
        self, *, status: StaffingWorkerStatus | None = None, offset: int = 0, limit: int = 200
    ) -> list[WorkerRow]:
        return self.workers.rows(status=status, offset=offset, limit=limit)


__all__ = ["StaffingWorker", "StaffingWorkerService", "worker_read"]
