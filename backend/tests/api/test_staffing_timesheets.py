# ruff: noqa: F811
# NOMICON: Arbeitnehmerueberlassung - nur in der Nomicon-Kopie.
"""Stundenzettel und Kundenfreigabe per Link: Ablauf und Sicherheit (Token, Ablauf, Raten)."""

from datetime import UTC, date, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from cc_crm.models.staffing import StaffingTimesheet
from cc_crm.services.staffing_timesheets import hash_token
from tests.api.test_staffing_api import (
    Crew,
    _assignment,
    _complete_checklist,
    _license,
    _worker,
    crew,
    make_candidate,
)

P = "/api/v1/staffing"
PUBLIC = "/api/v1/public/timesheets"
TODAY = date.today()
START = TODAY - timedelta(days=40)  # Einsatzbeginn
MONTH_START = TODAY - timedelta(days=30)
MONTH_END = TODAY - timedelta(days=1)

_ = (crew, make_candidate)  # Fixtures (per Import registriert)


@pytest.fixture(autouse=True)
def _fresh_rate_limiter():  # type: ignore[no-untyped-def]
    from cc_crm.api.v1.staffing_public import timesheet_link_rate_limiter

    yield
    timesheet_link_rate_limiter.reset()


@pytest.fixture
def public(client: TestClient) -> TestClient:
    """Kunde ohne Login: gleiche App und Datenbank, aber ohne Authorization-Header."""
    return TestClient(client.app)


def _active_assignment(client: TestClient, crew: Crew, make_candidate, who=None) -> dict:  # type: ignore[no-untyped-def]
    who = who or crew.a
    if not client.get(f"{P}/licenses", headers=crew.admin.headers).json():
        _license(client, crew)
    worker = _worker(client, who, make_candidate())
    assignment = _assignment(
        client, who, worker["id"], crew.client_id, start_date=START.isoformat()
    )
    _complete_checklist(client, who, assignment["id"])
    response = client.post(
        f"{P}/assignments/{assignment['id']}/status", json={"status": "active"}, headers=who.headers
    )
    assert response.status_code == 200, response.text
    return assignment


def _sheet(
    client: TestClient, who, assignment_id: str, start: date = MONTH_START, end: date = MONTH_END
) -> dict:  # type: ignore[no-untyped-def]
    response = client.post(
        f"{P}/assignments/{assignment_id}/timesheets",
        json={"period_start": start.isoformat(), "period_end": end.isoformat()},
        headers=who.headers,
    )
    assert response.status_code == 201, response.text
    return response.json()


def _entries(days: int = 3, hours: str = "8.00") -> dict:
    return {
        "entries": [
            {
                "work_date": (MONTH_START + timedelta(days=i)).isoformat(),
                "hours": hours,
                "break_minutes": 30,
            }
            for i in range(days)
        ]
    }


def _submitted(client: TestClient, crew: Crew, make_candidate) -> tuple[dict, dict, str]:  # type: ignore[no-untyped-def]
    assignment = _active_assignment(client, crew, make_candidate)
    sheet = _sheet(client, crew.a, assignment["id"])
    put = client.put(
        f"{P}/timesheets/{sheet['id']}/entries", json=_entries(), headers=crew.a.headers
    )
    assert put.status_code == 200, put.text
    submit = client.post(f"{P}/timesheets/{sheet['id']}/submit", headers=crew.a.headers)
    assert submit.status_code == 200, submit.text
    token = submit.json()["approval_path"].removeprefix("/stundenzettel/")
    return assignment, sheet, token


# --- Ablauf ------------------------------------------------------------------------------------


