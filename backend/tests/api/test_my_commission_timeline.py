# ruff: noqa: F811
# NOMICON: Provisionsmodell - nur in der Nomicon-Kopie.
"""Zeitstrahl "Meine Provision" in der API: Werte, laufender Monat, Fortschritt und Rechte
(Mitarbeiter nur sich, Teamleiter ihr Team, Admin alle; fremd und nicht vorhanden = 404)."""

import json
import uuid
from datetime import UTC, date, datetime
from decimal import Decimal

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session, sessionmaker

from cc_crm.models.enums import InvoiceStatus
from tests.api.test_commission_api import assign, set_fee
from tests.api.test_staffing_api import crew, make_candidate
from tests.api.test_team_lead import Team, team

T = "/api/v1/my-commission/timeline"
_ = (crew, make_candidate, team)  # Fixtures (per Import registriert)
FORBIDDEN_KEYS = {"margin", "margin_percent", "employer_cost", "break_even_revenue", "traffic"}


def timeline(client: TestClient, who, user_id: str | None = None):  # type: ignore[no-untyped-def]
    extra = f"?user_id={user_id}" if user_id else ""
    return client.get(f"{T}{extra}", headers=who.headers)


def test_timeline_shows_twelve_months_the_current_one_provisional_and_progress(
    client: TestClient, team: Team, session_factory: sessionmaker[Session]
) -> None:
    assign(client, team.admin, team.a.id, "consultant")
    set_fee(
        session_factory,
        team.a.fee_id,
        amount="20000.00",
        status=InvoiceStatus.PAID,
        paid_at=datetime.now(UTC),
    )
    data = timeline(client, team.a).json()
    today = date.today()
    assert len(data["months"]) == 12
    assert (data["months"][-1]["year"], data["months"][-1]["month"]) == (today.year, today.month)
    current = data["current_month"]
    assert current["is_current"] and current["is_provisional"]
    assert current["revenue"] == "20000.00"
    assert [m["is_current"] for m in data["months"]].count(True) == 1
    # Quartal bisher = Summe der Monate des laufenden Quartals bis heute
    quarter_months = [
        m
        for m in data["months"]
        if m["quarter"] == data["quarter"] and m["year"] == today.year and m["month"] <= today.month
    ]
    assert Decimal(data["quarter_commission"]) == sum(
        Decimal(m["commission"]) for m in quarter_months
    )
    assert Decimal(data["quarter_total"]) == sum(Decimal(m["total"]) for m in quarter_months)
    # Fortschritt: Consultant -> Specialist Consultant ab 48.000 €
    progress = data["progress"]
    assert progress["next_rank_label"] == "Specialist Consultant"
    assert progress["hurdle"] == "48000" and progress["remaining"] == "28000.00"
    assert progress["quarter_revenue"] == "20000.00" and progress["days_to_quarter_end"] >= 0
    assert FORBIDDEN_KEYS.isdisjoint(data) and FORBIDDEN_KEYS.isdisjoint(json.dumps(data))


def test_without_a_rank_only_revenue_and_no_progress(
    client: TestClient, team: Team, session_factory: sessionmaker[Session]
) -> None:
    set_fee(
        session_factory,
        team.a.fee_id,
        amount="5000.00",
        status=InvoiceStatus.PAID,
        paid_at=datetime.now(UTC),
    )
    data = timeline(client, team.a).json()
    assert data["rank_label"] is None and data["progress"] is None
    assert data["current_month"]["revenue"] == "5000.00"
    assert data["current_month"]["commission"] == "0.00"


def test_visibility_follows_the_same_rules_as_my_commission(client: TestClient, team: Team) -> None:
    # Mitarbeiter: nur sich selbst
    assert timeline(client, team.a).status_code == 200
    assert timeline(client, team.a, team.a.id).status_code == 200
    assert timeline(client, team.a, team.c.id).status_code == 404
    assert timeline(client, team.a, str(uuid.uuid4())).status_code == 404  # nicht vorhanden = fremd
    # Teamleiter B: sein Team (A), nicht das Team von C
    assert timeline(client, team.b, team.a.id).status_code == 200
    assert timeline(client, team.c, team.a.id).status_code == 404
    # Admin: alle
    assert timeline(client, team.admin, team.a.id).status_code == 200
    assert timeline(client, team.admin, team.c.id).status_code == 200
