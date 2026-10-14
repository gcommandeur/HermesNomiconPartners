# NOMICON: Arbeitnehmerueberlassung - nur in der Nomicon-Kopie.
"""API der Ueberlassung: Ablauf, Aktivierungsregeln, Sichtbarkeit von Lohn/Marge, Owner-Scope."""

from dataclasses import dataclass
from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session, sessionmaker

from cc_crm.models.candidate import Candidate
from cc_crm.models.client_company import ClientCompany
from tests.api.test_team_lead import Person, _make_user

P = "/api/v1/staffing"
TODAY = date.today()


@dataclass
class Crew:
    admin: Person
    a: Person  # Mitarbeiter, Team von B
    b: Person  # Teamleiter
    c: Person  # anderer Teamleiter
    client_id: str


@pytest.fixture
def crew(client: TestClient, session_factory: sessionmaker[Session]) -> Crew:
    admin = _make_user(session_factory, "gf@nomicon.example", "admin", "Gerda GF")
    a = _make_user(session_factory, "a@nomicon.example", "member", "Anna Disponentin")
    b = _make_user(session_factory, "b@nomicon.example", "team_lead", "Bernd Teamleiter")
    c = _make_user(session_factory, "c@nomicon.example", "team_lead", "Clara Teamleiterin")
    response = client.patch(
        f"/api/v1/users/{a.id}", json={"manager_id": b.id}, headers=admin.headers
    )
    assert response.status_code == 200, response.text
    with session_factory() as session:
        company = ClientCompany(name="Beispiel Logistik GmbH")
        session.add(company)
        session.commit()
        client_id = str(company.id)
    return Crew(admin=admin, a=a, b=b, c=c, client_id=client_id)


@pytest.fixture
def make_candidate(session_factory: sessionmaker[Session]):  # type: ignore[no-untyped-def]
    def factory(first: str = "Mira") -> str:
        with session_factory() as session:
            candidate = Candidate(first_name=first, last_name="Muster")
            session.add(candidate)
            session.commit()
            return str(candidate.id)

    return factory


def _license(client: TestClient, crew: Crew) -> None:
    response = client.post(
        f"{P}/licenses",
        json={
            "authority": "Bundesagentur fuer Arbeit",
            "valid_from": (TODAY - timedelta(days=200)).isoformat(),
            "valid_to": (TODAY + timedelta(days=400)).isoformat(),
        },
        headers=crew.admin.headers,
    )
    assert response.status_code == 201, response.text


def _worker(client: TestClient, who: Person, candidate_id: str, **extra: object) -> dict:
    response = client.post(
        f"{P}/workers", json={"candidate_id": candidate_id, **extra}, headers=who.headers
    )
    assert response.status_code == 201, response.text
    return response.json()


def _assignment(client: TestClient, who: Person, worker_id: str, client_id: str, **extra) -> dict:  # type: ignore[no-untyped-def]
    response = client.post(
        f"{P}/assignments?confirm_engagement=true",  # Test-Setup: mehrere Einsaetze je Person
        json={
            "worker_id": worker_id,
            "client_company_id": client_id,
            "start_date": (TODAY - timedelta(days=10)).isoformat(),
            **extra,
        },
        headers=who.headers,
    )
    assert response.status_code == 201, response.text
    return response.json()


def _complete_checklist(client: TestClient, who: Person, assignment_id: str) -> None:
    detail = client.get(f"{P}/assignments/{assignment_id}", headers=who.headers).json()
    for item in detail["checklist"]:
        response = client.patch(
            f"{P}/assignments/{assignment_id}/checklist/{item['id']}",
            json={"done": True},
            headers=who.headers,
        )
        assert response.status_code == 200, response.text


# --- Ablauf und Aktivierungsregel -------------------------------------------------------------