def test_full_flow_with_customer_approval(
    client: TestClient, crew: Crew, make_candidate, public: TestClient
) -> None:  # type: ignore[no-untyped-def]
    assignment, sheet, token = _submitted(client, crew, make_candidate)
    assert len(token) >= 40  # 256 Bit Zufall

    internal = client.get(f"{P}/timesheets/{sheet['id']}", headers=crew.a.headers).json()
    assert internal["status"] == "submitted"
    assert internal["total_hours"] == "24.00"
    assert internal["approval_link_expires_at"] is not None
    assert "approval_token_hash" not in internal and token not in str(internal)

    # Der Kunde sieht nur das Noetige - keine IDs, kein Lohn, keine Marge
    view = public.get(f"{PUBLIC}/{token}")
    assert view.status_code == 200, view.text
    data = view.json()
    assert set(data) == {
        "worker_name",
        "client_name",
        "period_start",
        "period_end",
        "status",
        "total_hours",
        "entries",
        "decided_at",
        "decided_by_name",
        "rejection_reason",
        "expires_at",
    }
    assert data["client_name"] == "Beispiel Logistik GmbH"
    assert data["total_hours"] == "24.00"
    assert len(data["entries"]) == 3
    for forbidden in ("hourly_wage", "billing_rate", "assignment_id", "owner_user_id"):
        assert forbidden not in view.text

    approved = public.post(f"{PUBLIC}/{token}/approve", json={"approver_name": "Petra Kunde"})
    assert approved.status_code == 200, approved.text
    assert approved.json()["status"] == "approved"
    assert approved.json()["decided_by_name"] == "Petra Kunde"

    done = client.get(f"{P}/timesheets/{sheet['id']}", headers=crew.a.headers).json()
    assert done["status"] == "approved"
    assert done["decided_by_name"] == "Petra Kunde"
    assert done["approval_link_expires_at"] is None
    # Freigegeben ist endgueltig
    assert (
        client.put(
            f"{P}/timesheets/{sheet['id']}/entries", json=_entries(), headers=crew.a.headers
        ).status_code
        == 422
    )
    assert (
        client.post(f"{P}/timesheets/{sheet['id']}/submit", headers=crew.a.headers).status_code
        == 422
    )
    # Liste am Einsatz
    listed = client.get(
        f"{P}/assignments/{assignment['id']}/timesheets", headers=crew.a.headers
    ).json()
    assert [s["id"] for s in listed] == [sheet["id"]]
    # Audit (Admin): Einreichen und Freigabe mit Namen des Kunden
    log = client.get("/api/v1/audit-logs", headers=crew.admin.headers).text
    assert "submitted" in log and "approved" in log and "Kunde: Petra Kunde" in log


def test_rejection_reopens_and_a_new_link_replaces_the_old_one(
    client: TestClient, crew: Crew, make_candidate, public: TestClient
) -> None:  # type: ignore[no-untyped-def]
    _assignment_, sheet, token = _submitted(client, crew, make_candidate)
    rejected = public.post(
        f"{PUBLIC}/{token}/reject",
        json={"approver_name": "Petra Kunde", "reason": "Stunden am 3. falsch"},
    )
    assert rejected.status_code == 200 and rejected.json()["status"] == "rejected"
    internal = client.get(f"{P}/timesheets/{sheet['id']}", headers=crew.a.headers).json()
    assert internal["status"] == "rejected"
    assert internal["rejection_reason"] == "Stunden am 3. falsch"

    # Link ist verbraucht
    assert public.get(f"{PUBLIC}/{token}").status_code == 410
    # Korrektur macht den Zettel wieder offen, Einreichen erzeugt einen NEUEN Link
    fixed = client.put(
        f"{P}/timesheets/{sheet['id']}/entries", json=_entries(hours="7.50"), headers=crew.a.headers
    ).json()
    assert fixed["status"] == "open" and fixed["rejection_reason"] is None
    second = client.post(f"{P}/timesheets/{sheet['id']}/submit", headers=crew.a.headers).json()
    new_token = second["approval_path"].removeprefix("/stundenzettel/")
    assert new_token != token
    assert public.get(f"{PUBLIC}/{new_token}").json()["total_hours"] == "22.50"

    # Erneutes Einreichen ("Link neu erzeugen") entwertet auch den vorherigen, noch ungenutzten Link
    third = client.post(f"{P}/timesheets/{sheet['id']}/submit", headers=crew.a.headers).json()
    assert public.get(f"{PUBLIC}/{new_token}").status_code in (404, 410)
    assert (
        public.get(f"{PUBLIC}/{third['approval_path'].removeprefix('/stundenzettel/')}").status_code
        == 200
    )


# --- Sicherheit des Links ----------------------------------------------------------------------


def test_only_the_hash_is_stored(
    client: TestClient, crew: Crew, make_candidate, session_factory: sessionmaker[Session]
) -> None:  # type: ignore[no-untyped-def]
    _a, sheet, token = _submitted(client, crew, make_candidate)
    with session_factory() as session:
        row = session.scalars(select(StaffingTimesheet)).one()
        assert row.approval_token_hash == hash_token(token)
        assert len(row.approval_token_hash) == 64
        assert token not in (row.approval_token_hash or "")
        assert row.approval_token_expires_at is not None


