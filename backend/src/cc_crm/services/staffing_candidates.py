# NOMICON: Überlassung am Kandidaten (Liste, Detail) - nur in der Nomicon-Kopie.
"""Aggregate für die Kandidatenliste (Status, aktueller Kunde, Fristen-Ampel) und der Filter
"Überlassung". Eine Abfrage je Baustein statt einer je Zeile: Arbeitnehmer der Seite, ihre offenen
Einsätze, die Fristen aller offenen Paare (einmal je Anfrage). Keine Lohn- oder Margenangaben."""

import uuid
from datetime import date

from sqlalchemy import ColumnElement, exists, func, not_, select
from sqlalchemy.orm import Session

from cc_crm.core.errors import BusinessRuleError
from cc_crm.models.candidate import Candidate
from cc_crm.models.client_company import ClientCompany
from cc_crm.models.staffing import (
    StaffingAssignment,
    StaffingAssignmentStatus,
    StaffingInvoiceLine,
    StaffingPriorPeriod,
    StaffingTimesheet,
    StaffingTimesheetStatus,
    StaffingWorker,
    StaffingWorkerStatus,
)
from cc_crm.schemas.staffing_candidates import (
    StaffingCandidateSummaryRead,
    StaffingWorkerTimesheetSummary,
)
from cc_crm.services.staffing_deadline_job import assignment_span
from cc_crm.services.staffing_deadlines import Span, Traffic, compute_deadline
from cc_crm.services.staffing_settings import load_config

_OPEN = (StaffingAssignmentStatus.PLANNED, StaffingAssignmentStatus.ACTIVE)
# wie in der Fristenzählung: geplante, aktive und beendete Einsätze zählen (abgebrochene nicht)
COUNTED_STATUSES = (*_OPEN, StaffingAssignmentStatus.ENDED)
_URGENCY = {Traffic.RED: 0, Traffic.YELLOW: 1, Traffic.GREEN: 2}


def _critical_worker_ids(
    session: Session, today: date, worker_ids: list[uuid.UUID] | None = None
) -> dict[uuid.UUID, tuple[Traffic, int | None]]:
    """Je Leiharbeitnehmer die dringendste Frist (rot vor gelb vor grün) über alle Kunden mit
    offenem Einsatz. Eine einzige Abfrage über alle gezählten Einsätze (kein Rechnen je Paar mit
    Datenbankzugriff); die gesetzliche Zählung kennt keine Besitzgrenzen, deshalb agenturweit."""
    statement = select(StaffingAssignment).where(StaffingAssignment.status.in_(COUNTED_STATUSES))
    if worker_ids is not None:
        statement = statement.where(StaffingAssignment.worker_id.in_(worker_ids))
    pairs: dict[tuple[uuid.UUID, uuid.UUID], list[StaffingAssignment]] = {}
    for assignment in session.scalars(statement).all():
        pairs.setdefault((assignment.worker_id, assignment.client_company_id), []).append(
            assignment
        )
    # Vorzeiten beim selben Kunden zählen mit (eine Abfrage für alle betroffenen Personen)
    prior: dict[tuple[uuid.UUID, uuid.UUID], list[Span]] = {}
    prior_statement = select(StaffingPriorPeriod).where(
        StaffingPriorPeriod.worker_id.in_({worker for worker, _client in pairs})
    )
    for period in session.scalars(prior_statement).all():
        prior.setdefault((period.worker_id, period.client_company_id), []).append(
            Span(period.start_date, period.end_date)
        )
    config = load_config(session)
    worst: dict[uuid.UUID, tuple[Traffic, int | None]] = {}
    for (worker_id, client_id), assignments in pairs.items():
        if not any(a.status in _OPEN for a in assignments):
            continue
        result = compute_deadline(
            [assignment_span(a) for a in assignments],
            today,
            config,
            prior_spans=prior.get((worker_id, client_id), ()),
        )
        if not result.has_chain:
            continue
        current = worst.get(worker_id)
        if current is None or _URGENCY[result.traffic] < _URGENCY[current[0]]:
            worst[worker_id] = (result.traffic, result.days_remaining)
    return worst


