# ruff: noqa: F811
# NOMICON: Provisionsmodell - nur in der Nomicon-Kopie.
"""Deals und Bonus im Provisionsmodell: ein Einsatz = ein Deal, Verlaengerung = neuer Deal,
Zeitpunkt immer nach Zahldatum, Umsatz je Quartal nach Zahldatum, ohne Zahlung weder Bonus noch
Umsatz."""

import uuid
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from cc_crm.models.enums import InvoiceStatus
from cc_crm.models.staffing import (
    StaffingAssignment,
    StaffingAssignmentExtension,
    StaffingAssignmentStatus,
    StaffingInvoice,
    StaffingInvoiceLine,
)
from tests.api.test_commission_api import C, assign, report, set_fee
from tests.api.test_staffing_api import Crew, _assignment, _worker, crew, make_candidate
from tests.api.test_team_lead import Team, team  # noqa: F401

P = "/api/v1/staffing"
_ = (crew, make_candidate)  # Fixtures (per Import registriert)


def planned_assignment(client: TestClient, crew: Crew, make_candidate, end: date | None):  # type: ignore[no-untyped-def]
    worker = _worker(client, crew.a, make_candidate())
    extra = {"planned_end_date": end.isoformat()} if end else {}
    return _assignment(
        client, crew.a, worker["id"], crew.client_id, start_date="2026-01-01", **extra
    )


def add_invoice(
    session_factory: sessionmaker[Session],
    crew: Crew,
    assignment_id: str,
    *,
    month: int,
    amount: str = "4000.00",
    status: InvoiceStatus = InvoiceStatus.PAID,
    paid_on: date | None = None,
    year: int = 2026,
) -> None:
    """Monatsrechnung (ein Monat, eine Zeile); `paid_on` ist das Zahldatum."""
    start = date(year, month, 1)
    end = date(year + (month == 12), month % 12 + 1, 1) - timedelta(days=1)
    with session_factory() as session:
        invoice = StaffingInvoice(
            client_company_id=uuid.UUID(crew.client_id),
            period_start=start,
            period_end=end,
            amount_net=Decimal(amount),
            vat_rate=Decimal("19"),
            amount_gross=Decimal(amount) * Decimal("1.19"),
            invoice_status=status,
            invoice_date=end,
            paid_at=datetime.combine(paid_on, datetime.min.time(), tzinfo=UTC) if paid_on else None,
            created_by_user_id=uuid.UUID(crew.admin.id),
        )
        session.add(invoice)
        session.flush()
        session.add(
            StaffingInvoiceLine(
                invoice_id=invoice.id,
                assignment_id=uuid.UUID(assignment_id),
                worker_name="Mira Muster",
                description=f"Ueberlassung {month:02d}/{year}",
                period_start=start,
                period_end=end,
                hours=Decimal("160"),
                rate=Decimal("25"),
                amount_net=Decimal(amount),
            )
        )
        session.commit()


def six_months(session_factory, crew, assignment_id):  # type: ignore[no-untyped-def]
    """Januar bis Juni je 4.000 EUR, jeweils im Folgemonat am 10. bezahlt."""
    for month in range(1, 7):
        paid_on = date(2026, month + 1, 10)
        add_invoice(session_factory, crew, assignment_id, month=month, paid_on=paid_on)


def row(client: TestClient, admin, user_id: str, quarter: int):  # type: ignore[no-untyped-def]
    data = report(client, admin.headers, 2026, quarter)
    return next(r for r in data["rows"] if r["user_id"] == user_id)