def test_unknown_token_is_404_and_expired_is_410(
    client: TestClient,
    crew: Crew,
    make_candidate,
    public: TestClient,
    session_factory: sessionmaker[Session],
) -> None:  # type: ignore[no-untyped-def]
    _a, _s, token = _submitted(client, crew, make_candidate)
    assert public.get(f"{PUBLIC}/{'x' * 43}").status_code == 404
    assert (
        public.post(f"{PUBLIC}/{'y' * 43}/approve", json={"approver_name": "Petra"}).status_code
        == 404
    )

    with session_factory() as session:
        row = session.scalars(select(StaffingTimesheet)).one()
        row.approval_token_expires_at = datetime.now(UTC) - timedelta(minutes=1)
        session.commit()
    assert public.get(f"{PUBLIC}/{token}").status_code == 410
    assert (
        public.post(f"{PUBLIC}/{token}/approve", json={"approver_name": "Petra Kunde"}).status_code
        == 410
    )
    # abgelaufen darf nichts veraendern
    assert (
        client.get(f"{P}/timesheets/{_s['id']}", headers=crew.a.headers).json()["status"]
        == "submitted"
    )
    # Mit einem neuen Link geht es wieder
    renewed = client.post(f"{P}/timesheets/{_s['id']}/submit", headers=crew.a.headers).json()
    assert (
        public.get(f"{PUBLIC}{renewed['approval_path'].removeprefix('/stundenzettel')}").status_code
        == 200
    )


def test_token_is_single_use(
    client: TestClient, crew: Crew, make_candidate, public: TestClient
) -> None:  # type: ignore[no-untyped-def]
    _a, sheet, token = _submitted(client, crew, make_candidate)
    assert (
        public.post(f"{PUBLIC}/{token}/approve", json={"approver_name": "Petra Kunde"}).status_code
        == 200
    )
    again = public.post(
        f"{PUBLIC}/{token}/reject", json={"approver_name": "Mallory", "reason": "doch nicht"}
    )
    assert again.status_code == 410
    after = client.get(f"{P}/timesheets/{sheet['id']}", headers=crew.a.headers).json()
    assert after["status"] == "approved" and after["decided_by_name"] == "Petra Kunde"


def test_a_token_only_works_for_its_own_timesheet(
    client: TestClient, crew: Crew, make_candidate, public: TestClient
) -> None:  # type: ignore[no-untyped-def]
    assignment, sheet_a, token_a = _submitted(client, crew, make_candidate)
    other = _active_assignment(client, crew, make_candidate)
    sheet_b = _sheet(client, crew.a, other["id"])
    client.put(f"{P}/timesheets/{sheet_b['id']}/entries", json=_entries(2), headers=crew.a.headers)
    client.post(f"{P}/timesheets/{sheet_b['id']}/submit", headers=crew.a.headers)

    public.post(f"{PUBLIC}/{token_a}/approve", json={"approver_name": "Petra Kunde"})
    states = {
        s: client.get(f"{P}/timesheets/{s}", headers=crew.a.headers).json()["status"]
        for s in (sheet_a["id"], sheet_b["id"])
    }
    assert states == {sheet_a["id"]: "approved", sheet_b["id"]: "submitted"}
    # Eine ID im Link-Platz ist kein Token
    assert public.get(f"{PUBLIC}/{sheet_b['id']}").status_code == 404
    assert public.get(f"{PUBLIC}/{assignment['id']}").status_code == 404


def test_failed_lookups_are_rate_limited_before_the_token_is_checked(
    client: TestClient, crew: Crew, make_candidate, public: TestClient
) -> None:  # type: ignore[no-untyped-def]
    _a, _s, token = _submitted(client, crew, make_candidate)
    codes = [public.get(f"{PUBLIC}/guess{i:040d}").status_code for i in range(12)]
    assert codes[:10] == [404] * 10
    assert codes[10:] == [429, 429]
    # ab hier wird gar nicht mehr nachgeschlagen: auch der ECHTE Link bekommt 429
    assert public.get(f"{PUBLIC}/{token}").status_code == 429
    assert (
        public.post(f"{PUBLIC}/{token}/approve", json={"approver_name": "Petra Kunde"}).status_code
        == 429
    )


