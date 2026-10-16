# ruff: noqa: F811
# NOMICON: Provisionsmodell - nur in der Nomicon-Kopie.
"""Provisionsmodell ueber die API: nur Admins, Einstellungen, Rangzuordnung, Quartalsbericht mit
echtem Umsatz aus Vermittlungshonoraren und Ueberlassungsrechnungen."""

import uuid
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session, sessionmaker

from cc_crm.models.enums import InvoiceStatus
from cc_crm.models.recruiting import Fee
from cc_crm.services.commission_report import current_quarter
from tests.api.test_staffing_api import Crew, crew, make_candidate
from tests.api.test_staffing_billing import approved_sheet, draft
from tests.api.test_staffing_timesheets import public
from tests.api.test_team_lead import Team, team  # noqa: F401

C = "/api/v1/commission"
YEAR, QUARTER = current_quarter()

_ = (crew, make_candidate, public)  # Fixtures (per Import registriert)


def set_fee(
    session_factory: sessionmaker[Session],
    fee_id: str,
    *,
    amount: str,
    status: InvoiceStatus,
    paid_at: datetime | None = None,
    invoice_date: date | None = None,
) -> None:
    with session_factory() as session:
        fee = session.get(Fee, uuid.UUID(fee_id))
        assert fee is not None
        fee.amount_net = Decimal(amount)
        fee.invoice_status = status
        fee.paid_at = paid_at
        fee.invoice_date = invoice_date
        session.commit()


def report(client: TestClient, headers: dict[str, str], year: int = YEAR, quarter: int = QUARTER):  # type: ignore[no-untyped-def]
    response = client.get(f"{C}/report?year={year}&quarter={quarter}", headers=headers)
    assert response.status_code == 200, response.text
    return response.json()


def assign(client: TestClient, admin, user_id: str, rank: str | None):  # type: ignore[no-untyped-def]
    response = client.put(
        f"{C}/users/{user_id}/rank", json={"rank_key": rank}, headers=admin.headers
    )
    assert response.status_code == 200, response.text
    return response.json()


# --- Zugriff -----------------------------------------------------------------------------------


def test_everything_is_admin_only(client: TestClient, team: Team) -> None:  # noqa: F811
    config = client.get(f"{C}/config", headers=team.admin.headers).json()
    body = {k: v for k, v in config.items() if k != "notice"}
    calls = [
        ("get", f"{C}/config", None),
        ("put", f"{C}/config", body),
        ("get", f"{C}/report", None),
        ("get", f"{C}/users", None),
        ("put", f"{C}/users/{team.a.id}/rank", {"rank_key": "consultant"}),
    ]
    for person in (team.a, team.b):  # Mitarbeiter und Teamleiter
        for method, url, payload in calls:
            response = client.request(method.upper(), url, json=payload, headers=person.headers)
            assert response.status_code == 403, (person.id, method, url)
    anonymous = TestClient(client.app)
    assert anonymous.get(f"{C}/report").status_code == 401
    for method, url, payload in calls:
        assert (
            client.request(
                method.upper(), url, json=payload, headers=team.admin.headers
            ).status_code
            == 200
        )


# --- Einstellungen -----------------------------------------------------------------------------


def test_config_defaults_roundtrip_and_validation(client: TestClient, team: Team) -> None:  # noqa: F811
    config = client.get(f"{C}/config", headers=team.admin.headers).json()
    assert [r["key"] for r in config["ranks"]] == [
        "consultant", "specialist", "senior", "manager", "principal", "director",
    ]  # fmt: skip
    assert config["general"]["commission_free_base"] == "10000"
    assert config["general"]["employer_factor"] == "1.23"
    assert config["general"]["target_margin"] == "50"
    assert config["ranks"][0]["fixed_yearly"] == "40000"
    assert config["revenue_basis"] == {
        "placement_fees": "paid",
        "include_staffing": True,
        "staffing": "issued",
    }
    assert "Excel" in config["notice"]

    body = {k: v for k, v in config.items() if k != "notice"}
    body["general"]["target_margin"] = "40"
    body["ranks"][0]["fixed_yearly"] = "41000"
    saved = client.put(f"{C}/config", json=body, headers=team.admin.headers)
    assert saved.status_code == 200, saved.text
    again = client.get(f"{C}/config", headers=team.admin.headers).json()
    assert Decimal(again["general"]["target_margin"]) == 40
    assert Decimal(again["ranks"][0]["fixed_yearly"]) == 41000
    assert "config_changed" in client.get("/api/v1/audit-logs", headers=team.admin.headers).text

    def put(mutate):  # type: ignore[no-untyped-def]
        payload = {k: v for k, v in again.items() if k != "notice"}
        mutate(payload)
        return client.put(f"{C}/config", json=payload, headers=team.admin.headers)

    assert put(lambda p: p["ranks"][0].update(threshold1="50000")).status_code == 422  # S1 >= S2
    assert (
        put(lambda p: p["ranks"][1].update(key="consultant")).status_code == 422
    )  # doppelter Schluessel
    assert put(lambda p: p["general"].update(employer_factor="0.5")).status_code == 422
    assert put(lambda p: p["general"].update(target_margin="99")).status_code == 422
    assert (
        put(lambda p: p["general"].update(target_margin="70")).status_code == 422
    )  # frisst die Marge
    assert put(lambda p: p["revenue_basis"].update(staffing="nie")).status_code == 422
    assert put(lambda p: p.update(ranks=[])).status_code == 422
    # Nach den abgelehnten Versuchen bleibt die gespeicherte Konfiguration unveraendert
    assert (
        Decimal(
            client.get(f"{C}/config", headers=team.admin.headers).json()["general"]["target_margin"]
        )
        == 40
    )


