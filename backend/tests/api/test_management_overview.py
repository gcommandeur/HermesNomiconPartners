# ruff: noqa: F811
# NOMICON: Ansicht "Gesamt" - Rohertrag, Prognose, Kunden mit beiden Geschaeften, Alarme.
from __future__ import annotations

import uuid
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session, sessionmaker

from cc_crm.models.candidate import Candidate
from cc_crm.models.enums import InvoiceStatus, SubmissionStatus
from cc_crm.models.recruiting import Fee, Placement
from cc_crm.models.staffing import (
    StaffingAssignment,
    StaffingAssignmentStatus,
    StaffingTimesheet,
    StaffingTimesheetEntry,
    StaffingTimesheetStatus,
    StaffingWorker,
    StaffingWorkerStatus,
)
from cc_crm.models.submission import CandidateSubmission
from tests.api.test_staffing_api import Crew, crew, make_candidate  # noqa: F401

API = "/api/v1/management/overview"
TODAY = date.today()
NOW = datetime.now(UTC)


def _process(
    session: Session,
    candidate: Candidate,
    client_id: uuid.UUID,
    status: SubmissionStatus,
    fee: str | None,
    probability: float | None,
    owner: str | None,
) -> CandidateSubmission:
    row = CandidateSubmission(
        candidate_id=candidate.id,
        client_company_id=client_id,
        status=status,
        expected_fee=Decimal(fee) if fee else None,
        closing_probability=probability,
        owner_user_id=uuid.UUID(owner) if owner else None,
    )
    session.add(row)
    session.flush()
    return row


def _placement(session: Session, process: CandidateSubmission, amount: str) -> Placement:
    placement = Placement(
        submission_id=process.id,
        start_date=TODAY,
        final_salary=Decimal("60000"),
        fee_percentage=Decimal("20"),
        calculated_fee=Decimal(amount),
    )
    session.add(placement)
    session.flush()
    return placement


def _fee(session: Session, placement: Placement, amount: str, **extra) -> Fee:  # type: ignore[no-untyped-def]
    row = Fee(
        placement_id=placement.id,
        amount_net=Decimal(amount),
        vat_rate=Decimal("19"),
        amount_gross=Decimal(amount) * Decimal("1.19"),
        **extra,
    )
    session.add(row)
    return row


def _worker(
    session: Session, name: str, hours: str | None = "40"
) -> tuple[Candidate, StaffingWorker]:
    candidate = Candidate(first_name=name, last_name="Muster")
    session.add(candidate)
    session.flush()
    worker = StaffingWorker(
        candidate_id=candidate.id,
        status=StaffingWorkerStatus.ACTIVE,
        weekly_hours=Decimal(hours) if hours else None,
    )
    session.add(worker)
    session.flush()
    return candidate, worker


