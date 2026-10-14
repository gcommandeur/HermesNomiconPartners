# NOMICON: Disposition der Ueberlassung - nur in der Nomicon-Kopie.
"""Kennzahlen, Bench und Stundenzettel-Eingang fuer die Disposition. Alles, was an Einsaetzen
haengt, ist wie ueberall auf den Sichtbereich des Nutzers begrenzt (`owner_scope`); die Bench ist
eine Liste von Leiharbeitnehmern (Profile sind wie Kandidaten ein gemeinsamer Pool)."""

import uuid
from datetime import date

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from cc_crm.models.candidate import Candidate
from cc_crm.models.staffing import (
    StaffingAssignment,
    StaffingAssignmentStatus,
    StaffingInvoiceLine,
    StaffingTimesheet,
    StaffingTimesheetStatus,
    StaffingWorker,
    StaffingWorkerStatus,
)
from cc_crm.repositories.staffing import candidate_display_name
from cc_crm.schemas.staffing_disposition import (
    StaffingBenchWorkerRead,
    StaffingDispositionRead,
    StaffingTimesheetInboxRead,
)
from cc_crm.services.staffing_overview import overview

_OPEN = (StaffingAssignmentStatus.PLANNED, StaffingAssignmentStatus.ACTIVE)


def bench(session: Session, today: date) -> list[StaffingBenchWorkerRead]:
    """Aktive Leiharbeitnehmer ohne geplanten oder aktiven Einsatz, am laengsten frei zuerst."""
    busy = select(StaffingAssignment.worker_id).where(StaffingAssignment.status.in_(_OPEN))
    rows = session.execute(
        select(StaffingWorker, Candidate.first_name, Candidate.last_name)
        .join(Candidate, Candidate.id == StaffingWorker.candidate_id)
        .where(StaffingWorker.status == StaffingWorkerStatus.ACTIVE, StaffingWorker.id.not_in(busy))
    ).all()
    last_end = dict(
        session.execute(
            select(
                StaffingAssignment.worker_id,
                func.max(
                    func.coalesce(
                        StaffingAssignment.actual_end_date, StaffingAssignment.planned_end_date
                    )
                ),
            )
            .where(StaffingAssignment.status == StaffingAssignmentStatus.ENDED)
            .group_by(StaffingAssignment.worker_id)
        ).all()
    )
    result = []
    for worker, first, last in rows:
        since = last_end.get(worker.id) or worker.entry_date
        if isinstance(since, str):  # SQLite liefert Aggregate als Text
            since = date.fromisoformat(since)
        result.append(
            StaffingBenchWorkerRead(
                worker_id=worker.id,
                worker_name=candidate_display_name(first, last),
                free_since=since,
                days_free=(today - since).days if since else None,
                pay_grade=worker.pay_grade,
                work_permit_valid_until=worker.work_permit_valid_until,
            )
        )
    return sorted(result, key=lambda item: (item.free_since is None, item.free_since or today))


def timesheet_inbox(
    session: Session, owner_scope: list[uuid.UUID] | None, today: date
) -> StaffingTimesheetInboxRead:
    statement = select(StaffingTimesheet.status, StaffingTimesheet.period_end, StaffingTimesheet.id)
    statement = statement.join(
        StaffingAssignment, StaffingAssignment.id == StaffingTimesheet.assignment_id
    )
    if owner_scope is not None:
        statement = statement.where(StaffingAssignment.owner_user_id.in_(owner_scope))
    billed = {
        row[0]
        for row in session.execute(
            select(StaffingInvoiceLine.timesheet_id).where(
                StaffingInvoiceLine.timesheet_id.is_not(None)
            )
        )
    }
    counts = {"open": 0, "open_overdue": 0, "submitted": 0, "approved_unbilled": 0, "rejected": 0}
    for status, period_end, timesheet_id in session.execute(statement).all():
        if status == StaffingTimesheetStatus.OPEN:
            counts["open"] += 1
            if period_end < today:
                counts["open_overdue"] += 1
        elif status == StaffingTimesheetStatus.SUBMITTED:
            counts["submitted"] += 1
        elif status == StaffingTimesheetStatus.APPROVED and timesheet_id not in billed:
            counts["approved_unbilled"] += 1
        elif status == StaffingTimesheetStatus.REJECTED:
            counts["rejected"] += 1
    return StaffingTimesheetInboxRead(**counts)


def disposition(
    session: Session, owner_scope: list[uuid.UUID] | None, today: date
) -> StaffingDispositionRead:
    base = overview(session, owner_scope, today)
    benched = bench(session, today)
    inbox = timesheet_inbox(session, owner_scope, today)
    return StaffingDispositionRead(
        active_assignments=base.active_assignments,
        planned_assignments=base.planned_assignments,
        open_checklist_assignments=base.open_checklist_assignments,
        bench_count=len(benched),
        timesheet_backlog=inbox.open_overdue + inbox.approved_unbilled,
        license=base.license,
        inbox=inbox,
        bench=benched,
    )