# --- Raenge ------------------------------------------------------------------------------------


def test_rank_assignment(client: TestClient, team: Team) -> None:  # noqa: F811
    listed = {u["user_id"]: u for u in client.get(f"{C}/users", headers=team.admin.headers).json()}
    assert listed[team.a.id]["rank_key"] is None
    done = assign(client, team.admin, team.a.id, "consultant")
    assert done["rank_key"] == "consultant"
    wrong = client.put(
        f"{C}/users/{team.a.id}/rank", json={"rank_key": "ceo"}, headers=team.admin.headers
    )
    assert wrong.status_code == 422
    missing = client.put(
        f"{C}/users/{uuid.uuid4()}/rank", json={"rank_key": "consultant"}, headers=team.admin.headers
    )
    assert missing.status_code == 404
    assert assign(client, team.admin, team.a.id, None)["rank_key"] is None  # entfernen
    assert "rank_changed" in client.get("/api/v1/audit-logs", headers=team.admin.headers).text


# --- Bericht mit Vermittlungshonoraren ---------------------------------------------------------


def test_report_from_paid_placement_fees(
    client: TestClient, team: Team, session_factory: sessionmaker[Session]
) -> None:  # noqa: F811
    now = datetime.now(UTC)
    set_fee(
        session_factory, team.a.fee_id, amount="20000.00", status=InvoiceStatus.PAID, paid_at=now
    )
    set_fee(
        session_factory, team.b.fee_id, amount="50000.00", status=InvoiceStatus.PAID, paid_at=now
    )
    # C: bezahlt, aber ohne Rang -> unter "ohne Rang"; nur ein Entwurf zaehlt nirgends
    set_fee(
        session_factory, team.c.fee_id, amount="8000.00", status=InvoiceStatus.PAID, paid_at=now
    )
    assign(client, team.admin, team.a.id, "consultant")
    assign(client, team.admin, team.b.id, "consultant")

    data = report(client, team.admin.headers)
    rows = {r["user_id"]: r for r in data["rows"]}
    a = rows[team.a.id]
    assert (
        a["revenue"] == "20000.00"
        and a["revenue_fees"] == "20000.00"
        and a["revenue_staffing"] == "0.00"
    )
    assert a["commission"] == "1000.00"  # 10.000 zu 10 %
    assert (a["band1_revenue"], a["band2_revenue"], a["band3_revenue"]) == (
        "10000.00",
        "0.00",
        "0.00",
    )
    assert a["fixed_pay"] == "10000.00" and a["employer_cost"] == "15030.00"
    assert a["margin"] == "4970.00" and a["margin_percent"] == "24.85"
    assert a["traffic"] == "yellow"
    assert a["break_even_revenue"] == "14332.96"
    assert a["promotion_to_key"] is None and a["promotion_hurdle"] == "48000"
    assert (a["bonus"], a["gross"]) == ("0.00", "11000.00")
    b = rows[team.b.id]
    assert b["revenue"] == "50000.00"
    assert (
        b["promotion_to_key"] == "specialist"
        and b["promotion_to_label"] == "Specialist Consultant"
    )  # Huerde 48.000 erreicht, 60.000 noch nicht
    assert b["traffic"] == "green"
    assert [u["user_id"] for u in data["unassigned"]] == [team.c.id]
    assert data["unassigned"][0]["revenue"] == "8000.00"
    totals = data["totals"]
    assert totals["revenue"] == "70000.00"
    assert Decimal(totals["employer_cost"]) == Decimal(a["employer_cost"]) + Decimal(
        b["employer_cost"]
    )
    assert data["period_start"] == date(YEAR, 3 * QUARTER - 2, 1).isoformat()


