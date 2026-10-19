# NOMICON: Arbeitnehmerueberlassung - nur in der Nomicon-Kopie.
"""Ueberlassungsvertrag bei der Aktivierung: Pflicht, Deckung des Zeitraums, abgeleiteter
Checklistenpunkt und Aufgabe bei einer spaeteren Luecke."""

import uuid
from datetime import timedelta

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from cc_crm.models.client_company import ClientCompany
from cc_crm.models.task import Task
from tests.api.test_staffing_api import (
    TODAY,
    Crew,
    P,
    _assignment,
    _attach_contract,
    _complete_checklist,
    _license,
    _worker,
    crew,
    make_candidate,
)

_ = (crew, make_candidate)  # Fixtures (per Import registriert)


def _activate(client: TestClient, crew: Crew, assignment_id: str):  # type: ignore[no-untyped-def]
    return client.post(
        f"{P}/assignments/{assignment_id}/status",
        json={"status": "active"},
        headers=crew.a.headers,
    )


def _ready(client: TestClient, crew: Crew, make_candidate, **extra: object) -> dict:  # type: ignore[no-untyped-def]
    """Geplanter Einsatz mit gueltiger Erlaubnis, OHNE Vertrag."""
    _license(client, crew)
    worker = _worker(client, crew.a, make_candidate())
    return _assignment(client, crew.a, worker["id"], crew.client_id, **extra)


def _tick_everything_but_the_contract(client: TestClient, crew: Crew, assignment_id: str) -> None:
    detail = client.get(f"{P}/assignments/{assignment_id}", headers=crew.a.headers).json()
    for item in detail["checklist"]:
        if item["item_key"] != "supply_contract":
            response = client.patch(
                f"{P}/assignments/{assignment_id}/checklist/{item['id']}",
                json={"done": True},
                headers=crew.a.headers,
            )
            assert response.status_code == 200, response.text


def test_activation_needs_a_linked_contract(
    client: TestClient,
    crew: Crew,
    make_candidate,  # type: ignore[no-untyped-def]
) -> None:
    assignment = _ready(client, crew, make_candidate)
    _tick_everything_but_the_contract(client, crew, assignment["id"])
    blocked = _activate(client, crew, assignment["id"])
    assert blocked.status_code == 422
    assert "Kein Überlassungsvertrag" in blocked.json()["detail"]
    assert "Checkliste" not in blocked.json()["detail"]  # der Rest ist erledigt

    contract = _attach_contract(client, crew.a, assignment)
    done = _activate(client, crew, assignment["id"])
    assert done.status_code == 200, done.text
    body = done.json()
    assert body["status"] == "active"
    supply = next(i for i in body["checklist"] if i["item_key"] == "supply_contract")
    assert supply["done"] is True
    assert body["checklist_done"] == body["checklist_total"] == 6
    assert body["contract_id"] == contract["id"]


def test_contract_must_be_active_and_cover_the_period(
    client: TestClient,
    crew: Crew,
    make_candidate,  # type: ignore[no-untyped-def]
) -> None:
    assignment = _ready(
        client, crew, make_candidate, planned_end_date=(TODAY + timedelta(days=60)).isoformat()
    )
    _tick_everything_but_the_contract(client, crew, assignment["id"])

    # abgelaufen: nicht aktiv
    contract = _attach_contract(client, crew.a, assignment, status="expired")
    blocked = _activate(client, crew, assignment["id"])
    assert blocked.status_code == 422
    assert "nicht aktiv (Status: abgelaufen)" in blocked.json()["detail"]

    # aktiv, aber endet vor dem geplanten Einsatzende
    client.patch(
        f"{P}/contracts/{contract['id']}",
        json={"status": "active", "valid_to": (TODAY + timedelta(days=30)).isoformat()},
        headers=crew.a.headers,
    )
    short = _activate(client, crew, assignment["id"])
    assert short.status_code == 422
    assert "läuft am" in short.json()["detail"]

    # beginnt erst nach dem Einsatzbeginn
    client.patch(
        f"{P}/contracts/{contract['id']}",
        json={"valid_to": None, "valid_from": TODAY.isoformat()},
        headers=crew.a.headers,
    )
    late = _activate(client, crew, assignment["id"])
    assert late.status_code == 422
    assert "gilt erst ab" in late.json()["detail"]

    # deckt alles: aktiv, Beginn davor, offen nach hinten
    client.patch(
        f"{P}/contracts/{contract['id']}",
        json={"valid_from": (TODAY - timedelta(days=100)).isoformat()},
        headers=crew.a.headers,
    )
    assert _activate(client, crew, assignment["id"]).status_code == 200


def test_contract_of_another_client_is_rejected(
    client: TestClient,
    crew: Crew,
    make_candidate,  # type: ignore[no-untyped-def]
    session_factory: sessionmaker[Session],
) -> None:
    assignment = _ready(client, crew, make_candidate)
    with session_factory() as session:
        other = ClientCompany(name="Andere AG")
        session.add(other)
        session.commit()
        other_id = str(other.id)
    contract = client.post(
        f"{P}/contracts",
        json={
            "client_company_id": other_id,
            "valid_from": (TODAY - timedelta(days=50)).isoformat(),
            "status": "active",
        },
        headers=crew.a.headers,
    ).json()
    linked = client.patch(
        f"{P}/assignments/{assignment['id']}",
        json={"contract_id": contract["id"]},
        headers=crew.a.headers,
    )
    assert linked.status_code == 422
    assert "anderen Kunden" in linked.json()["detail"]