def test_management_overview_gross_profit_forecast_and_alerts(
    client: TestClient, crew: Crew, session_factory: sessionmaker[Session]
) -> None:
    client_id = uuid.UUID(crew.client_id)
    with session_factory() as session:
        c1 = Candidate(first_name="Eins", last_name="K")
        c2 = Candidate(first_name="Zwei", last_name="K")
        c3 = Candidate(first_name="Drei", last_name="K")
        session.add_all([c1, c2, c3])
        session.flush()
        # --- Rohertrag Direct: nur bezahlte Honorare im Zeitraum (Woche)
        placed = _process(
            session, c1, client_id, SubmissionStatus.PLACEMENT, "12000", 1.0, crew.a.id
        )
        placement = _placement(session, placed, "12000")
        _fee(session, placement, "12000", invoice_status=InvoiceStatus.PAID, paid_at=NOW)
        _fee(
            session,
            placement,
            "5000",
            invoice_status=InvoiceStatus.PAID,
            paid_at=NOW - timedelta(days=100),
        )  # zu alt
        _fee(
            session,
            placement,
            "7000",
            invoice_status=InvoiceStatus.ISSUED,
            invoice_date=TODAY - timedelta(days=40),
            payment_due_date=TODAY - timedelta(days=10),
        )  # nicht bezahlt, ueberfaellig -> Alarm
        # --- Prognose Direct
        _process(
            session, c2, client_id, SubmissionStatus.INTERVIEW, "10000", 0.5, crew.a.id
        )  # 5.000
        _process(session, c3, client_id, SubmissionStatus.OFFER, "20000", 0.25, crew.a.id)  # 5.000
        _process(
            session, c1, client_id, SubmissionStatus.CV_OUT, "8000", None, crew.a.id
        )  # ohne p.
        _process(session, c2, client_id, SubmissionStatus.CV_IN, None, 0.4, None)  # ohne Fee/Owner
        # --- Ueberlassung: freigegebene Stunden im Zeitraum
        _, worker = _worker(session, "Anna")
        assignment = StaffingAssignment(
            worker_id=worker.id,
            client_company_id=client_id,
            owner_user_id=uuid.UUID(crew.a.id),
            start_date=TODAY - timedelta(days=60),
            planned_end_date=TODAY + timedelta(days=14),
            billing_rate=Decimal("27.80"),
            hourly_wage=Decimal("15.40"),
            status=StaffingAssignmentStatus.ACTIVE,
        )
        session.add(assignment)
        session.flush()
        sheet = StaffingTimesheet(
            assignment_id=assignment.id,
            period_start=TODAY - timedelta(days=7),
            period_end=TODAY - timedelta(days=1),
            status=StaffingTimesheetStatus.APPROVED,
            decided_at=NOW,
        )
        session.add(sheet)
        session.flush()
        for offset in range(5):  # 5 x 8 = 40 Stunden
            session.add(
                StaffingTimesheetEntry(
                    timesheet_id=sheet.id,
                    work_date=TODAY - timedelta(days=7 - offset),
                    hours=Decimal("8"),
                )
            )
        # freigegeben, aber Satz fehlt: wird gezaehlt, nicht gerechnet
        _, worker2 = _worker(session, "Bert")
        no_rate = StaffingAssignment(
            worker_id=worker2.id,
            client_company_id=client_id,
            owner_user_id=uuid.UUID(crew.a.id),
            start_date=TODAY - timedelta(days=30),
            status=StaffingAssignmentStatus.PLANNED,
        )
        session.add(no_rate)
        session.flush()
        session.add(
            StaffingTimesheet(
                assignment_id=no_rate.id,
                period_start=TODAY - timedelta(days=7),
                period_end=TODAY - timedelta(days=1),
                status=StaffingTimesheetStatus.APPROVED,
                decided_at=NOW,
            )
        )
        session.commit()

    body = client.get(f"{API}?period=week", headers=crew.admin.headers).json()
    assert Decimal(body["employer_factor"]) == Decimal("1.23")
    gross = body["gross_profit"]
    assert Decimal(gross["direct"]) == Decimal("12000.00")  # nur das frische, bezahlte Honorar
    assert Decimal(gross["staffing"]) == Decimal("354.32")  # 40 h x (27,80 - 15,40 x 1,23)
    assert Decimal(gross["total"]) == Decimal("12354.32")
    assert Decimal(gross["staffing_hours"]) == Decimal("40")
    assert gross["staffing_missing_rates"] == 1
    forecast = body["forecast"]
    assert Decimal(forecast["direct_weighted"]) == Decimal("10000.00")  # 5.000 + 5.000
    assert (forecast["direct_without_probability"], forecast["direct_without_fee"]) == (1, 1)
    assert Decimal(forecast["staffing_margin"]) == Decimal("708.64")  # 8,858 x 40 x 2 Wochen
    assert (forecast["staffing_counted"], forecast["staffing_excluded"]) == (1, 0)
    assert Decimal(forecast["total"]) == Decimal("10708.64")
    # Quartal holt das alte Honorar dazu (100 Tage: noch ausserhalb), Monat ebenso nicht
    quarter = client.get(f"{API}?period=quarter", headers=crew.admin.headers).json()
    assert Decimal(quarter["gross_profit"]["direct"]) == Decimal("12000.00")
    # Kunde mit beiden Geschaeften, Alarme
    both = body["both_business_clients"]
    assert [c["client_name"] for c in both] == ["Beispiel Logistik GmbH"]
    assert both[0]["assignments"] == 2 and both[0]["placements"] == 1
    kinds = {a["kind"] for a in body["alerts"]}
    assert {"invoices_overdue", "processes_without_owner", "license"} <= kinds
    assert len(body["assumptions"]) == 4


def test_management_overview_is_admin_only_and_hides_nothing_for_admins(
    client: TestClient, crew: Crew
) -> None:
    for person in (crew.a, crew.b, crew.c):  # auch Teamleiter: Gesamt ist nur Admins
        assert client.get(API, headers=person.headers).status_code == 403
    assert client.get(API, headers=crew.admin.headers).status_code == 200
    assert client.get(f"{API}?period=year", headers=crew.admin.headers).status_code == 422
    assert client.get(API, headers={"Authorization": ""}).status_code == 401
