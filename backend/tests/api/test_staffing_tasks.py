"""Aufgaben der Ansicht Überlassung: Besitzbereich, kein Lohn/Marge, Ansicht erzwungen."""

from datetime import date, timedelta

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session, sessionmaker

from tests.api.test_staffing_api import (  # noqa: F401
    Crew,
    _assignment,
    _complete_checklist,
    _license,
    _worker,
    crew,
    make_candidate,
)

P = "/api/v1/staffing"
TODAY = date.today()


def _tasks(client: TestClient, who) -> dict:  # type: ignore[no-untyped-def]
    response = client.get(f"{P}/tasks", headers=who.headers)
    assert response.status_code == 200, response.text
    return response.json()


def test_tasks_cover_checklist_deadline_and_bench_and_follow_the_owner_scope(
    client: TestClient, crew: Crew, make_candidate  # noqa: F811
) -> None:  # type: ignore[no-untyped-def]
    _license(client, crew)
    worker = _worker(client, crew.admin, make_candidate("Anna"), hourly_wage="14.50")
    # Einsatz beginnt in 5 Tagen, Checkliste offen -> dringende Checklisten-Aufgabe
    assignment = _assignment(
        client,
        crew.a,
        worker["id"],
        crew.client_id,
        start_date=(TODAY + timedelta(days=5)).isoformat(),
    )
    own = _tasks(client, crew.a)
    kinds = {t["kind"] for t in own["tasks"]}
    assert "checklist_open" in kinds
    checklist = next(t for t in own["tasks"] if t["kind"] == "checklist_open")
    assert checklist["severity"] == "red" and checklist["assignment_id"] == assignment["id"]
    assert "Checkliste offen" in checklist["title"]
    assert own["alerts"] and "dringende" in own["alerts"][0]
    # Rote Aufgaben stehen vor gelben und Hinweisen
    order = {"red": 0, "yellow": 1, "info": 2}
    assert [order[t["severity"]] for t in own["tasks"]] == sorted(
        order[t["severity"]] for t in own["tasks"]
    )

    # Besitzbereich: Disponent C (anderes Team) sieht diesen Einsatz nicht
    other = _tasks(client, crew.c)
    assert all(t["assignment_id"] != assignment["id"] for t in other["tasks"])
    # Teamleiter B (Team von A) und Admin sehen ihn
    assert any(t["assignment_id"] == assignment["id"] for t in _tasks(client, crew.b)["tasks"])
    assert any(t["assignment_id"] == assignment["id"] for t in _tasks(client, crew.admin)["tasks"])

    # Keine Lohn-/Margenangaben, auch nicht für Admins
    for who in (crew.a, crew.admin):
        text = client.get(f"{P}/tasks", headers=who.headers).text
        for forbidden in ("wage", "billing", "margin", "14.50"):
            assert forbidden not in text, (who, forbidden)


def test_missing_license_and_overdue_timesheets_are_tasks(
    client: TestClient, crew: Crew, make_candidate  # noqa: F811
) -> None:  # type: ignore[no-untyped-def]
    tasks = _tasks(client, crew.admin)["tasks"]
    assert any(t["kind"] == "license" and t["severity"] == "red" for t in tasks)  # keine Erlaubnis

    _license(client, crew)
    worker = _worker(client, crew.a, make_candidate("Berta"))
    assignment = _assignment(client, crew.a, worker["id"], crew.client_id)
    _complete_checklist(client, crew.a, assignment["id"])
    activated = client.post(
        f"{P}/assignments/{assignment['id']}/status",
        json={"status": "active"},
        headers=crew.a.headers,
    )
    assert activated.status_code == 200, activated.text
    after = _tasks(client, crew.admin)["tasks"]
    assert not any(t["kind"] == "license" for t in after)  # Erlaubnis gültig
    # aktiv, aber für den Vormonat gibt es keinen Stundenzettel (Einsatz begann vor 10 Tagen)
    first_of_month = TODAY.replace(day=1)
    last_month_end = first_of_month - timedelta(days=1)
    started_before_last_month_end = (TODAY - timedelta(days=10)) <= last_month_end
    missing = [t for t in after if t["kind"] == "timesheet_missing"]
    assert bool(missing) == started_before_last_month_end


def test_tasks_route_needs_the_staffing_view(
    client: TestClient, crew: Crew, session_factory: sessionmaker[Session]  # noqa: F811
) -> None:
    # Nutzer ohne Ansicht Überlassung bekommt 403 und sieht nichts davon
    import uuid

    from cc_crm.models.access_views import UserViewAccess

    with session_factory() as session:
        for row in session.query(UserViewAccess).filter(
            UserViewAccess.user_id == uuid.UUID(crew.a.id)
        ):
            if row.view == "staffing":
                session.delete(row)
        session.commit()
    response = client.get(f"{P}/tasks", headers=crew.a.headers)
    assert response.status_code == 403
    assert "nicht freigeschaltet" in response.json()["detail"]
