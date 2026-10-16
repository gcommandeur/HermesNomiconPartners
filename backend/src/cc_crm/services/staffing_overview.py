# NOMICON: Arbeitnehmerüberlassung - nur in der Nomicon-Kopie.
"""Übersicht (Dashboard) und Fristenliste der Überlassung, gefiltert nach Sichtbarkeit."""

import uuid
from dataclasses import asdict
from datetime import date

from sqlalchemy.orm import Session

from cc_crm.models.staffing import StaffingAssignmentStatus
from cc_crm.repositories.staffing import StaffingAssignmentRepository, StaffingLicenseRepository
from cc_crm.schemas.staffing import (
    StaffingDeadlineRead,
    StaffingLicenseStatus,
    StaffingOverviewRead,
    StaffingPairDeadlineRead,
)
from cc_crm.services.staffing_deadline_job import pair_deadline
from cc_crm.services.staffing_deadlines import DeadlineResult, Traffic
from cc_crm.services.staffing_settings import load_config

DISCLAIMER = (
    "Hinweis: Diese Werte sind einstellbare Annahmen und kein Rechtsrat. Bitte mit Fachanwalt "
    "oder Verband bestätigen; Tarifverträge können abweichen."
)
_OPEN = (StaffingAssignmentStatus.PLANNED, StaffingAssignmentStatus.ACTIVE)
_URGENCY = {Traffic.RED: 0, Traffic.YELLOW: 1, Traffic.GREEN: 2}


def deadline_read(result: DeadlineResult) -> StaffingDeadlineRead:
    return StaffingDeadlineRead(**asdict(result))


def license_status(session: Session, today: date) -> StaffingLicenseStatus:
    config = load_config(session)
    current = StaffingLicenseRepository(session).covering(today, today)
    if current is None:
        return StaffingLicenseStatus(
            valid=False, valid_to=None, days_remaining=None, traffic=Traffic.RED
        )
    if current.valid_to is None:
        return StaffingLicenseStatus(
            valid=True, valid_to=None, days_remaining=None, traffic=Traffic.GREEN
        )
    remaining = (current.valid_to - today).days
    traffic = (
        Traffic.RED
        if remaining < config.red_days
        else Traffic.YELLOW
        if remaining < config.yellow_days
        else Traffic.GREEN
    )
    return StaffingLicenseStatus(
        valid=True, valid_to=current.valid_to, days_remaining=remaining, traffic=traffic
    )


def pair_deadlines(
    session: Session, owner_scope: list[uuid.UUID] | None, today: date
) -> list[StaffingPairDeadlineRead]:
    """Paare mit mindestens einem sichtbaren geplanten/aktiven Einsatz. Gerechnet wird mit ALLEN
    Einsätzen des Paares (die gesetzliche Zählung kennt keine Disponenten-Grenzen)."""
    repo = StaffingAssignmentRepository(session)
    config = load_config(session)
    seen: dict[tuple[uuid.UUID, uuid.UUID], StaffingPairDeadlineRead] = {}
    for row in repo.rows(owner_scope=owner_scope, limit=5000):
        assignment = row.assignment
        if assignment.status not in _OPEN:
            continue
        key = (assignment.worker_id, assignment.client_company_id)
        if key in seen:
            continue
        result = pair_deadline(session, key[0], key[1], today, config)
        if not result.has_chain:
            continue
        seen[key] = StaffingPairDeadlineRead(
            **asdict(result),
            worker_id=key[0],
            worker_name=row.worker_name,
            client_company_id=key[1],
            client_name=row.client_name,
            owner_user_id=assignment.owner_user_id,
        )
    return sorted(
        seen.values(),
        key=lambda d: (
            _URGENCY[d.traffic],
            d.days_remaining if d.days_remaining is not None else 0,
        ),
    )


def overview(
    session: Session, owner_scope: list[uuid.UUID] | None, today: date
) -> StaffingOverviewRead:
    repo = StaffingAssignmentRepository(session)
    rows = [
        r for r in repo.rows(owner_scope=owner_scope, limit=5000) if r.assignment.status in _OPEN
    ]
    return StaffingOverviewRead(
        active_assignments=sum(
            r.assignment.status == StaffingAssignmentStatus.ACTIVE for r in rows
        ),
        planned_assignments=sum(
            r.assignment.status == StaffingAssignmentStatus.PLANNED for r in rows
        ),
        open_checklist_assignments=sum(r.checklist_done < r.checklist_total for r in rows),
        license=license_status(session, today),
        deadlines=pair_deadlines(session, owner_scope, today),
    )