def test_report_period_and_basis_switch(
    client: TestClient, team: Team, session_factory: sessionmaker[Session]
) -> None:  # noqa: F811
    assign(client, team.admin, team.a.id, "consultant")
    # Im VORIGEN Quartal bezahlt zaehlt nicht; gestellt (unbezahlt) im laufenden nur mit "issued"
    long_ago = datetime.now(UTC) - timedelta(days=120)
    set_fee(
        session_factory,
        team.a.fee_id,
        amount="30000.00",
        status=InvoiceStatus.PAID,
        paid_at=long_ago,
    )
    assert report(client, team.admin.headers)["rows"][0]["revenue"] == "0.00"
    set_fee(
        session_factory, team.a.fee_id, amount="30000.00", status=InvoiceStatus.ISSUED,
        invoice_date=date.today(),
    )  # fmt: skip
    assert (
        report(client, team.admin.headers)["rows"][0]["revenue"] == "0.00"
    )  # nur bezahlte zaehlen
    config = client.get(f"{C}/config", headers=team.admin.headers).json()
    body = {k: v for k, v in config.items() if k != "notice"}
    body["revenue_basis"]["placement_fees"] = "issued"
    assert client.put(f"{C}/config", json=body, headers=team.admin.headers).status_code == 200
    row = report(client, team.admin.headers)["rows"][0]
    assert row["revenue"] == "30000.00" and row["commission"] == "2100.00"
    assert row["promotion_to_key"] is None  # Huerde 48.000 nicht erreicht
    # Bericht fuer ein anderes Quartal bleibt leer; ungueltige Quartale werden abgelehnt
    other = (QUARTER % 4) + 1
    assert (
        report(client, team.admin.headers, YEAR + (1 if other == 1 else 0), other)["rows"][0][
            "revenue"
        ]
        == "0.00"
    )
    assert client.get(f"{C}/report?quarter=5", headers=team.admin.headers).status_code == 422
    assert client.get(f"{C}/report?year=1999", headers=team.admin.headers).status_code == 422


def test_no_ranked_users_gives_an_empty_green_report(client: TestClient, team: Team) -> None:  # noqa: F811
    data = report(client, team.admin.headers)
    assert data["rows"] == [] and data["totals"]["traffic"] == "green"


# --- Bericht mit Ueberlassungsrechnungen -------------------------------------------------------


def test_staffing_invoices_count_for_the_dispatcher(
    client: TestClient, crew: Crew, make_candidate, public: TestClient
) -> None:  # type: ignore[no-untyped-def]
    _assignment, sheet = approved_sheet(
        client, crew, make_candidate, public
    )  # A: 24 Std. x 28,50 = 684,00
    invoice = draft(client, crew.a, sheet["id"]).json()
    assign(client, crew.admin, crew.a.id, "consultant")
    # Entwurf zaehlt nicht
    assert report(client, crew.admin.headers)["rows"][0]["revenue_staffing"] == "0.00"
    issued = client.post(
        f"/api/v1/staffing/invoices/{invoice['id']}/status",
        json={"invoice_status": "issued"},
        headers=crew.admin.headers,
    )
    assert issued.status_code == 200
    row = report(client, crew.admin.headers)["rows"][0]
    assert row["revenue_staffing"] == "684.00" and row["revenue"] == "684.00"
    # Einstellung: Ueberlassung ganz ausblenden, bzw. nur bezahlte Rechnungen
    config = client.get(f"{C}/config", headers=crew.admin.headers).json()
    body = {k: v for k, v in config.items() if k != "notice"}
    body["revenue_basis"]["staffing"] = "paid"
    client.put(f"{C}/config", json=body, headers=crew.admin.headers)
    assert report(client, crew.admin.headers)["rows"][0]["revenue_staffing"] == "0.00"
    client.post(
        f"/api/v1/staffing/invoices/{invoice['id']}/status",
        json={"invoice_status": "paid"},
        headers=crew.admin.headers,
    )
    assert report(client, crew.admin.headers)["rows"][0]["revenue_staffing"] == "684.00"
    body["revenue_basis"]["include_staffing"] = False
    client.put(f"{C}/config", json=body, headers=crew.admin.headers)
    assert report(client, crew.admin.headers)["rows"][0]["revenue_staffing"] == "0.00"
    body["revenue_basis"]["include_staffing"] = True
    client.put(f"{C}/config", json=body, headers=crew.admin.headers)
    assert report(client, crew.admin.headers)["rows"][0]["revenue_staffing"] == "684.00"
