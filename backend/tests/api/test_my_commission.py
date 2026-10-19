# ruff: noqa: F811
# NOMICON: Provisionsmodell - nur in der Nomicon-Kopie.
"""Meine Provision: Rechenweg, Fortschritt zur Befoerderung und Sichtbarkeit je Rolle
(Mitarbeiter nur sich, Teamleiter sich und ihr Team, Admin alle; fremd = 404)."""

import uuid
from datetime import UTC, date, datetime

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session, sessionmaker

from cc_crm.models.enums import InvoiceStatus
from tests.api.test_commission_api import assign, set_fee
from tests.api.test_commission_deals import add_invoice, planned_assignment, six_months
from tests.api.test_staffing_api import Crew, crew, make_candidate
from tests.api.test_team_lead import Team, team

M = "/api/v1/my-commission"
_ = (crew, make_candidate, team)  # Fixtures (per Import registriert)
PAID = datetime(2026, 2, 10, tzinfo=UTC)
FORBIDDEN_KEYS = {"margin", "margin_percent", "employer_cost", "break_even_revenue", "traffic"}


def mine(client: TestClient, who, quarter: int = 1, user_id: str | None = None):  # type: ignore[no-untyped-def]
    extra = f"&user_id={user_id}" if user_id else ""
    return client.get(f"{M}?year=2026&quarter={quarter}{extra}", headers=who.headers)


def test_calculation_is_traceable_and_progress_is_shown(
    client: TestClient, team: Team, session_factory: sessionmaker[Session]
) -> None:
    assign(client, team.admin, team.a.id, "consultant")
    set_fee(
        session_factory, team.a.fee_id, amount="20000.00", status=InvoiceStatus.PAID, paid_at=PAID
    )
    data = mine(client, team.a).json()
    assert data["rank_label"] == "Consultant"
    assert data["next_rank_label"] == "Specialist Consultant"
    assert data["is_top_rank"] is False and data["promotion_hurdle"] == "48000"
    assert data["revenue"] == "20000.00" and data["progress_percent"] == "41.7"
    assert data["explanation"] == [
        "10.000 € frei (Freigrenze 10.000 €)",
        "10.000 € zu 10 % = 1.000 €",
    ]
    assert (data["commission"], data["bonus"], data["fixed_pay"], data["gross"]) == (
        "1000.00",
        "300.00",
        "10000.00",
        "11300.00",
    )
    assert data["placement_deals"] == 1 and data["promotion_label"] is None
    # Keine Marge und keine Firmenkosten in der Antwort
    assert FORBIDDEN_KEYS.isdisjoint(data)


def test_top_rank_and_unassigned_user(
    client: TestClient, team: Team, session_factory: sessionmaker[Session]
) -> None:
    assert mine(client, team.b).json()["rank_key"] is None  # kein Rang zugewiesen
    assign(client, team.admin, team.b.id, "director")
    data = mine(client, team.b).json()
    assert data["is_top_rank"] is True and data["next_rank_label"] is None
    assert data["promotion_hurdle"] is None and data["progress_percent"] is None


def test_unpaid_only_as_expected_hint(
    client: TestClient, team: Team, session_factory: sessionmaker[Session]
) -> None:
    assign(client, team.admin, team.a.id, "consultant")
    set_fee(session_factory, team.a.fee_id, amount="15000.00", status=InvoiceStatus.ISSUED,
            invoice_date=date(2026, 2, 1))  # fmt: skip
    data = mine(client, team.a).json()
    assert data["expected_revenue"] == "15000.00"
    assert data["revenue"] == "0.00" and data["commission"] == "0.00" and data["bonus"] == "0.00"


