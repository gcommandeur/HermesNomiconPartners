# NOMICON: Aufgaben und Hinweise der Ansicht Überlassung - nur in der Nomicon-Kopie.
"""Fristen, Stundenzettel, Checklisten, Bench und Erlaubnis als Aufgabenliste. Keine eigene
Rechtslogik: Ampelwerte und Warnschwellen kommen aus dem Fristen-Service und den einstellbaren
Compliance-Einstellungen. Die Aufgaben folgen dem Besitzbereich (`staffing_owner_scope`), die Bench
ist wie in der Disposition agenturweit."""

import uuid
from datetime import date, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from cc_crm.models.staffing import (
    StaffingAssignment,
    StaffingAssignmentStatus,
    StaffingTimesheet,
    StaffingTimesheetStatus,
)
from cc_crm.repositories.staffing import StaffingAssignmentRepository
from cc_crm.schemas.staffing_tasks import Severity, StaffingTaskRead, StaffingTasksRead
from cc_crm.services.staffing_deadlines import Traffic
from cc_crm.services.staffing_disposition import bench
from cc_crm.services.staffing_overview import license_status, pair_deadlines
from cc_crm.services.staffing_settings import load_config

BENCH_AFTER_DAYS = 14  # ab so vielen freien Tagen erscheint ein Leiharbeitnehmer als Aufgabe
_SEVERITY_ORDER = {"red": 0, "yellow": 1, "info": 2}


def _fmt(value: date) -> str:
    return value.strftime("%d.%m.%Y")


def _previous_month(today: date) -> tuple[date, date]:
    end = today.replace(day=1) - timedelta(days=1)
    return end.replace(day=1), end