def test_full_flow_and_activation_rules(client: TestClient, crew: Crew, make_candidate) -> None:  # type: ignore[no-untyped-def]
    worker = _worker(client, crew.a, make_candidate())
    assignment = _assignment(client, crew.a, worker["id"], crew.client_id)
    assert assignment["owner_user_id"] == crew.a.id
    assert assignment["status"] == "planned"
    assert assignment["checklist_total"] == 6

    # Weder Erlaubnis noch Checkliste: klare Meldung mit BEIDEN Problemen
    blocked = client.post(
        f"{P}/assignments/{assignment['id']}/status",
        json={"status": "active"},
        headers=crew.a.headers,
    )
    assert blocked.status_code == 422
    detail = blocked.json()["detail"]
    assert "nicht aktiviert werden" in detail
    assert "Keine gueltige AÜG-Erlaubnis" in detail
    assert "Pflicht-Checkliste unvollstaendig" in detail
    assert "Merkblatt" in detail

    shown = client.get(f"{P}/assignments/{assignment['id']}", headers=crew.a.headers).json()
    assert len(shown["activation_problems"]) == 2

    _license(client, crew)
    still_blocked = client.post(
        f"{P}/assignments/{assignment['id']}/status",
        json={"status": "active"},
        headers=crew.a.headers,
    )
    assert still_blocked.status_code == 422
    assert "Erlaubnis" not in still_blocked.json()["detail"]
    assert "Checkliste" in still_blocked.json()["detail"]

    _complete_checklist(client, crew.a, assignment["id"])
    activated = client.post(
        f"{P}/assignments/{assignment['id']}/status",
        json={"status": "active"},
        headers=crew.a.headers,
    )
    assert activated.status_code == 200, activated.text
    body = activated.json()
    assert body["status"] == "active"
    assert body["activation_problems"] == []
    assert body["deadline"]["has_chain"] is True
    assert body["deadline"]["counted_days"] == 11
    # Anwaerter wurde mit der ersten Aktivierung zum aktiven Leiharbeitnehmer
    assert (
        client.get(f"{P}/workers/{worker['id']}", headers=crew.a.headers).json()["status"]
        == "active"
    )

    ended = client.post(
        f"{P}/assignments/{assignment['id']}/status",
        json={"status": "ended"},
        headers=crew.a.headers,
    )
    assert ended.status_code == 200
    assert ended.json()["actual_end_date"] == TODAY.isoformat()
    # Beendet ist endgueltig
    again = client.post(
        f"{P}/assignments/{assignment['id']}/status",
        json={"status": "active"},
        headers=crew.a.headers,
    )
    assert again.status_code == 422
    edit = client.patch(
        f"{P}/assignments/{assignment['id']}", json={"location": "Halle 3"}, headers=crew.a.headers
    )
    assert edit.status_code == 422


def test_license_must_cover_the_planned_period(
    client: TestClient, crew: Crew, make_candidate
) -> None:  # type: ignore[no-untyped-def]
    _license(client, crew)  # gueltig bis heute + 400 Tage
    worker = _worker(client, crew.a, make_candidate())
    too_long = _assignment(
        client,
        crew.a,
        worker["id"],
        crew.client_id,
        planned_end_date=(TODAY + timedelta(days=500)).isoformat(),
    )
    _complete_checklist(client, crew.a, too_long["id"])
    response = client.post(
        f"{P}/assignments/{too_long['id']}/status",
        json={"status": "active"},
        headers=crew.a.headers,
    )
    assert response.status_code == 422
    assert "Erlaubnis" in response.json()["detail"]


# --- Lohn und Marge nur fuer Admins -----------------------------------------------------------


def test_wage_and_billing_rate_are_admin_only(
    client: TestClient, crew: Crew, make_candidate
) -> None:  # type: ignore[no-untyped-def]
    # Nicht-Admin darf Lohn weder setzen (403) noch loeschen
    forbidden = client.post(
        f"{P}/workers",
        json={"candidate_id": make_candidate("Zora"), "hourly_wage": "14.50"},
        headers=crew.a.headers,
    )
    assert forbidden.status_code == 403

    worker = _worker(client, crew.admin, make_candidate(), hourly_wage="14.50")
    assert worker["hourly_wage"] == "14.50"
    assignment = _assignment(
        client,
        crew.admin,
        worker["id"],
        crew.client_id,
        owner_user_id=crew.a.id,
        billing_rate="28.00",
    )
    assert assignment["billing_rate"] == "28.00"
    assert assignment["hourly_wage"] == "14.50"  # aus dem Arbeitnehmer uebernommen

    for headers in (crew.a.headers, crew.b.headers):  # Mitarbeiter UND Teamleiter
        shown_worker = client.get(f"{P}/workers/{worker['id']}", headers=headers).json()
        assert shown_worker["hourly_wage"] is None
        assert all(
            w["hourly_wage"] is None for w in client.get(f"{P}/workers", headers=headers).json()
        )
        by_candidate = client.get(
            f"{P}/workers/by-candidate/{worker['candidate_id']}", headers=headers
        ).json()
        assert by_candidate["hourly_wage"] is None
        for url in (f"{P}/assignments/{assignment['id']}", f"{P}/assignments"):
            data = client.get(url, headers=headers).json()
            rows = data if isinstance(data, list) else [data]
            assert rows, url
            for row in rows:
                assert row["billing_rate"] is None
                assert row["hourly_wage"] is None
    for payload in ({"billing_rate": "30.00"}, {"hourly_wage": None}):
        response = client.patch(
            f"{P}/assignments/{assignment['id']}", json=payload, headers=crew.a.headers
        )
        assert response.status_code == 403, payload
    response = client.patch(
        f"{P}/workers/{worker['id']}", json={"hourly_wage": "99"}, headers=crew.a.headers
    )
    assert response.status_code == 403
    # Admin sieht und aendert weiterhin
    assert (
        client.patch(
            f"{P}/assignments/{assignment['id']}",
            json={"billing_rate": "30.00"},
            headers=crew.admin.headers,
        ).json()["billing_rate"]
        == "30.00"
    )