def test_staffing_breakdown_per_assignment(
    client: TestClient, crew: Crew, make_candidate, session_factory: sessionmaker[Session]
) -> None:
    assignment = planned_assignment(client, crew, make_candidate, date(2026, 6, 30))
    six_months(session_factory, crew, assignment["id"])
    add_invoice(session_factory, crew, assignment["id"], month=7, status=InvoiceStatus.ISSUED)
    assign(client, crew.admin, crew.a.id, "consultant")
    q1 = mine(client, crew.a, 1).json()
    # Januar- und Februar-Rechnung sind im ersten Quartal bezahlt: 2 Monate, 8.000 EUR
    items = q1["staffing_assignments"]
    assert [(i["worker_name"], i["paid_months"], i["revenue"]) for i in items] == [
        ("Mira Muster", 2, "8000.00")
    ]
    q2 = mine(client, crew.a, 2).json()
    items = q2["staffing_assignments"]
    assert [(i["paid_months"], i["revenue"]) for i in items] == [(3, "12000.00")]
    # Juli-Rechnung gestellt, nicht bezahlt: nur Hinweis "erwartet" (ab dem Quartal ihres Datums)
    assert q2["expected_revenue"] == "0.00"
    assert mine(client, crew.a, 3).json()["expected_revenue"] == "4000.00"
    assert q2["staffing_deals"] == 0 and q1["staffing_deals"] == 1


def test_visibility_member_sees_only_self(client: TestClient, team: Team) -> None:
    assign(client, team.admin, team.a.id, "consultant")
    assign(client, team.admin, team.b.id, "manager")
    me = mine(client, team.a)
    assert me.status_code == 200 and me.json()["user_id"] == team.a.id
    assert mine(client, team.a, user_id=team.a.id).status_code == 200
    for other in (team.b, team.c, team.admin):
        assert mine(client, team.a, user_id=other.id).status_code == 404
    assert mine(client, team.a, user_id=str(uuid.uuid4())).status_code == 404
    # Die Antwort fuer mich nennt keine anderen Personen
    text = me.text
    assert team.b.id not in text and "Bernd" not in text and "Clara" not in text
    people = client.get(f"{M}/people", headers=team.a.headers).json()
    assert [(p["user_id"], p["is_self"]) for p in people] == [(team.a.id, True)]


def test_visibility_team_lead_sees_self_and_team(client: TestClient, team: Team) -> None:
    assign(client, team.admin, team.a.id, "consultant")
    assert mine(client, team.b).json()["user_id"] == team.b.id
    assert mine(client, team.b, user_id=team.a.id).json()["user_id"] == team.a.id  # mein Team
    assert mine(client, team.b, user_id=team.c.id).status_code == 404  # anderer Teamleiter
    assert mine(client, team.b, user_id=team.admin.id).status_code == 404
    assert mine(client, team.c, user_id=team.a.id).status_code == 404  # nicht ihr Team
    ids = [p["user_id"] for p in client.get(f"{M}/people", headers=team.b.headers).json()]
    assert ids == [team.b.id, team.a.id]


def test_visibility_admin_sees_everyone(client: TestClient, team: Team) -> None:
    for other in (team.a, team.b, team.c):
        assert mine(client, team.admin, user_id=other.id).json()["user_id"] == other.id
    assert mine(client, team.admin, user_id=str(uuid.uuid4())).status_code == 404
    ids = {p["user_id"] for p in client.get(f"{M}/people", headers=team.admin.headers).json()}
    assert {team.admin.id, team.a.id, team.b.id, team.c.id} <= ids
    assert [p["is_self"] for p in client.get(f"{M}/people", headers=team.admin.headers).json()][0]


def test_my_commission_works_without_the_management_view(client: TestClient, team: Team) -> None:
    """Die Route liegt NICHT hinter der Ansicht "Gesamt": ein normaler Mitarbeiter darf sie nutzen,
    waehrend der Admin-Bericht fuer ihn gesperrt bleibt."""
    assert mine(client, team.a).status_code == 200
    assert client.get("/api/v1/commission/report", headers=team.a.headers).status_code in (403, 404)
