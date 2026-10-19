# NOMICON: Arbeitnehmerüberlassung - nur in der Nomicon-Kopie.
"""Vorzeiten beim Kunden: früher geleistete Überlassungszeiten (anderer Verleiher, vor CRM-Start).

Sie fließen in `pair_deadline` ein (services/staffing_deadline_job.py) und zählen dort wie
Einsätze für Höchstdauer und Equal Pay (Annahme, kein Rechtsrat). Vorzeiten sind immer
abgeschlossen und tragen keine Lohn- oder Margenwerte. Löschen ist erlaubt (Eingabekorrektur) und
wird protokolliert."""

import uuid
from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from cc_crm.core.errors import BusinessRuleError, EntityNotFoundError
from cc_crm.models.client_company import ClientCompany
from cc_crm.models.staffing import StaffingPriorPeriod, StaffingWorker
from cc_crm.models.user import User
from cc_crm.schemas.staffing import (
    StaffingPriorPeriodCreate,
    StaffingPriorPeriodRead,
    StaffingPriorPeriodUpdate,
)
from cc_crm.services import staffing_audit as audit


def prior_period_read(period: StaffingPriorPeriod, client_name: str) -> StaffingPriorPeriodRead:
    return StaffingPriorPeriodRead(
        id=period.id,
        created_at=period.created_at,
        updated_at=period.updated_at,
        worker_id=period.worker_id,
        client_company_id=period.client_company_id,
        client_name=client_name,
        start_date=period.start_date,
        end_date=period.end_date,
        source=period.source,
        note=period.note,
        created_by_user_id=period.created_by_user_id,
    )


def _check_closed(start: date, end: date, today: date) -> None:
    if end < start:
        raise BusinessRuleError("Das Ende liegt vor dem Beginn.")
    if end > today:
        raise BusinessRuleError(
            "Eine Vorzeit ist ein abgeschlossener Zeitraum und kann nicht in der Zukunft enden. "
            "Laufende Zeiten gehören in einen Einsatz."
        )


class StaffingPriorPeriodService:
    def __init__(self, session: Session) -> None:
        self.session = session

    def _client_name(self, client_company_id: uuid.UUID) -> str:
        name = self.session.scalar(
            select(ClientCompany.name).where(ClientCompany.id == client_company_id)
        )
        if name is None:
            raise EntityNotFoundError("Kunde nicht gefunden")
        return name

    def _get(self, period_id: uuid.UUID) -> StaffingPriorPeriod:
        period = self.session.get(StaffingPriorPeriod, period_id)
        if period is None:
            raise EntityNotFoundError("Vorzeit nicht gefunden")
        return period

    def list_for_worker(self, worker_id: uuid.UUID) -> list[StaffingPriorPeriodRead]:
        if self.session.get(StaffingWorker, worker_id) is None:
            raise EntityNotFoundError("Leiharbeitnehmer nicht gefunden")
        rows = self.session.execute(
            select(StaffingPriorPeriod, ClientCompany.name)
            .join(ClientCompany, ClientCompany.id == StaffingPriorPeriod.client_company_id)
            .where(StaffingPriorPeriod.worker_id == worker_id)
            .order_by(StaffingPriorPeriod.start_date.desc(), StaffingPriorPeriod.id)
        ).all()
        return [prior_period_read(row[0], row[1]) for row in rows]

    def create(
        self,
        worker_id: uuid.UUID,
        payload: StaffingPriorPeriodCreate,
        actor: User,
        today: date | None = None,
    ) -> StaffingPriorPeriodRead:
        if self.session.get(StaffingWorker, worker_id) is None:
            raise EntityNotFoundError("Leiharbeitnehmer nicht gefunden")
        client_name = self._client_name(payload.client_company_id)
        _check_closed(payload.start_date, payload.end_date, today or date.today())
        period = StaffingPriorPeriod(
            worker_id=worker_id, created_by_user_id=actor.id, **payload.model_dump()
        )
        self.session.add(period)
        self.session.flush()
        audit.log_created(
            self.session,
            audit.ENTITY_PRIOR_PERIOD,
            period.id,
            {"worker_id": worker_id, **payload.model_dump()},
            actor.email,
        )
        self.session.commit()
        return prior_period_read(period, client_name)

    def update(
        self,
        period_id: uuid.UUID,
        payload: StaffingPriorPeriodUpdate,
        actor: User,
        today: date | None = None,
    ) -> StaffingPriorPeriodRead:
        period = self._get(period_id)
        values = payload.model_dump(exclude_unset=True)
        for required in ("client_company_id", "start_date", "end_date", "source"):
            if values.get(required, ...) is None:
                values.pop(required)
        client_name = self._client_name(values.get("client_company_id", period.client_company_id))
        _check_closed(
            values.get("start_date", period.start_date),
            values.get("end_date", period.end_date),
            today or date.today(),
        )
        audit.log_updated(
            self.session, audit.ENTITY_PRIOR_PERIOD, period, period.id, values, actor.email
        )
        for field, value in values.items():
            setattr(period, field, value)
        self.session.commit()
        return prior_period_read(period, client_name)

    def delete(self, period_id: uuid.UUID, actor: User) -> None:
        period = self._get(period_id)
        audit.log_event(
            self.session,
            audit.ENTITY_PRIOR_PERIOD,
            period.id,
            "deleted",
            actor.email,
            {
                "worker_id": period.worker_id,
                "client_company_id": period.client_company_id,
                "start_date": period.start_date,
                "end_date": period.end_date,
                "source": period.source.value,
            },
        )
        self.session.delete(period)
        self.session.commit()