def test_wage_never_reaches_non_admins_through_logs(
    client: TestClient, crew: Crew, make_candidate
) -> None:  # type: ignore[no-untyped-def]
    candidate_id = make_candidate()
    worker = _worker(client, crew.admin, candidate_id, hourly_wage="14.50")
    client.patch(
        f"{P}/workers/{worker['id']}", json={"hourly_wage": "15.75"}, headers=crew.admin.headers
    )
    # Globales Audit-Log: nur Admin (403), enthaelt den Lohn
    assert client.get("/api/v1/audit-logs", headers=crew.a.headers).status_code == 403
    admin_log = client.get("/api/v1/audit-logs", headers=crew.admin.headers).text
    assert "15.75" in admin_log
    # Kandidaten-Historie (fuer alle lesbar): keine Ueberlassungs-Eintraege
    for who in (crew.a, crew.b, crew.admin):
        history = client.get(f"/api/v1/candidates/{candidate_id}/history", headers=who.headers)
        assert history.status_code == 200
        assert "15.75" not in history.text and "staffing" not in history.text


# --- Owner-Scope -------------------------------------------------------------------------------


def test_assignment_visibility_follows_the_owner_scope(
    client: TestClient, crew: Crew, make_candidate
) -> None:  # type: ignore[no-untyped-def]
    worker = _worker(client, crew.a, make_candidate())
    mine = _assignment(client, crew.a, worker["id"], crew.client_id)  # Owner A
    others = _assignment(client, crew.c, worker["id"], crew.client_id)  # Owner C
    orphan = _assignment(client, crew.admin, worker["id"], crew.client_id, owner_user_id=None)
    # Admin ohne Angabe wird selbst Owner; echter Waisenfall ueber Owner-Wechsel nicht moeglich
    ids = lambda who: {r["id"] for r in client.get(f"{P}/assignments", headers=who.headers).json()}  # noqa: E731
    assert ids(crew.a) == {mine["id"]}
    assert ids(crew.b) == {mine["id"]}  # Teamleiter: eigene + Team (A) - nicht C
    assert ids(crew.c) == {others["id"]}
    assert ids(crew.admin) == {mine["id"], others["id"], orphan["id"]}
    for who, url_id, expected in (
        (crew.a, others["id"], 404),
        (crew.b, others["id"], 404),
        (crew.c, mine["id"], 404),
        (crew.b, mine["id"], 200),
        (crew.admin, others["id"], 200),
    ):
        assert client.get(f"{P}/assignments/{url_id}", headers=who.headers).status_code == expected
    # nicht existent = dasselbe 404 wie fremd
    import uuid

    assert client.get(f"{P}/assignments/{uuid.uuid4()}", headers=crew.a.headers).status_code == 404
    # Zuweisung an einen Disponenten ausserhalb des eigenen Bereichs ist nicht erlaubt
    response = client.post(
        f"{P}/assignments",
        json={
            "worker_id": worker["id"],
            "client_company_id": crew.client_id,
            "start_date": TODAY.isoformat(),
            "owner_user_id": crew.c.id,
        },
        headers=crew.a.headers,
    )
    assert response.status_code == 403


