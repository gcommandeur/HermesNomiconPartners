# NOMICON: Arbeitnehmerueberlassung - nur in der Nomicon-Kopie.
"""Ueberschneidung desselben Leiharbeitnehmers: nur warnen (409), mit Bestaetigung speichern."""

import uuid
from datetime import timedelta

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from cc_crm.models.client_company import ClientCompany
from cc_crm.models.recruiting import AuditLog
from tests.api.test_staffing_api import (
    TODAY,
    Crew,
    P,
    _complete_checklist,
    _license,
    _worker,
    crew,
    make_candidate,
)

_ = (crew, make_candidate)  # Fixtures (per Import registriert)


def _day(offset: int) -> str:
    return (TODAY + timedelta(days=offset)).isoformat()


def _post(
    client: TestClient,
    crew: Crew,
    worker_id: str,
    client_id: str,
    start: int,
    end: int | None,
    **query: str,
):  # type: ignore[no-untyped-def]
    params = "&".join(["confirm_engagement=true", *(f"{k}={v}" for k, v in query.items())])
    body: dict[str, object] = {
        "worker_id": worker_id,
        "client_company_id": client_id,
        "start_date": _day(start),
    }
    if end is not None:
        body["planned_end_date"] = _day(end)
    return client.post(f"{P}/assignments?{params}", json=body, headers=crew.a.headers)


def _other_client(session_factory: sessionmaker[Session]) -> str:
    with session_factory() as session:
        company = ClientCompany(name="Zweite Logistik AG")
        session.add(company)
        session.commit()
        return str(company.id)


def test_overlap_is_a_409_with_the_overlapping_assignments(
    client: TestClient,
    crew: Crew,
    make_candidate,  # type: ignore[no-untyped-def]
) -> None:
    worker = _worker(client, crew.a, make_candidate())
    first = _post(client, crew, worker["id"], crew.client_id, -10, 20)
    assert first.status_code == 201, first.text

    clash = _post(client, crew, worker["id"], crew.client_id, 0, None)  # gleicher Kunde
    assert clash.status_code == 409
    body = clash.json()
    assert body["detail"].startswith("Überschneidung")
    assert "Beispiel Logistik GmbH" in body["detail"]
    assert len(body["overlaps"]) == 1
    item = body["overlaps"][0]
    assert item["assignment_id"] == first.json()["id"]
    assert item["client_name"] == "Beispiel Logistik GmbH"
    assert (item["start_date"], item["planned_end_date"], item["status"]) == (
        _day(-10),
        _day(20),
        "planned",
    )
    # weder Lohn noch Verrechnungssatz in Antwort oder Text
    assert not {"hourly_wage", "billing_rate"} & set(item)
    assert "€" not in body["detail"]
    # nichts wurde gespeichert
    listed = client.get(f"{P}/assignments", headers=crew.a.headers).json()
    assert len(listed) == 1


def test_overlap_is_found_across_clients_but_not_for_adjacent_days(
    client: TestClient,
    crew: Crew,
    make_candidate,  # type: ignore[no-untyped-def]
    session_factory: sessionmaker[Session],
) -> None:
    other_client = _other_client(session_factory)
    worker = _worker(client, crew.a, make_candidate())
    assert _post(client, crew, worker["id"], crew.client_id, -10, 20).status_code == 201

    across = _post(client, crew, worker["id"], other_client, 20, 40)  # genau der letzte Tag
    assert across.status_code == 409
    assert across.json()["overlaps"][0]["client_name"] == "Beispiel Logistik GmbH"

    adjacent = _post(client, crew, worker["id"], other_client, 21, 40)  # Folgetag: kein Treffer
    assert adjacent.status_code == 201, adjacent.text
    before = _post(client, crew, worker["id"], other_client, -50, -11)  # Vortag: kein Treffer
    assert before.status_code == 201, before.text


