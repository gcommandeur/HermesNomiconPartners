# NOMICON: Arbeitnehmerueberlassung - nur in der Nomicon-Kopie.
"""Zugriffsgrenzen der Ueberlassung (Muster: api/dependencies.py::process_owner_scope).

Einsaetze (und alles daran: Checkliste, Stundenzettel) sind ueber `owner_user_id` (Disponent)
gescopt: Mitarbeiter sehen ihre eigenen, Teamleiter eigene und die ihres Teams, Admins alle.
Fremd UND nicht existent liefert dasselbe 404 (nie 403). Leiharbeitnehmer, Vertraege und
Erlaubnis sind - wie Kandidaten und Kanzleien - ein gemeinsamer Pool.

Neue Routen mit `assignment_id` / `timesheet_id` / `invoice_id` im Pfad MUESSEN `AssignmentAccess`,
`TimesheetAccess` bzw. `InvoiceAccess` bekommen (erzwungen von
tests/api/test_staffing_access_guard.py)."""

import uuid

from fastapi import Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from cc_crm.api.dependencies import CurrentUser, DatabaseSession, process_owner_scope
from cc_crm.core.errors import EntityNotFoundError
from cc_crm.models.staffing import StaffingAssignment, StaffingInvoice, StaffingTimesheet
from cc_crm.models.user import User


def staffing_owner_scope(current_user: User, session: Session) -> list[uuid.UUID] | None:
    """None = keine Einschraenkung (Admin), sonst die Disponenten-IDs, deren Einsaetze sichtbar
    sind. Gleiche Regel wie bei Prozessen (eigene / eigene + Team), LIVE aus der Datenbank."""
    return process_owner_scope(current_user, session)


def user_can_access_assignment(
    session: Session, current_user: User, assignment_id: uuid.UUID
) -> bool:
    scope = staffing_owner_scope(current_user, session)
    if scope is None:
        return True
    owner_user_id = session.scalar(
        select(StaffingAssignment.owner_user_id).where(StaffingAssignment.id == assignment_id)
    )
    return owner_user_id is not None and owner_user_id in scope


def require_assignment_access(
    assignment_id: uuid.UUID, session: DatabaseSession, current_user: CurrentUser
) -> None:
    """Admins laufen durch (der Handler meldet ein nicht existierendes Objekt selbst mit 404)."""
    if not user_can_access_assignment(session, current_user, assignment_id):
        raise EntityNotFoundError("Einsatz nicht gefunden")


def require_timesheet_access(
    timesheet_id: uuid.UUID, session: DatabaseSession, current_user: CurrentUser
) -> None:
    scope = staffing_owner_scope(current_user, session)
    if scope is None:
        return
    owner_user_id = session.scalar(
        select(StaffingAssignment.owner_user_id)
        .join(StaffingTimesheet, StaffingTimesheet.assignment_id == StaffingAssignment.id)
        .where(StaffingTimesheet.id == timesheet_id)
    )
    if owner_user_id is None or owner_user_id not in scope:
        raise EntityNotFoundError("Stundenzettel nicht gefunden")


def require_invoice_access(
    invoice_id: uuid.UUID, session: DatabaseSession, current_user: CurrentUser
) -> None:
    """Rechnungen sehen Admins und wer sie angelegt hat (bzw. dessen Teamleiter)."""
    scope = staffing_owner_scope(current_user, session)
    if scope is None:
        return
    creator = session.scalar(
        select(StaffingInvoice.created_by_user_id).where(StaffingInvoice.id == invoice_id)
    )
    if creator is None or creator not in scope:
        raise EntityNotFoundError("Rechnung nicht gefunden")


AssignmentAccess = Depends(require_assignment_access)
TimesheetAccess = Depends(require_timesheet_access)
InvoiceAccess = Depends(require_invoice_access)