def test_public_input_is_validated(
    client: TestClient, crew: Crew, make_candidate, public: TestClient
) -> None:  # type: ignore[no-untyped-def]
    _a, _s, token = _submitted(client, crew, make_candidate)
    assert public.post(f"{PUBLIC}/{token}/approve", json={"approver_name": "P"}).status_code == 422
    assert public.post(f"{PUBLIC}/{token}/approve", json={}).status_code == 422
    assert (
        public.post(f"{PUBLIC}/{token}/reject", json={"approver_name": "Petra Kunde"}).status_code
        == 422
    )
    assert (
        public.post(
            f"{PUBLIC}/{token}/reject", json={"approver_name": "Petra Kunde", "reason": "x"}
        ).status_code
        == 422
    )
    # Unveraendert und weiter nutzbar
    assert public.get(f"{PUBLIC}/{token}").status_code == 200


def test_public_routes_are_exactly_the_three_expected_ones(client: TestClient) -> None:
    paths = client.app.openapi()["paths"]  # type: ignore[attr-defined]
    public_ops = sorted(
        (method.upper(), path)
        for path, item in paths.items()
        if "/public/" in path
        for method in item
    )
    assert public_ops == [
        ("GET", "/api/v1/public/timesheets/{token}"),
        ("POST", "/api/v1/public/timesheets/{token}/approve"),
        ("POST", "/api/v1/public/timesheets/{token}/reject"),
    ]


# --- Erfassung ---------------------------------------------------------------------------------


def test_timesheet_validation(client: TestClient, crew: Crew, make_candidate) -> None:  # type: ignore[no-untyped-def]
    worker = _worker(client, crew.a, make_candidate())
    planned = _assignment(
        client, crew.a, worker["id"], crew.client_id, start_date=START.isoformat()
    )
    refused = client.post(
        f"{P}/assignments/{planned['id']}/timesheets",
        json={"period_start": MONTH_START.isoformat(), "period_end": MONTH_END.isoformat()},
        headers=crew.a.headers,
    )
    assert refused.status_code == 422  # geplanter Einsatz: noch kein Stundenzettel

    assignment = _active_assignment(client, crew, make_candidate)
    base = {"period_start": MONTH_START.isoformat(), "period_end": MONTH_END.isoformat()}
    url = f"{P}/assignments/{assignment['id']}/timesheets"
    assert (
        client.post(
            url,
            json={**base, "period_end": (MONTH_START - timedelta(days=1)).isoformat()},
            headers=crew.a.headers,
        ).status_code
        == 422
    )
    assert (
        client.post(
            url,
            json={**base, "period_end": (MONTH_START + timedelta(days=70)).isoformat()},
            headers=crew.a.headers,
        ).status_code
        == 422
    )
    assert (
        client.post(
            url,
            json={
                "period_start": (START - timedelta(days=60)).isoformat(),
                "period_end": (START - timedelta(days=45)).isoformat(),
            },
            headers=crew.a.headers,
        ).status_code
        == 422
    )  # vor dem Einsatz
    sheet = _sheet(client, crew.a, assignment["id"])
    assert (
        client.post(url, json=base, headers=crew.a.headers).status_code == 409
    )  # gleicher Zeitraum
    overlap = {"period_start": (MONTH_END).isoformat(), "period_end": (TODAY).isoformat()}
    assert client.post(url, json=overlap, headers=crew.a.headers).status_code == 409

    entry = {"work_date": MONTH_START.isoformat(), "hours": "8", "break_minutes": 30}

    def put(body: dict) -> object:
        return client.put(
            f"{P}/timesheets/{sheet['id']}/entries", json=body, headers=crew.a.headers
        )

    assert put({"entries": [entry, entry]}).status_code == 422  # doppelter Tag
    assert (
        put(
            {"entries": [{**entry, "work_date": (MONTH_END + timedelta(days=1)).isoformat()}]}
        ).status_code
        == 422
    )  # ausserhalb
    assert put({"entries": [{**entry, "hours": "0"}]}).status_code == 422
    assert put({"entries": [{**entry, "hours": "24.5"}]}).status_code == 422
    assert put({"entries": [{**entry, "break_minutes": -1}]}).status_code == 422
    ok = put({"entries": [entry]})
    assert ok.status_code == 200 and ok.json()["total_hours"] == "8.00"
    assert put({"entries": []}).json()["total_hours"] == "0"  # ersetzt alles
    assert (
        client.post(f"{P}/timesheets/{sheet['id']}/submit", headers=crew.a.headers).status_code
        == 422
    )  # leer
    # Eingereichte Zettel sind nicht mehr aenderbar
    put({"entries": [entry]})
    assert (
        client.post(f"{P}/timesheets/{sheet['id']}/submit", headers=crew.a.headers).status_code
        == 200
    )
    assert put({"entries": [entry]}).status_code == 422