def test_six_month_assignment_is_one_deal_and_revenue_follows_payment(
    client: TestClient, crew: Crew, make_candidate, session_factory: sessionmaker[Session]
) -> None:
    assignment = planned_assignment(client, crew, make_candidate, date(2026, 6, 30))
    six_months(session_factory, crew, assignment["id"])
    assign(client, crew.admin, crew.a.id, "consultant")

    q1, q2, q3 = (row(client, crew.admin, crew.a.id, q) for q in (1, 2, 3))
    # Zahlungen: Feb+Mar (Q1) = 8.000, Apr+Mai+Jun (Q2) = 12.000, Jul (Q3) = 4.000; zusammen 24.000
    assert (q1["revenue_staffing"], q2["revenue_staffing"], q3["revenue_staffing"]) == (
        "8000.00",
        "12000.00",
        "4000.00",
    )
    # EIN Deal fuer sechs Monate: Bonus 300 EUR nur im Quartal der ersten Zahlung (Q1)
    assert (q1["staffing_deals"], q2["staffing_deals"], q3["staffing_deals"]) == (1, 0, 0)
    assert (q1["bonus"], q2["bonus"], q3["bonus"]) == ("300.00", "0.00", "0.00")
    # Provision je Quartal gestaffelt: Q1 unter der Freigrenze, Q2: 2.000 zu 10 %
    assert (q1["commission"], q2["commission"]) == ("0.00", "200.00")
    assert q1["gross"] == "10300.00"  # Fix 10.000 + Provision 0 + Bonus 300
    assert q2["gross"] == "10200.00"


def test_extension_is_detected_and_is_a_new_deal(
    client: TestClient, crew: Crew, make_candidate, session_factory: sessionmaker[Session]
) -> None:
    assignment = planned_assignment(client, crew, make_candidate, date(2026, 6, 30))
    six_months(session_factory, crew, assignment["id"])
    assign(client, crew.admin, crew.a.id, "consultant")
    url = f"{P}/assignments/{assignment['id']}"

    def set_end(day: str) -> None:
        response = client.patch(url, json={"planned_end_date": day}, headers=crew.a.headers)
        assert response.status_code == 200, response.text

    set_end("2026-06-30")  # gleiches Ende: keine Verlaengerung
    set_end("2026-06-20")  # frueheres Ende (Verkuerzung): keine Verlaengerung
    set_end("2026-06-30")  # wieder auf das urspruengliche Ende: nur eine Rueckkehr, aber spaeter
    with session_factory() as session:
        back = session.scalars(select(StaffingAssignmentExtension)).all()
        assert [(e.previous_end, e.new_end) for e in back] == [
            (date(2026, 6, 20), date(2026, 6, 30))
        ]
        for extension in back:
            session.delete(extension)
        session.commit()
    # Verlaengerung bis Dezember: eine Zeile mit dem alten Ende
    set_end("2026-12-31")
    with session_factory() as session:
        extensions = session.scalars(select(StaffingAssignmentExtension)).all()
        assert [(e.previous_end, e.new_end) for e in extensions] == [
            (date(2026, 6, 30), date(2026, 12, 31))
        ]

    # Juli und August (nach dem alten Ende) gehoeren zur Verlaengerung; erste Zahlung am 10.8.
    add_invoice(session_factory, crew, assignment["id"], month=7, paid_on=date(2026, 8, 10))
    add_invoice(session_factory, crew, assignment["id"], month=8, paid_on=date(2026, 9, 10))
    q1, q2, q3 = (row(client, crew.admin, crew.a.id, q) for q in (1, 2, 3))
    assert (q1["staffing_deals"], q2["staffing_deals"], q3["staffing_deals"]) == (1, 0, 1)
    assert q3["bonus"] == "300.00"
    # Die Juni-Rechnung (Zeitraum bis 30.6., bezahlt im Juli) bleibt beim ersten Deal
    assert q3["revenue_staffing"] == "12000.00"  # Jun (Jul) + Jul (Aug) + Aug (Sep)


def test_second_assignment_is_a_new_deal(
    client: TestClient, crew: Crew, make_candidate, session_factory: sessionmaker[Session]
) -> None:
    first = planned_assignment(client, crew, make_candidate, date(2026, 3, 31))
    second = planned_assignment(client, crew, make_candidate, date(2026, 3, 31))
    add_invoice(session_factory, crew, first["id"], month=1, paid_on=date(2026, 2, 10))
    add_invoice(session_factory, crew, second["id"], month=1, paid_on=date(2026, 2, 20))
    assign(client, crew.admin, crew.a.id, "consultant")
    q1 = row(client, crew.admin, crew.a.id, 1)
    assert q1["staffing_deals"] == 2 and q1["bonus"] == "600.00"