def build_tasks(
    session: Session, owner_scope: list[uuid.UUID] | None, today: date
) -> StaffingTasksRead:
    config = load_config(session)
    tasks: list[StaffingTaskRead] = []
    rows = [
        row
        for row in StaffingAssignmentRepository(session).rows(owner_scope=owner_scope, limit=5000)
        if row.assignment.status
        in (StaffingAssignmentStatus.PLANNED, StaffingAssignmentStatus.ACTIVE)
    ]
    by_pair = {(r.assignment.worker_id, r.assignment.client_company_id): r for r in rows}

    # 1. Höchstüberlassungsdauer und Equal Pay aus dem Fristen-Service
    for deadline in pair_deadlines(session, owner_scope, today):
        row = by_pair.get((deadline.worker_id, deadline.client_company_id))
        assignment_id = row.assignment.id if row else None
        if deadline.traffic in (Traffic.RED, Traffic.YELLOW) and deadline.max_end_date:
            remaining = deadline.days_remaining or 0
            text = (
                f"seit {-remaining} Tag(en) überschritten"
                if deadline.exceeded
                else f"in {remaining} Tag(en) erreicht"
            )
            tasks.append(
                StaffingTaskRead(
                    kind="deadline_max",
                    severity="red" if deadline.traffic == Traffic.RED else "yellow",
                    title=(
                        f"Höchstüberlassungsdauer: {deadline.worker_name} "
                        f"bei {deadline.client_name}"
                    ),
                    detail=f"Spätester Einsatztag {_fmt(deadline.max_end_date)} – {text}.",
                    due_at=deadline.max_end_date,
                    assignment_id=assignment_id,
                    worker_id=deadline.worker_id,
                )
            )
        if (
            deadline.equal_pay_from
            and not deadline.equal_pay_reached
            and (deadline.equal_pay_from - today).days <= config.yellow_days
        ):
            tasks.append(
                StaffingTaskRead(
                    kind="equal_pay",
                    severity="yellow",
                    title=f"Equal Pay beginnt: {deadline.worker_name} bei {deadline.client_name}",
                    detail=f"Ab {_fmt(deadline.equal_pay_from)} gilt Equal Pay – Entgelt prüfen.",
                    due_at=deadline.equal_pay_from,
                    assignment_id=assignment_id,
                    worker_id=deadline.worker_id,
                )
            )

    # 2. Stundenzettel: Rückstand, abgelehnt, fehlender Zettel für den Vormonat
    scope_ids = {row.assignment.id for row in rows}
    names = {r.assignment.id: r for r in rows}
    sheets = session.scalars(
        select(StaffingTimesheet).where(StaffingTimesheet.assignment_id.in_(scope_ids))
    ).all() if scope_ids else []
    for sheet in sheets:
        row = names[sheet.assignment_id]
        who = f"{row.worker_name} bei {row.client_name}"
        if sheet.status == StaffingTimesheetStatus.OPEN and sheet.period_end < today:
            tasks.append(
                StaffingTaskRead(
                    kind="timesheet_overdue",
                    severity="yellow",
                    title=f"Stundenzettel offen: {who}",
                    detail=f"Zeitraum bis {_fmt(sheet.period_end)} noch nicht eingereicht.",
                    due_at=sheet.period_end,
                    assignment_id=sheet.assignment_id,
                )
            )
        elif sheet.status == StaffingTimesheetStatus.REJECTED:
            tasks.append(
                StaffingTaskRead(
                    kind="timesheet_rejected",
                    severity="yellow",
                    title=f"Stundenzettel abgelehnt: {who}",
                    detail="Vom Kunden abgelehnt – korrigieren und erneut einreichen.",
                    due_at=sheet.period_end,
                    assignment_id=sheet.assignment_id,
                )
            )
    first, last = _previous_month(today)
    for row in rows:
        assignment: StaffingAssignment = row.assignment
        if assignment.status != StaffingAssignmentStatus.ACTIVE:
            continue
        if assignment.start_date > last:
            continue
        covered = any(
            s.assignment_id == assignment.id and s.period_start <= last and s.period_end >= first
            for s in sheets
        )
        if not covered:
            tasks.append(
                StaffingTaskRead(
                    kind="timesheet_missing",
                    severity="info",
                    title=f"Stundenzettel fehlt: {row.worker_name} bei {row.client_name}",
                    detail=f"Für {first.strftime('%m/%Y')} gibt es noch keinen Stundenzettel.",
                    due_at=last,
                    assignment_id=assignment.id,
                )
            )

    # 3. Offene Checklisten (Einsatz beginnt bald oder läuft ohne vollständige Checkliste)
    for row in rows:
        if row.checklist_done >= row.checklist_total:
            continue
        starts_in = (row.assignment.start_date - today).days
        severity: Severity = "red" if starts_in <= 7 else "yellow" if starts_in <= 21 else "info"
        tasks.append(
            StaffingTaskRead(
                kind="checklist_open",
                severity=severity,
                title=f"Checkliste offen: {row.worker_name} bei {row.client_name}",
                detail=(
                    f"{row.checklist_done} von {row.checklist_total} Pflichtpunkten erledigt, "
                    f"Einsatz {'beginnt' if starts_in >= 0 else 'begann'} am "
                    f"{_fmt(row.assignment.start_date)}."
                ),
                due_at=row.assignment.start_date,
                assignment_id=row.assignment.id,
            )
        )

    # 4. Bench-Dauer (agenturweit wie in der Disposition)
    for free in bench(session, today):
        if free.days_free is not None and free.days_free >= BENCH_AFTER_DAYS:
            tasks.append(
                StaffingTaskRead(
                    kind="bench",
                    severity="info",
                    title=f"Auf der Bench: {free.worker_name}",
                    detail=f"Seit {free.days_free} Tagen ohne Einsatz – neuen Einsatz suchen.",
                    due_at=free.free_since,
                    worker_id=free.worker_id,
                )
            )

    # 5. AÜG-Erlaubnis
    lic = license_status(session, today)
    if not lic.valid:
        tasks.append(
            StaffingTaskRead(
                kind="license",
                severity="red",
                title="Keine gültige AÜG-Erlaubnis",
                detail="Ohne gültige Erlaubnis dürfen keine Einsätze aktiv sein.",
            )
        )
    elif lic.traffic in (Traffic.RED, Traffic.YELLOW) and lic.valid_to is not None:
        tasks.append(
            StaffingTaskRead(
                kind="license",
                severity="red" if lic.traffic == Traffic.RED else "yellow",
                title="AÜG-Erlaubnis läuft ab",
                detail=(
                    f"Gültig bis {_fmt(lic.valid_to)} (noch {lic.days_remaining} Tage) – "
                    "Verlängerung beantragen."
                ),
                due_at=lic.valid_to,
            )
        )

    tasks.sort(key=lambda t: (_SEVERITY_ORDER[t.severity], t.due_at or date.max))
    red = sum(t.severity == "red" for t in tasks)
    alerts: list[str] = []
    if red:
        alerts.append(f"{red} dringende Aufgabe(n) bei Fristen, Checklisten oder Erlaubnis.")
    deadlines = sum(t.kind == "deadline_max" for t in tasks)
    if deadlines:
        alerts.append(f"{deadlines} Überlassung(en) nähern sich der Höchstdauer.")
    backlog = sum(t.kind in ("timesheet_overdue", "timesheet_rejected") for t in tasks)
    if backlog:
        alerts.append(f"{backlog} Stundenzettel warten auf Einreichung oder Korrektur.")
    return StaffingTasksRead(
        tasks=tasks,
        alerts=alerts[:3],
        bench_after_days=BENCH_AFTER_DAYS,
        equal_pay_warn_days=config.yellow_days,
    )