def test_confirmed_overlap_is_saved_and_protocolled(
    client: TestClient,
    crew: Crew,
    make_candidate,  # type: ignore[no-untyped-def]
    session_factory: sessionmaker[Session],
) -> None:
    worker = _worker(client, crew.a, make_candidate())
    first = _post(client, crew, worker["id"], crew.client_id, -10, 20).json()
    saved = _post(client, crew, worker["id"], crew.client_id, 0, 10, confirm_overlap="true")
    assert saved.status_code == 201, saved.text
    with session_factory() as session:
        entries = session.scalars(
            select(AuditLog).where(
                AuditLog.entity_id == uuid.UUID(saved.json()["id"]),
                AuditLog.action == "overlap_acknowledged",
            )
        ).all()
    assert len(entries) == 1
    assert entries[0].changed_by == "a@nomicon.example"  # Disponentin aus der Crew-Fixture
    assert first["id"] in str(entries[0].new_values)


def test_updating_dates_into_an_overlap_needs_confirmation(
    client: TestClient,
    crew: Crew,
    make_candidate,  # type: ignore[no-untyped-def]
    session_factory: sessionmaker[Session],
) -> None:
    worker = _worker(client, crew.a, make_candidate())
    _post(client, crew, worker["id"], crew.client_id, -10, 20)
    later = _post(client, crew, worker["id"], crew.client_id, 30, 60).json()
    url = f"{P}/assignments/{later['id']}"

    clash = client.patch(url, json={"start_date": _day(10)}, headers=crew.a.headers)
    assert clash.status_code == 409
    assert clash.json()["overlaps"]

    ok = client.patch(
        f"{url}?confirm_overlap=true", json={"start_date": _day(10)}, headers=crew.a.headers
    )
    assert ok.status_code == 200, ok.text
    # Eine spaetere Aenderung ohne Datumsaenderung fragt nicht erneut
    again = client.patch(url, json={"location": "Halle 3"}, headers=crew.a.headers)
    assert again.status_code == 200
    with session_factory() as session:
        actions = session.scalars(
            select(AuditLog.action).where(AuditLog.entity_id == uuid.UUID(later["id"]))
        ).all()
    assert "overlap_acknowledged" in actions


def test_aborted_and_ended_assignments_do_not_count(
    client: TestClient,
    crew: Crew,
    make_candidate,  # type: ignore[no-untyped-def]
) -> None:
    worker = _worker(client, crew.a, make_candidate())
    first = _post(client, crew, worker["id"], crew.client_id, -10, 20).json()
    client.post(
        f"{P}/assignments/{first['id']}/status", json={"status": "aborted"}, headers=crew.a.headers
    )
    assert _post(client, crew, worker["id"], crew.client_id, 0, 10).status_code == 201


def test_activation_shows_the_overlap_only_as_a_warning(
    client: TestClient,
    crew: Crew,
    make_candidate,  # type: ignore[no-untyped-def]
    session_factory: sessionmaker[Session],
) -> None:
    _license(client, crew)
    other_client = _other_client(session_factory)
    worker = _worker(client, crew.a, make_candidate())
    _post(client, crew, worker["id"], other_client, -10, 20)
    second = _post(
        client, crew, worker["id"], crew.client_id, -5, 15, confirm_overlap="true"
    ).json()
    _complete_checklist(client, crew.a, second["id"])

    detail = client.get(f"{P}/assignments/{second['id']}", headers=crew.a.headers).json()
    assert detail["activation_problems"] == []  # blockiert nicht
    assert len(detail["activation_warnings"]) == 1
    assert "Überschneidung" in detail["activation_warnings"][0]
    assert "Zweite Logistik AG" in detail["activation_warnings"][0]

    activated = client.post(
        f"{P}/assignments/{second['id']}/status", json={"status": "active"}, headers=crew.a.headers
    )
    assert activated.status_code == 200, activated.text


def test_foreign_assignments_stay_hidden_with_confirm_overlap(
    client: TestClient,
    crew: Crew,
    make_candidate,  # type: ignore[no-untyped-def]
) -> None:
    worker = _worker(client, crew.a, make_candidate())
    mine = _post(client, crew, worker["id"], crew.client_id, -10, 20).json()
    stranger = client.patch(
        f"{P}/assignments/{mine['id']}?confirm_overlap=true",
        json={"location": "x"},
        headers=crew.c.headers,
    )
    assert stranger.status_code == 404
