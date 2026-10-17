# NOMICON: Arbeitnehmerüberlassung - nur in der Nomicon-Kopie.
"""Equal Pay mit Folge: bestätigen, dass der Lohn geprüft und angeglichen wurde.

Ab dem Equal-Pay-Datum einer Kette (Annahme, kein Rechtsrat) legt der tägliche Job eine Aufgabe
"Lohn prüfen und angleichen" für den Disponenten an (services/staffing_deadline_job.py). Sie ist
erledigt, sobald `equal_pay_confirmed_on` an einem Einsatz des Paares gesetzt ist. Das Bestätigen
darf jeder mit Zugriff auf den Einsatz; die Lohnhöhe sehen und ändern weiterhin nur Admins - weder
Aufgabentexte noch diese Antworten enthalten Lohn- oder Margenwerte, nur Namen und Datum.

Eine Bestätigung gehört zur aktuellen Kette: sie zählt nur, wenn sie am oder nach dem Kettenbeginn
liegt (nach einem Reset durch eine lange Unterbrechung beginnt Equal Pay von vorn)."""

import uuid
from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from cc_crm.core.errors import BusinessRuleError, EntityNotFoundError
from cc_crm.models.enums import TaskStatus
from cc_crm.models.staffing import StaffingAssignment, StaffingAssignmentStatus
from cc_crm.models.task import Task
from cc_crm.models.user import User
from cc_crm.services import staffing_audit as audit

EQUAL_PAY_PREWARN_DAYS = 30  # Vorwarnung: so viele Tage vor dem Equal-Pay-Datum
_EDITABLE = (StaffingAssignmentStatus.PLANNED, StaffingAssignmentStatus.ACTIVE)


def pair_equal_pay_confirmed_on(
    session: Session,
    worker_id: uuid.UUID,
    client_company_id: uuid.UUID,
    chain_start: date | None,
) -> date | None:
    """Jüngste Bestätigung an einem (nicht abgebrochenen) Einsatz des Paares innerhalb der
    aktuellen Kette; `None`, wenn es keine gibt."""
    if chain_start is None:
        return None
    confirmed = session.scalars(
        select(StaffingAssignment.equal_pay_confirmed_on).where(
            StaffingAssignment.worker_id == worker_id,
            StaffingAssignment.client_company_id == client_company_id,
            StaffingAssignment.status != StaffingAssignmentStatus.ABORTED,
            StaffingAssignment.equal_pay_confirmed_on.is_not(None),
            StaffingAssignment.equal_pay_confirmed_on >= chain_start,
        )
    ).all()
    dates = [day for day in confirmed if day is not None]
    return max(dates) if dates else None


def close_equal_pay_tasks(
    session: Session, worker_id: uuid.UUID, client_company_id: uuid.UUID
) -> int:
    """Setzt die offenen Equal-Pay-Aufgaben des Paares auf erledigt (idempotent)."""
    prefix = f"[staffing-deadline:{worker_id}:{client_company_id}:equal_pay"
    closed = 0
    for task in session.scalars(
        select(Task).where(
            Task.description.contains(prefix),
            Task.status.in_((TaskStatus.OPEN, TaskStatus.IN_PROGRESS)),
        )
    ):
        task.status = TaskStatus.DONE
        closed += 1
    return closed


class StaffingEqualPayService:
    def __init__(self, session: Session) -> None:
        self.session = session

    def _editable_assignment(self, assignment_id: uuid.UUID) -> StaffingAssignment:
        assignment = self.session.get(StaffingAssignment, assignment_id)
        if assignment is None:
            raise EntityNotFoundError("Einsatz nicht gefunden")
        if assignment.status not in _EDITABLE:
            raise BusinessRuleError("Beendete oder abgebrochene Einsätze sind nicht mehr änderbar.")
        return assignment

    def confirm(
        self,
        assignment_id: uuid.UUID,
        actor: User,
        confirmed_on: date | None = None,
        today: date | None = None,
    ) -> None:
        day = today or date.today()
        assignment = self._editable_assignment(assignment_id)
        on = confirmed_on or day
        if on > day:
            raise BusinessRuleError("Die Bestätigung kann nicht in der Zukunft liegen.")
        if on < assignment.start_date:
            raise BusinessRuleError("Die Bestätigung liegt vor dem Beginn des Einsatzes.")
        audit.log_updated(
            self.session,
            audit.ENTITY_ASSIGNMENT,
            assignment,
            assignment.id,
            {"equal_pay_confirmed_on": on, "equal_pay_confirmed_by_user_id": actor.id},
            actor.email,
            action="equal_pay_confirmed",
        )
        assignment.equal_pay_confirmed_on = on
        assignment.equal_pay_confirmed_by_user_id = actor.id
        close_equal_pay_tasks(self.session, assignment.worker_id, assignment.client_company_id)
        self.session.commit()

    def clear(self, assignment_id: uuid.UUID, actor: User) -> None:
        """Bestätigung zurücknehmen (Eingabekorrektur); die Aufgabe wird nicht wieder geöffnet."""
        assignment = self._editable_assignment(assignment_id)
        audit.log_updated(
            self.session,
            audit.ENTITY_ASSIGNMENT,
            assignment,
            assignment.id,
            {"equal_pay_confirmed_on": None, "equal_pay_confirmed_by_user_id": None},
            actor.email,
            action="equal_pay_unconfirmed",
        )
        assignment.equal_pay_confirmed_on = None
        assignment.equal_pay_confirmed_by_user_id = None
        self.session.commit()
