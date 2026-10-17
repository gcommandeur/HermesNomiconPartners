# NOMICON: Arbeitnehmerueberlassung - nur in der Nomicon-Kopie.
"""Vorlaeufige Fristen in der API: Kennzeichen und Gruende, Ampelfarbe unveraendert."""

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


def test_provisional_flag_follows_planned_and_open_ended_assignments(
    client: TestClient,
    crew: Crew,
    make_candidate,  # type: ignore[no-untyped-def]
) -> None:
    _license(client, crew)
    worker = _worker(client, crew.a, make_candidate())
    assignment = _assignment(client, crew.a, worker["id"], crew.client_id)  # geplant, ohne Ende
    url = f"{P}/assignments/{assignment['id']}"

    planned = client.get(url, headers=crew.a.headers).json()["deadline"]
    assert planned["provisional"] is True
    assert planned["provisional_reasons"] == ["planned_assignment", "open_end"]
    traffic_before = planned["traffic"]

    # Enddatum erfasst, aber noch nicht aktiviert: nur noch der geplante Einsatz fehlt
    client.patch(
        url,
        json={"planned_end_date": (TODAY + timedelta(days=60)).isoformat()},
        headers=crew.a.headers,
    )
    assert client.get(url, headers=crew.a.headers).json()["deadline"]["provisional_reasons"] == [
        "planned_assignment"
    ]

    # Aktiviert und mit bekanntem Ende: endgueltig
    _complete_checklist(client, crew.a, assignment["id"])
    activated = client.post(f"{url}/status", json={"status": "active"}, headers=crew.a.headers)
    assert activated.status_code == 200, activated.text
    final = activated.json()["deadline"]
    assert final["provisional"] is False and final["provisional_reasons"] == []
    assert (
        final["traffic"] == traffic_before
    )  # die Ampelfarbe aendert sich nicht durch "vorlaeufig"

    # Fristenliste und Uebersicht tragen das Kennzeichen ebenfalls
    pair = client.get(f"{P}/deadlines", headers=crew.a.headers).json()[0]
    assert pair["provisional"] is False

    # Ende wieder entfernt: Einsatz ohne Enddatum -> vorlaeufig
    client.patch(url, json={"planned_end_date": None}, headers=crew.a.headers)
    pair = client.get(f"{P}/deadlines", headers=crew.a.headers).json()[0]
    assert pair["provisional"] is True and pair["provisional_reasons"] == ["open_end"]