def test_supply_contract_item_cannot_be_ticked_by_hand(
    client: TestClient,
    crew: Crew,
    make_candidate,  # type: ignore[no-untyped-def]
) -> None:
    assignment = _ready(client, crew, make_candidate)
    detail = client.get(f"{P}/assignments/{assignment['id']}", headers=crew.a.headers).json()
    item = next(i for i in detail["checklist"] if i["item_key"] == "supply_contract")
    assert item["done"] is False
    for done in (True, False):
        response = client.patch(
            f"{P}/assignments/{assignment['id']}/checklist/{item['id']}",
            json={"done": done},
            headers=crew.a.headers,
        )
        assert response.status_code == 422
        assert "automatisch" in response.json()["detail"]
    assert "Überlassungsvertrag" in response.json()["detail"]

    # Verknuepfen hakt den Punkt ab, Loesen nimmt ihn wieder zurueck (live und in der Liste)
    _attach_contract(client, crew.a, assignment)
    linked = client.get(f"{P}/assignments/{assignment['id']}", headers=crew.a.headers).json()
    assert next(i for i in linked["checklist"] if i["item_key"] == "supply_contract")["done"]
    listed = client.get(f"{P}/assignments", headers=crew.a.headers).json()
    assert next(a for a in listed if a["id"] == assignment["id"])["checklist_done"] == 1
    client.patch(
        f"{P}/assignments/{assignment['id']}", json={"contract_id": None}, headers=crew.a.headers
    )
    unlinked = client.get(f"{P}/assignments/{assignment['id']}", headers=crew.a.headers).json()
    assert not next(i for i in unlinked["checklist"] if i["item_key"] == "supply_contract")["done"]


def _gap_tasks(session_factory: sessionmaker[Session]) -> list[Task]:
    with session_factory() as session:
        return list(
            session.scalars(
                select(Task).where(Task.title.startswith("Überlassungsvertrag deckt"))
            ).all()
        )


def test_contract_gap_on_an_active_assignment_creates_one_task(
    client: TestClient,
    crew: Crew,
    make_candidate,  # type: ignore[no-untyped-def]
    session_factory: sessionmaker[Session],
) -> None:
    assignment = _ready(client, crew, make_candidate)
    _complete_checklist(client, crew.a, assignment["id"])
    contract_id = client.get(f"{P}/assignments/{assignment['id']}", headers=crew.a.headers).json()[
        "contract_id"
    ]
    assert _activate(client, crew, assignment["id"]).status_code == 200
    assert _gap_tasks(session_factory) == []

    # Vertrag endet gestern: der aktive Einsatz ist nicht mehr gedeckt -> Aufgabe, KEINE Sperre
    changed = client.patch(
        f"{P}/contracts/{contract_id}",
        json={"valid_to": (TODAY - timedelta(days=1)).isoformat()},
        headers=crew.a.headers,
    )
    assert changed.status_code == 200
    tasks = _gap_tasks(session_factory)
    assert len(tasks) == 1
    assert tasks[0].owner_user_id == uuid.UUID(crew.a.id)
    text = f"{tasks[0].title} {tasks[0].description}"
    assert "läuft am" in text and "bleibt aktiv" in text
    assert "Mira" in text  # Name ja, Lohn/Marge nie
    assert "€" not in text and "14.50" not in text

    # Weitere Aenderung, die den schon vorher ungedeckten Einsatz nicht neu ausloest
    client.patch(
        f"{P}/assignments/{assignment['id']}", json={"location": "Halle 3"}, headers=crew.a.headers
    )
    client.patch(
        f"{P}/contracts/{contract_id}",
        json={"valid_to": (TODAY - timedelta(days=2)).isoformat()},
        headers=crew.a.headers,
    )
    assert len(_gap_tasks(session_factory)) == 1

    # Repariert und erneut gebrochen: neuer Zustand = neue Aufgabe
    client.patch(f"{P}/contracts/{contract_id}", json={"valid_to": None}, headers=crew.a.headers)
    client.patch(
        f"{P}/contracts/{contract_id}",
        json={"valid_to": (TODAY - timedelta(days=3)).isoformat()},
        headers=crew.a.headers,
    )
    assert len(_gap_tasks(session_factory)) == 2


def test_extending_the_assignment_beyond_the_contract_creates_a_task(
    client: TestClient,
    crew: Crew,
    make_candidate,  # type: ignore[no-untyped-def]
    session_factory: sessionmaker[Session],
) -> None:
    assignment = _ready(
        client, crew, make_candidate, planned_end_date=(TODAY + timedelta(days=20)).isoformat()
    )
    _attach_contract(client, crew.a, assignment, valid_to=(TODAY + timedelta(days=30)).isoformat())
    _complete_checklist(client, crew.a, assignment["id"])
    assert _activate(client, crew, assignment["id"]).status_code == 200

    extended = client.patch(
        f"{P}/assignments/{assignment['id']}",
        json={"planned_end_date": (TODAY + timedelta(days=90)).isoformat()},
        headers=crew.a.headers,
    )
    assert extended.status_code == 200  # nie blockierend
    assert len(_gap_tasks(session_factory)) == 1


def test_planned_assignments_get_no_gap_task(
    client: TestClient,
    crew: Crew,
    make_candidate,  # type: ignore[no-untyped-def]
    session_factory: sessionmaker[Session],
) -> None:
    assignment = _ready(client, crew, make_candidate)
    contract = _attach_contract(client, crew.a, assignment)
    client.patch(
        f"{P}/contracts/{contract['id']}",
        json={"valid_to": (TODAY - timedelta(days=1)).isoformat()},
        headers=crew.a.headers,
    )
    assert _gap_tasks(session_factory) == []