def list_filter(session: Session, mode: str, today: date) -> list[ColumnElement[bool]]:
    """Zusatzbedingungen für die Kandidatenliste (serverseitig, ohne Abfrage je Zeile)."""
    open_assignment = exists().where(
        StaffingAssignment.worker_id == StaffingWorker.id, StaffingAssignment.status.in_(_OPEN)
    )
    if mode == "workers":
        return [
            exists().where(
                StaffingWorker.candidate_id == Candidate.id,
                StaffingWorker.status != StaffingWorkerStatus.LEFT,
            )
        ]
    if mode == "applicants":
        return [
            exists().where(
                StaffingWorker.candidate_id == Candidate.id,
                StaffingWorker.status == StaffingWorkerStatus.APPLICANT,
            )
        ]
    if mode == "bench":
        return [
            exists().where(
                StaffingWorker.candidate_id == Candidate.id,
                StaffingWorker.status == StaffingWorkerStatus.ACTIVE,
                not_(open_assignment),
            )
        ]
    if mode == "critical":
        critical = [
            worker_id
            for worker_id, (traffic, _) in _critical_worker_ids(session, today).items()
            if traffic in (Traffic.RED, Traffic.YELLOW)
        ]
        return [
            exists().where(
                StaffingWorker.candidate_id == Candidate.id, StaffingWorker.id.in_(critical)
            )
        ]
    raise BusinessRuleError("Unbekannter Überlassungs-Filter.")


def candidate_summaries(
    session: Session, candidate_ids: list[uuid.UUID], today: date
) -> dict[uuid.UUID, StaffingCandidateSummaryRead]:
    result = {
        cid: StaffingCandidateSummaryRead(candidate_id=cid, status="none") for cid in candidate_ids
    }
    if not candidate_ids:
        return result
    workers = session.scalars(
        select(StaffingWorker).where(StaffingWorker.candidate_id.in_(candidate_ids))
    ).all()
    if not workers:
        return result
    worker_ids = [w.id for w in workers]
    current: dict[uuid.UUID, tuple[StaffingAssignmentStatus, str]] = {}
    for assignment, client_name in session.execute(
        select(StaffingAssignment, ClientCompany.name)
        .join(ClientCompany, ClientCompany.id == StaffingAssignment.client_company_id)
        .where(StaffingAssignment.worker_id.in_(worker_ids), StaffingAssignment.status.in_(_OPEN))
        .order_by(StaffingAssignment.start_date)
    ).all():
        known = current.get(assignment.worker_id)
        # aktiv geht vor geplant
        if known is None or (
            known[0] == StaffingAssignmentStatus.PLANNED
            and assignment.status == StaffingAssignmentStatus.ACTIVE
        ):
            current[assignment.worker_id] = (assignment.status, client_name)
    traffic = _critical_worker_ids(session, today, worker_ids)
    for worker in workers:
        open_state = current.get(worker.id)
        light = traffic.get(worker.id)
        result[worker.candidate_id] = StaffingCandidateSummaryRead(
            candidate_id=worker.candidate_id,
            status=worker.status.value,
            worker_id=worker.id,
            client_name=open_state[1] if open_state else None,
            assignment_status=open_state[0].value if open_state else None,  # type: ignore[arg-type]
            traffic=light[0].value if light else None,
            days_remaining=light[1] if light else None,
            bench=worker.status == StaffingWorkerStatus.ACTIVE and open_state is None,
        )
    return result


def worker_timesheet_summary(
    session: Session, worker_id: uuid.UUID, owner_scope: list[uuid.UUID] | None
) -> StaffingWorkerTimesheetSummary:
    """Stundenzettel der Person je Status, begrenzt auf Einsätze im Besitzbereich des Nutzers."""
    statement = (
        select(StaffingTimesheet.status, func.count(), StaffingTimesheet.id)
        .join(StaffingAssignment, StaffingAssignment.id == StaffingTimesheet.assignment_id)
        .where(StaffingAssignment.worker_id == worker_id)
        .group_by(StaffingTimesheet.status, StaffingTimesheet.id)
    )
    if owner_scope is not None:
        statement = statement.where(StaffingAssignment.owner_user_id.in_(owner_scope))
    billed = set(
        session.scalars(
            select(StaffingInvoiceLine.timesheet_id).where(
                StaffingInvoiceLine.timesheet_id.is_not(None)
            )
        ).all()
    )
    counts = {"open": 0, "submitted": 0, "approved": 0, "rejected": 0, "approved_unbilled": 0}
    for status, _, timesheet_id in session.execute(statement).all():
        if status == StaffingTimesheetStatus.OPEN:
            counts["open"] += 1
        elif status == StaffingTimesheetStatus.SUBMITTED:
            counts["submitted"] += 1
        elif status == StaffingTimesheetStatus.APPROVED:
            counts["approved"] += 1
            if timesheet_id not in billed:
                counts["approved_unbilled"] += 1
        elif status == StaffingTimesheetStatus.REJECTED:
            counts["rejected"] += 1
    return StaffingWorkerTimesheetSummary(worker_id=worker_id, **counts)
