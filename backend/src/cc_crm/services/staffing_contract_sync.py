# NOMICON: Arbeitnehmerüberlassung - nur in der Nomicon-Kopie.
"""Folgen der Vertragsprüfung: abgeleiteter Checklistenpunkt und Aufgabe bei einer Lücke.

Der Checklistenpunkt "Überlassungsvertrag" wird nie von Hand abgehakt: er ist erfüllt, wenn der
verknüpfte Vertrag den Einsatz abdeckt (services/staffing_contract_check.py). Er wird bei jeder
Änderung von Einsatz oder Vertrag neu gesetzt. Führt eine Änderung bei einem AKTIVEN Einsatz dazu,
dass der Vertrag den Zeitraum nicht mehr deckt, entsteht einmalig eine Aufgabe für den Disponenten
- die Änderung selbst wird nicht blockiert."""

import uuid
from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from cc_crm.models.enums import TaskPriority
from cc_crm.models.staffing import (
    StaffingAssignment,
    StaffingAssignmentStatus,
    StaffingChecklistItem,
    StaffingChecklistKey,
    StaffingContract,
)
from cc_crm.services.staffing_contract_check import (
    supply_contract_problem,
)
from cc_crm.services.staffing_task_helpers import (
    active_admin_ids,
    create_task_once,
    pair_names,
)


def contract_problem_for(
    session: Session, assignment: StaffingAssignment, today: date
) -> str | None:
    contract = (
        session.get(StaffingContract, assignment.contract_id)
        if assignment.contract_id is not None
        else None
    )
    return supply_contract_problem(assignment, contract, today)


def sync_supply_contract_item(
    session: Session, assignment: StaffingAssignment, today: date
) -> None:
    """Setzt den Checklistenpunkt "Überlassungsvertrag" nach dem Stand des Vertrags."""
    item = session.scalar(
        select(StaffingChecklistItem).where(
            StaffingChecklistItem.assignment_id == assignment.id,
            StaffingChecklistItem.item_key == StaffingChecklistKey.SUPPLY_CONTRACT,
        )
    )
    if item is None:
        return
    covered = contract_problem_for(session, assignment, today) is None
    if item.done != covered:
        item.done = covered
        item.done_on = today if covered else None


def notify_contract_gap(
    session: Session,
    assignment: StaffingAssignment,
    problem_before: str | None,
    today: date,
) -> int:
    """Einmalige Aufgabe, wenn ein AKTIVER Einsatz durch eine Änderung den Vertrag verliert.
    Nur der Übergang "gedeckt -> nicht gedeckt" löst aus (ein schon vorher ungedeckter Einsatz
    nicht); die Kennung enthält den Zustand von Vertrag und Zeitraum, sodass dieselbe Lücke nur
    eine Aufgabe erzeugt. Keine Lohn- oder Margenwerte im Text."""
    if assignment.status != StaffingAssignmentStatus.ACTIVE or problem_before is not None:
        return 0
    problem = contract_problem_for(session, assignment, today)
    if problem is None:
        return 0
    contract = (
        session.get(StaffingContract, assignment.contract_id)
        if assignment.contract_id is not None
        else None
    )
    worker_name, client_name = pair_names(
        session, assignment.worker_id, assignment.client_company_id
    )
    recipients: list[uuid.UUID] = (
        [assignment.owner_user_id]
        if assignment.owner_user_id is not None
        else active_admin_ids(session)
    )
    state = ":".join(
        str(part)
        for part in (
            assignment.contract_id,
            assignment.start_date,
            assignment.planned_end_date,
            contract.valid_from if contract else None,
            contract.valid_to if contract else None,
            contract.status.value if contract else None,
        )
    )
    headline = "fehlt" if assignment.contract_id is None else "deckt Einsatz nicht mehr"
    created = 0
    for user_id in recipients:
        if create_task_once(
            session,
            marker=f"[staffing-contract:{assignment.id}:{state}:{user_id}]",
            title=f"Überlassungsvertrag {headline}: {worker_name} bei {client_name}",
            body=(
                f"{problem} Der Einsatz bleibt aktiv, der Vertrag oder der Einsatzzeitraum "
                "sollte angepasst werden."
            ),
            owner_user_id=user_id,
            priority=TaskPriority.HIGH,
            today=today,
        ):
            created += 1
    return created