def test_overview_and_deadlines_are_scoped_and_ordered(
    client: TestClient, crew: Crew, make_candidate
) -> None:  # type: ignore[no-untyped-def]
    w1 = _worker(client, crew.admin, make_candidate("Eins"))
    w2 = _worker(client, crew.admin, make_candidate("Zwei"))
    # Eins: seit 17 Monaten -> rot/gelb; Zwei: frisch
    old = _assignment(
        client,
        crew.a,
        w1["id"],
        crew.client_id,
        start_date=(TODAY - timedelta(days=500)).isoformat(),
    )
    _assignment(client, crew.a, w2["id"], crew.client_id)
    foreign = _worker(client, crew.admin, make_candidate("Drei"))
    _assignment(client, crew.c, foreign["id"], crew.client_id)

    deadlines = client.get(f"{P}/deadlines", headers=crew.a.headers).json()
    assert [d["worker_name"] for d in deadlines] == ["Eins Muster", "Zwei Muster"]
    assert deadlines[0]["traffic"] in ("yellow", "red")
    assert deadlines[1]["traffic"] == "green"
    assert deadlines[0]["days_remaining"] < deadlines[1]["days_remaining"]
    assert len(client.get(f"{P}/deadlines", headers=crew.admin.headers).json()) == 3

    overview = client.get(f"{P}/overview", headers=crew.a.headers).json()
    assert overview["planned_assignments"] == 2
    assert overview["open_checklist_assignments"] == 2
    assert overview["license"]["valid"] is False
    assert overview["license"]["traffic"] == "red"
    assert len(overview["deadlines"]) == 2
    detail = client.get(f"{P}/assignments/{old['id']}", headers=crew.a.headers).json()
    assert detail["deadline"]["chain_start"] == (TODAY - timedelta(days=500)).isoformat()


# --- Einstellungen und Erlaubnis nur Admin -----------------------------------------------------


def test_settings_and_licenses_are_admin_writes(client: TestClient, crew: Crew) -> None:
    current = client.get(f"{P}/settings", headers=crew.a.headers).json()
    assert (current["max_months"], current["equal_pay_months"], current["reset_gap_months"]) == (
        18,
        9,
        3,
    )
    assert "kein Rechtsrat" in current["notice"]
    body = {k: v for k, v in current.items() if k != "notice"}
    assert client.put(f"{P}/settings", json=body, headers=crew.a.headers).status_code == 403
    assert (
        client.put(
            f"{P}/settings", json={**body, "max_months": 24}, headers=crew.admin.headers
        ).json()["max_months"]
        == 24
    )
    bad = client.put(
        f"{P}/settings", json={**body, "equal_pay_months": 30}, headers=crew.admin.headers
    )
    assert bad.status_code == 422  # Equal Pay muss vor der Hoechstdauer liegen
    licence = {"authority": "BA", "valid_from": "2026-01-01"}
    assert client.post(f"{P}/licenses", json=licence, headers=crew.a.headers).status_code == 403
    created = client.post(f"{P}/licenses", json=licence, headers=crew.admin.headers)
    assert created.status_code == 201
    assert len(client.get(f"{P}/licenses", headers=crew.a.headers).json()) == 1
    assert (
        client.patch(
            f"{P}/licenses/{created.json()['id']}", json={"notes": "x"}, headers=crew.a.headers
        ).status_code
        == 403
    )


def test_duplicate_worker_and_unknown_candidate(
    client: TestClient, crew: Crew, make_candidate
) -> None:  # type: ignore[no-untyped-def]
    candidate_id = make_candidate()
    _worker(client, crew.a, candidate_id)
    assert (
        client.post(
            f"{P}/workers", json={"candidate_id": candidate_id}, headers=crew.a.headers
        ).status_code
        == 409
    )
    import uuid

    assert (
        client.post(
            f"{P}/workers", json={"candidate_id": str(uuid.uuid4())}, headers=crew.a.headers
        ).status_code
        == 404
    )
    assert (
        client.get(f"{P}/workers/by-candidate/{uuid.uuid4()}", headers=crew.a.headers).status_code
        == 404
    )


def test_requires_login(client: TestClient) -> None:
    anonymous = TestClient(client.app)
    for path in ("/workers", "/assignments", "/overview", "/deadlines", "/settings", "/licenses"):
        assert anonymous.get(f"{P}{path}").status_code == 401, path
