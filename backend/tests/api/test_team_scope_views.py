"""Teamleiter-Scoping fuer Kalender, Team-KPIs und den Analytics-Nutzerfilter
(Entscheidungen 2026-10-03): Teamleiter sehen ihr Team, Admins alles,
Mitarbeiter nur sich. Setup wie in test_team_lead.py."""

from fastapi.testclient import TestClient

from tests.api.test_team_lead import Person, Team, _ids, team  # noqa: F401


def _event(client: TestClient, person: Person, title: str) -> str:
    response = client.post(
        "/api/v1/calendar-events",
        json={"title": title, "start_at": "2026-08-01T10:00:00"},
        headers=person.headers,
    )
    assert response.status_code == 201, response.text
    return str(response.json()["id"])


def _event_ids(client: TestClient, person: Person, query: str = "") -> set[str]:
    response = client.get(f"/api/v1/calendar-events{query}", headers=person.headers)
    assert response.status_code == 200, response.text
    # Nur die Termine dieses Tests (Titel "Scope-..."): die Prozess-Fixture legt
    # selbst Interview-Termine an.
    return {item["id"] for item in response.json() if item["title"].startswith("Scope-")}


def test_calendar_follows_team_scope(client: TestClient, team: Team) -> None:  # noqa: F811
    a = _event(client, team.a, "Scope-Anna")
    b = _event(client, team.b, "Scope-Bernd")
    c = _event(client, team.c, "Scope-Clara")

    assert _event_ids(client, team.a) == {a}
    assert _event_ids(client, team.b) == {a, b}
    assert _event_ids(client, team.c) == {c}
    assert _event_ids(client, team.admin) == {a, b, c}


def test_calendar_owner_filter_stays_inside_scope(client: TestClient, team: Team) -> None:  # noqa: F811
    a = _event(client, team.a, "Scope-Anna")
    b = _event(client, team.b, "Scope-Bernd")
    _event(client, team.c, "Scope-Clara")

    assert _event_ids(client, team.b, f"?owner_user_id={team.a.id}") == {a}
    assert _event_ids(client, team.b, f"?owner_user_id={team.b.id}") == {b}
    # Fremder Nutzer: Filter wird ignoriert, Scope bleibt (Team von B).
    assert _event_ids(client, team.b, f"?owner_user_id={team.c.id}") == {a, b}
    # Mitarbeiter A kann nicht auf B filtern.
    assert _event_ids(client, team.a, f"?owner_user_id={team.b.id}") == {a}


def _team_kpi_ids(client: TestClient, person: Person) -> set[str]:
    response = client.get("/api/v1/team-kpis?period=month", headers=person.headers)
    assert response.status_code == 200, response.text
    return {item["user_id"] for item in response.json()["members"]}


def test_team_kpis_scoped_for_team_lead(client: TestClient, team: Team) -> None:  # noqa: F811
    assert _team_kpi_ids(client, team.b) == {team.a.id, team.b.id}
    assert _team_kpi_ids(client, team.c) == {team.c.id}
    assert {team.a.id, team.b.id, team.c.id, team.admin.id} >= _team_kpi_ids(client, team.admin)
    assert {team.a.id, team.b.id, team.c.id} <= _team_kpi_ids(client, team.admin)


def test_team_kpis_forbidden_for_member(client: TestClient, team: Team) -> None:  # noqa: F811
    response = client.get("/api/v1/team-kpis", headers=team.a.headers)
    assert response.status_code == 403


def _cockpit_hot_ids(client: TestClient, person: Person, owners: list[str]) -> list[str]:
    query = "&".join(f"owner_user_id={uid}" for uid in owners)
    response = client.get(f"/api/v1/cockpit?{query}", headers=person.headers)
    assert response.status_code == 200, response.text
    body = response.json()
    return sorted(str(item["id"]) for item in body["important"] + body["hot_processes"])


def test_cockpit_owner_filter_is_clamped_to_scope(client: TestClient, team: Team) -> None:  # noqa: F811
    # Vorbedingung: Der Admin sieht fuer C etwas, sonst waere der Test wirkungslos.
    as_admin = client.get(f"/api/v1/cockpit?owner_user_id={team.c.id}", headers=team.admin.headers)
    assert as_admin.status_code == 200, as_admin.text
    admin_view = as_admin.json()
    assert (
        admin_view["kpis"]
        != client.get(
            "/api/v1/cockpit?owner_user_id=00000000-0000-0000-0000-000000000000",
            headers=team.admin.headers,
        ).json()["kpis"]
        or admin_view["recruiting_kpis"]
        != client.get(
            "/api/v1/cockpit?owner_user_id=00000000-0000-0000-0000-000000000000",
            headers=team.admin.headers,
        ).json()["recruiting_kpis"]
    )

    # B fragt nach C (nicht im Team): bekommt dasselbe wie "niemand".
    nobody = client.get(
        "/api/v1/cockpit?owner_user_id=00000000-0000-0000-0000-000000000000",
        headers=team.b.headers,
    ).json()
    foreign = client.get(
        f"/api/v1/cockpit?owner_user_id={team.c.id}", headers=team.b.headers
    ).json()
    assert foreign["kpis"] == nobody["kpis"]
    assert foreign["recruiting_kpis"] == nobody["recruiting_kpis"]
    assert foreign["important"] == nobody["important"] == []
