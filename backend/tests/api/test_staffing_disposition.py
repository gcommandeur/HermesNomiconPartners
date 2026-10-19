# ruff: noqa: F811
# NOMICON: Disposition der Ueberlassung - nur in der Nomicon-Kopie.
"""Kennzahlen, Bench und Stundenzettel-Eingang: handgezaehlte Beispiele, Sichtbereich, kein Lohn."""

from __future__ import annotations

import uuid
from datetime import date, timedelta
from decimal import Decimal

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session, sessionmaker

from cc_crm.models.candidate import Candidate
from cc_crm.models.staffing import (
    StaffingAssignment,
    StaffingAssignmentStatus,
    StaffingInvoice,
    StaffingInvoiceLine,
    StaffingTimesheet,
    StaffingTimesheetStatus,
    StaffingWorker,
    StaffingWorkerStatus,
)
from tests.api.test_staffing_api import Crew, crew, make_candidate  # noqa: F401

P = "/api/v1/staffing"
TODAY = date.today()


def _worker(
    session: Session, name: str, status: StaffingWorkerStatus, entry_days_ago: int | None = None
) -> StaffingWorker:
    candidate = Candidate(first_name=name, last_name="Muster")
    session.add(candidate)
    session.flush()
    worker = StaffingWorker(
        candidate_id=candidate.id,
        status=status,
        entry_date=TODAY - timedelta(days=entry_days_ago) if entry_days_ago else None,
        hourly_wage=Decimal("15.40"),
    )
    session.add(worker)
    session.flush()
    return worker


def _assignment(
    session: Session,
    worker: StaffingWorker,
    crew: Crew,
    owner_id: str,
    status: StaffingAssignmentStatus,
    *,
    start_days_ago: int = 60,
    end_days_ago: int | None = None,
) -> StaffingAssignment:
    row = StaffingAssignment(
        worker_id=worker.id,
        client_company_id=uuid.UUID(crew.client_id),
        owner_user_id=uuid.UUID(owner_id),
        start_date=TODAY - timedelta(days=start_days_ago),
        actual_end_date=TODAY - timedelta(days=end_days_ago) if end_days_ago is not None else None,
        billing_rate=Decimal("27.80"),
        hourly_wage=Decimal("15.40"),
        status=status,
    )
    session.add(row)
    session.flush()
    return row


def _sheet(
    session: Session, assignment: StaffingAssignment, status: StaffingTimesheetStatus, ago: int
) -> StaffingTimesheet:
    start = TODAY - timedelta(days=ago + 6)
    row = StaffingTimesheet(
        assignment_id=assignment.id,
        period_start=start,
        period_end=start + timedelta(days=6),
        status=status,
    )
    session.add(row)
    session.flush()
    return row


def test_disposition_counts_bench_and_timesheets(
    client: TestClient, crew: Crew, session_factory: sessionmaker[Session]
) -> None:
    with session_factory() as session:
        busy = _worker(session, "Anna", StaffingWorkerStatus.ACTIVE)  # aktiver Einsatz (A)
        past = _worker(session, "Bert", StaffingWorkerStatus.ACTIVE)  # Einsatz vor 40 Tagen beendet
        never = _worker(session, "Cora", StaffingWorkerStatus.ACTIVE, entry_days_ago=100)
        _worker(session, "Dirk", StaffingWorkerStatus.APPLICANT)  # Anwaerter: nicht auf der Bench
        _worker(session, "Emma", StaffingWorkerStatus.LEFT)  # ausgeschieden: nicht auf der Bench
        mine = _assignment(session, busy, crew, crew.a.id, StaffingAssignmentStatus.ACTIVE)
        _assignment(
            session, busy, crew, crew.c.id, StaffingAssignmentStatus.PLANNED, start_days_ago=-10
        )  # Einsatz eines fremden Disponenten
        _assignment(
            session,
            past,
            crew,
            crew.a.id,
            StaffingAssignmentStatus.ENDED,
            start_days_ago=100,
            end_days_ago=40,
        )
        _sheet(session, mine, StaffingTimesheetStatus.OPEN, ago=20)  # Rueckstand
        _sheet(session, mine, StaffingTimesheetStatus.OPEN, ago=-10)  # Zeitraum laeuft noch
        _sheet(session, mine, StaffingTimesheetStatus.SUBMITTED, ago=30)
        _sheet(session, mine, StaffingTimesheetStatus.REJECTED, ago=40)
        _sheet(session, mine, StaffingTimesheetStatus.APPROVED, ago=50)  # noch nicht abgerechnet
        billed = _sheet(session, mine, StaffingTimesheetStatus.APPROVED, ago=60)
        invoice = StaffingInvoice(
            client_company_id=uuid.UUID(crew.client_id),
            period_start=billed.period_start,
            period_end=billed.period_end,
            amount_net=Decimal("100"),
            vat_rate=Decimal("19"),
            amount_gross=Decimal("119"),
        )
        session.add(invoice)
        session.flush()
        session.add(
            StaffingInvoiceLine(
                invoice_id=invoice.id,
                timesheet_id=billed.id,
                assignment_id=mine.id,
                worker_name="Anna Muster",
                description="x",
                period_start=billed.period_start,
                period_end=billed.period_end,
                hours=Decimal("10"),
                rate=Decimal("10"),
                amount_net=Decimal("100"),
            )
        )
        session.commit()
        never_id = str(never.id)

    body = client.get(f"{P}/disposition", headers=crew.a.headers).json()
    assert (body["active_assignments"], body["planned_assignments"]) == (1, 0)  # nur A's Einsatz
    assert body["inbox"] == {
        "open": 2,
        "open_overdue": 1,
        "submitted": 1,
        "approved_unbilled": 1,
        "rejected": 1,
    }
    assert body["timesheet_backlog"] == 2  # 1 Rueckstand + 1 freigegeben/unabgerechnet
    # Bench: Cora (nie im Einsatz, Eintritt vor 100 Tagen) und Bert (Ende vor 40 Tagen)
    assert [w["worker_name"] for w in body["bench"]] == ["Cora Muster", "Bert Muster"]
    assert [w["days_free"] for w in body["bench"]] == [100, 40]
    assert body["bench"][0]["worker_id"] == never_id and body["bench_count"] == 2
    # kein Lohn, keine Marge
    text = client.get(f"{P}/disposition", headers=crew.a.headers).text
    assert "hourly_wage" not in text and "billing_rate" not in text and "margin" not in text

    # Admin sieht beide Einsaetze (aktiv + geplant); ein anderer Disponent sieht As Eingang nicht
    admin = client.get(f"{P}/disposition", headers=crew.admin.headers).json()
    assert (admin["active_assignments"], admin["planned_assignments"]) == (1, 1)
    other = client.get(f"{P}/disposition", headers=crew.c.headers).json()
    assert other["inbox"]["open"] == 0 and other["inbox"]["submitted"] == 0
    assert other["planned_assignments"] == 1
    assert other["bench_count"] == 2  # die Bench ist ein gemeinsamer Pool


def test_disposition_requires_login_and_the_staffing_view(client: TestClient, crew: Crew) -> None:
    assert client.get(f"{P}/disposition", headers={"Authorization": ""}).status_code == 401