def test_no_payment_means_no_bonus_and_no_revenue(
    client: TestClient, crew: Crew, make_candidate, session_factory: sessionmaker[Session]
) -> None:
    assignment = planned_assignment(client, crew, make_candidate, date(2026, 3, 31))
    for status in (InvoiceStatus.DRAFT, InvoiceStatus.ISSUED, InvoiceStatus.DUE):
        add_invoice(session_factory, crew, assignment["id"], month=1, status=status)
    assign(client, crew.admin, crew.a.id, "consultant")
    q1 = row(client, crew.admin, crew.a.id, 1)
    assert q1["revenue_staffing"] == "0.00" and q1["staffing_deals"] == 0 and q1["bonus"] == "0.00"


def test_unpaid_fee_gives_neither_bonus_nor_revenue_paid_fee_gives_both(
    client: TestClient, team: Team, session_factory: sessionmaker[Session]
) -> None:
    assign(client, team.admin, team.a.id, "consultant")
    paid = datetime(2026, 2, 10, tzinfo=UTC)
    set_fee(session_factory, team.a.fee_id, amount="20000.00", status=InvoiceStatus.ISSUED,
            invoice_date=date(2026, 2, 1))  # fmt: skip
    q1 = row(client, team.admin, team.a.id, 1)
    assert q1["revenue_fees"] == "0.00" and q1["placement_deals"] == 0 and q1["bonus"] == "0.00"
    set_fee(
        session_factory, team.a.fee_id, amount="20000.00", status=InvoiceStatus.PAID, paid_at=paid
    )
    q1 = row(client, team.admin, team.a.id, 1)
    assert q1["revenue_fees"] == "20000.00" and q1["placement_deals"] == 1
    assert q1["bonus"] == "300.00" and q1["gross"] == "11300.00"  # Fix 10.000 + 1.000 + 300
    # Der Bonus gehoert in das Quartal der Zahlung, nicht in ein anderes
    assert row(client, team.admin, team.a.id, 2)["placement_deals"] == 0


def test_bonus_amounts_are_editable_separately(
    client: TestClient, team: Team, session_factory: sessionmaker[Session]
) -> None:
    assign(client, team.admin, team.a.id, "consultant")
    set_fee(session_factory, team.a.fee_id, amount="20000.00", status=InvoiceStatus.PAID,
            paid_at=datetime(2026, 2, 10, tzinfo=UTC))  # fmt: skip
    config = client.get(f"{C}/config", headers=team.admin.headers).json()
    body = {k: v for k, v in config.items() if k != "notice"}
    body["general"]["placement_bonus"] = "450"
    body["general"]["staffing_bonus"] = "250"
    assert client.put(f"{C}/config", json=body, headers=team.admin.headers).status_code == 200
    assert row(client, team.admin, team.a.id, 1)["bonus"] == "450.00"
    body["general"]["placement_bonus"] = "-1"
    assert client.put(f"{C}/config", json=body, headers=team.admin.headers).status_code == 422


def test_aborted_assignment_keeps_earned_bonus_but_unpaid_invoices_do_not_count(
    client: TestClient, crew: Crew, make_candidate, session_factory: sessionmaker[Session]
) -> None:
    assignment = planned_assignment(client, crew, make_candidate, date(2026, 6, 30))
    add_invoice(session_factory, crew, assignment["id"], month=1, paid_on=date(2026, 2, 10))
    add_invoice(session_factory, crew, assignment["id"], month=2, status=InvoiceStatus.ISSUED)
    with session_factory() as session:
        session.get(StaffingAssignment, uuid.UUID(assignment["id"])).status = (  # type: ignore[union-attr]
            StaffingAssignmentStatus.ABORTED
        )
        session.commit()
    assign(client, crew.admin, crew.a.id, "consultant")
    q1 = row(client, crew.admin, crew.a.id, 1)
    assert q1["staffing_deals"] == 1 and q1["revenue_staffing"] == "4000.00"
