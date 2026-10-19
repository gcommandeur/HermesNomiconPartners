# NOMICON: Arbeitnehmerüberlassung - nur in der Nomicon-Kopie.
"""Bestätigung "Keine Vorzeiten": geprüft, dass es beim Kunden keine früheren Zeiten gab.

Ohne Eintrag ist nicht erkennbar, ob "keine Vorzeiten" geprüft oder nur nicht erfasst wurden. Mit
Bestätigung (oder mit erfassten Vorzeiten) ist die Frist nicht mehr vorläufig; ohne beides bleibt
sie es ("Vorzeiten nicht bestätigt", `staffing_deadline_job.pair_deadline`). Gleiche Rechte wie die
Vorzeiten selbst (gemeinsamer Pool wie die Person); weder Lohn noch Marge. Zurücknehmen ist erlaubt
(Eingabekorrektur) und wird wie das Bestätigen protokolliert."""

import uuid
from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from cc_crm.core.errors import BusinessRuleError, ConflictError, EntityNotFoundError
from cc_crm.models.client_company import ClientCompany
from cc_crm.models.staffing import (
    StaffingPriorPeriod,
    StaffingPriorPeriodConfirmation,
    StaffingWorker,
)
from cc_crm.models.user import User
from cc_crm.schemas.staffing import (
    StaffingPriorPeriodConfirmationCreate,
    StaffingPriorPeriodConfirmationRead,
)
from cc_crm.services import staffing_audit as audit


def pair_prior_confirmed(
    session: Session, worker_id: uuid.UUID, client_company_id: uuid.UUID
) -> bool:
    """Ob für das Paar "keine Vorzeiten" bestätigt wurde."""
    return (
        session.scalar(
            select(StaffingPriorPeriodConfirmation.id).where(
                StaffingPriorPeriodConfirmation.worker_id == worker_id,
                StaffingPriorPeriodConfirmation.client_company_id == client_company_id,
            )
        )
        is not None
    )


def pair_has_prior_periods(
    session: Session, worker_id: uuid.UUID, client_company_id: uuid.UUID
) -> bool:
    return (
        session.scalar(
            select(StaffingPriorPeriod.id)
            .where(
                StaffingPriorPeriod.worker_id == worker_id,
                StaffingPriorPeriod.client_company_id == client_company_id,
            )
            .limit(1)
        )
        is not None
    )


def _read(
    row: StaffingPriorPeriodConfirmation, client_name: str, user_name: str | None
) -> StaffingPriorPeriodConfirmationRead:
    return StaffingPriorPeriodConfirmationRead(
        id=row.id,
        created_at=row.created_at,
        updated_at=row.updated_at,
        worker_id=row.worker_id,
        client_company_id=row.client_company_id,
        client_name=client_name,
        confirmed_on=row.confirmed_on,
        confirmed_by_user_id=row.confirmed_by_user_id,
        confirmed_by_name=user_name,
        note=row.note,
    )


class StaffingPriorConfirmationService:
    def __init__(self, session: Session) -> None:
        self.session = session

    def _check_worker(self, worker_id: uuid.UUID) -> None:
        if self.session.get(StaffingWorker, worker_id) is None:
            raise EntityNotFoundError("Leiharbeitnehmer nicht gefunden")

    def _client_name(self, client_company_id: uuid.UUID) -> str:
        name = self.session.scalar(
            select(ClientCompany.name).where(ClientCompany.id == client_company_id)
        )
        if name is None:
            raise EntityNotFoundError("Kunde nicht gefunden")
        return name

    def _find(
        self, worker_id: uuid.UUID, client_company_id: uuid.UUID
    ) -> StaffingPriorPeriodConfirmation | None:
        return self.session.scalar(
            select(StaffingPriorPeriodConfirmation).where(
                StaffingPriorPeriodConfirmation.worker_id == worker_id,
                StaffingPriorPeriodConfirmation.client_company_id == client_company_id,
            )
        )

    def list_for_worker(self, worker_id: uuid.UUID) -> list[StaffingPriorPeriodConfirmationRead]:
        self._check_worker(worker_id)
        rows = self.session.execute(
            select(StaffingPriorPeriodConfirmation, ClientCompany.name, User.display_name)
            .join(
                ClientCompany, ClientCompany.id == StaffingPriorPeriodConfirmation.client_company_id
            )
            .outerjoin(User, User.id == StaffingPriorPeriodConfirmation.confirmed_by_user_id)
            .where(StaffingPriorPeriodConfirmation.worker_id == worker_id)
            .order_by(ClientCompany.name, StaffingPriorPeriodConfirmation.id)
        ).all()
        return [_read(row[0], row[1], row[2]) for row in rows]

    def confirm(
        self,
        worker_id: uuid.UUID,
        payload: StaffingPriorPeriodConfirmationCreate,
        actor: User,
        today: date | None = None,
    ) -> StaffingPriorPeriodConfirmationRead:
        self._check_worker(worker_id)
        client_name = self._client_name(payload.client_company_id)
        day = today or date.today()
        on = payload.confirmed_on or day
        if on > day:
            raise BusinessRuleError("Die Bestätigung kann nicht in der Zukunft liegen.")
        if pair_has_prior_periods(self.session, worker_id, payload.client_company_id):
            raise ConflictError(
                'Für dieses Paar sind bereits Vorzeiten erfasst; "Keine Vorzeiten" passt nicht.'
            )
        row = self._find(worker_id, payload.client_company_id)
        values = {"confirmed_on": on, "confirmed_by_user_id": actor.id, "note": payload.note}
        if row is None:
            row = StaffingPriorPeriodConfirmation(
                worker_id=worker_id, client_company_id=payload.client_company_id, **values
            )
            self.session.add(row)
            self.session.flush()
            audit.log_created(
                self.session,
                audit.ENTITY_PRIOR_CONFIRMATION,
                row.id,
                {"worker_id": worker_id, "client_company_id": payload.client_company_id, **values},
                actor.email,
            )
        else:
            audit.log_updated(
                self.session,
                audit.ENTITY_PRIOR_CONFIRMATION,
                row,
                row.id,
                values,
                actor.email,
            )
            for field, value in values.items():
                setattr(row, field, value)
        self.session.commit()
        return _read(row, client_name, actor.display_name)

    def withdraw(self, worker_id: uuid.UUID, client_company_id: uuid.UUID, actor: User) -> None:
        self._check_worker(worker_id)
        row = self._find(worker_id, client_company_id)
        if row is None:
            raise EntityNotFoundError("Bestätigung nicht gefunden")
        audit.log_event(
            self.session,
            audit.ENTITY_PRIOR_CONFIRMATION,
            row.id,
            "deleted",
            actor.email,
            {
                "worker_id": worker_id,
                "client_company_id": client_company_id,
                "confirmed_on": row.confirmed_on,
            },
        )
        self.session.delete(row)
        self.session.commit()
