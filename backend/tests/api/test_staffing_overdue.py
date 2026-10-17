# NOMICON: Arbeitnehmerueberlassung - nur in der Nomicon-Kopie.
"""Ueberfaellige Einsaetze in API, Uebersicht und Aufgabenliste."""

from datetime import timedelta

from fastapi.testclient import TestClient

from tests.api.test_staffing_api import (
    TODAY,
    Crew,
    P,
    _assignment,
    _complete_checklist,
    _license,
    _worker,
    crew,
    make_candidate,
)

_ = (crew, make_candidate)  # Fixtures (per Import registriert)


def _active(client: TestClient, crew: Crew, make_candidate, **extra: object) -> dict:  # type: ignore[no-untyped-def]
    _license(client, crew)
    worker = _worker(client, crew.a, make_candidate())
    assignment = _assignment(client, crew.a, worker["id"], crew.client_id, **extra)
    _complete_checklist(client, crew.a, assignment["id"])
    response = client.post(
        f"{P}/assignments/{assignment['id']}/status",
        json={"status": "active"},
        headers=crew.a.headers,
    )
    assert response.status_code == 200, response.text
    return assignment


def test_overdue_flag_filter_overview_and_tasks(
    client: TestClient,
    crew: Crew,
    make_candidate,  # type: ignore[no-untyped-def]
) -> None:
    late = _active(client, crew, make_candidate)
    fine = _active(
        client, crew, make_candidate, planned_end_date=(TODAY + timedelta(days=30)).isoformat()
    )
    # Ende in der Vergangenheit setzen (Verkuerzung eines laufenden Einsatzes ist erlaubt)
    changed = client.patch(
        f"{P}/assignments/{late['id']}",
        json={"planned_end_date": (TODAY - timedelta(days=3)).isoformat()},
        headers=crew.a.headers,
    )
    assert changed.status_code == 200, changed.text

    everything = client.get(f"{P}/assignments", headers=crew.a.headers).json()
    flags = {a["id"]: a["is_overdue"] for a in everything}
    assert flags == {late["id"]: True, fine["id"]: False}

    only = client.get(f"{P}/assignments?overdue=true", headers=crew.a.headers).json()
    assert [a["id"] for a in only] == [late["id"]]

    overview = client.get(f"{P}/overview", headers=crew.a.headers).json()
    assert overview["overdue_assignments"] == 1

    tasks = client.get(f"{P}/tasks", headers=crew.a.headers).json()
    overdue = [t for t in tasks["tasks"] if t["kind"] == "assignment_overdue"]
    assert [t["assignment_id"] for t in overdue] == [late["id"]]
    assert overdue[0]["severity"] == "red"
    assert "beenden oder verlängern" in overdue[0]["detail"]
    assert any("überfällig" in alert for alert in tasks["alerts"])

    # Fremder sieht weder Einsatz noch Zaehlung
    stranger = client.get(f"{P}/overview", headers=crew.c.headers).json()
    assert stranger["overdue_assignments"] == 0
    assert client.get(f"{P}/assignments?overdue=true", headers=crew.c.headers).json() == []

    # Beenden raeumt die Warnung ab
    ended = client.post(
        f"{P}/assignments/{late['id']}/status",
        json={"status": "ended", "actual_end_date": (TODAY - timedelta(days=3)).isoformat()},
        headers=crew.a.headers,
    )
    assert ended.status_code == 200
    assert client.get(f"{P}/overview", headers=crew.a.headers).json()["overdue_assignments"] == 0
