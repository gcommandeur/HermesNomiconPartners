# NOMICON: Arbeitnehmerueberlassung - nur in der Nomicon-Kopie.
"""Bestaetigung "Keine Vorzeiten": API, Rechte, Protokoll und Wirkung auf "vorlaeufig"."""

import uuid
from datetime import timedelta

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from cc_crm.models.recruiting import AuditLog
from tests.api.test_staffing_api import (
    TODAY,
    Crew,
    P,
    _assignment,
    _worker,
    crew,
    make_candidate,
)
from tests.api.test_staffing_prior_periods import _period

_ = (crew, make_candidate)  # Fixtures (per Import registriert)


def _confirm(client: TestClient, crew: Crew, worker_id: str, **extra: object):  # type: ignore[no-untyped-def]
    return client.post(
        f"{P}/workers/{worker_id}/prior-period-confirmations",
        json={"client_company_id": crew.client_id, **extra},
        headers=crew.a.headers,
    )


def _deadline(client: TestClient, crew: Crew, assignment_id: str) -> dict:  # type: ignore[type-arg]
    response = client.get(f"{P}/assignments/{assignment_id}", headers=crew.a.headers)
    return response.json()["deadline"]


def test_deadline_is_provisional_until_no_prior_periods_are_confirmed(
    client: TestClient,
    crew: Crew,
    make_candidate,  # type: ignore[no-untyped-def]
) -> None:
    worker = _worker(client, crew.a, make_candidate())
    assignment = _assignment(
        client,
        crew.a,
        worker["id"],
        crew.client_id,
        planned_end_date=(TODAY + timedelta(days=100)).isoformat(),
    )
    before = _deadline(client, crew, assignment["id"])
    assert before["provisional"] is True
    assert "prior_unconfirmed" in before["provisional_reasons"]

    created = _confirm(client, crew, worker["id"], note="Arbeitgeber befragt")
    assert created.status_code == 201, created.text
    body = created.json()
    assert body["confirmed_on"] == TODAY.isoformat()
    assert body["confirmed_by_user_id"] == crew.a.id
    assert body["confirmed_by_name"] == "Anna Disponentin"

    after = _deadline(client, crew, assignment["id"])
    assert "prior_unconfirmed" not in after["provisional_reasons"]


def test_recorded_prior_periods_also_end_the_provisional_state(
    client: TestClient,
    crew: Crew,
    make_candidate,  # type: ignore[no-untyped-def]
) -> None:
    worker = _worker(client, crew.a, make_candidate())
    assignment = _assignment(client, crew.a, worker["id"], crew.client_id)
    assert "prior_unconfirmed" in _deadline(client, crew, assignment["id"])["provisional_reasons"]
    assert _period(client, crew, worker["id"]).status_code == 201
    assert (
        "prior_unconfirmed" not in _deadline(client, crew, assignment["id"])["provisional_reasons"]
    )
    # "Keine Vorzeiten" passt dann nicht mehr
    assert _confirm(client, crew, worker["id"]).status_code == 409


def test_withdraw_reopens_the_provisional_state_and_everything_is_protocolled(
    client: TestClient,
    crew: Crew,
    make_candidate,  # type: ignore[no-untyped-def]
    session_factory: sessionmaker[Session],
) -> None:
    worker = _worker(client, crew.a, make_candidate())
    assignment = _assignment(client, crew.a, worker["id"], crew.client_id)
    assert _confirm(client, crew, worker["id"]).status_code == 201
    again = _confirm(client, crew, worker["id"], note="geändert")  # Upsert, kein zweiter Eintrag
    assert again.status_code == 201
    listed = client.get(
        f"{P}/workers/{worker['id']}/prior-period-confirmations", headers=crew.b.headers
    )
    assert [item["note"] for item in listed.json()] == ["geändert"]  # gemeinsamer Pool

    gone = client.delete(
        f"{P}/workers/{worker['id']}/prior-period-confirmations/{crew.client_id}",
        headers=crew.a.headers,
    )
    assert gone.status_code == 204
    assert "prior_unconfirmed" in _deadline(client, crew, assignment["id"])["provisional_reasons"]
    missing = client.delete(
        f"{P}/workers/{worker['id']}/prior-period-confirmations/{crew.client_id}",
        headers=crew.a.headers,
    )
    assert missing.status_code == 404

    with session_factory() as session:
        actions = session.scalars(
            select(AuditLog.action)
            .where(AuditLog.entity_type == "staffing_prior_period_confirmation")
            .order_by(AuditLog.id)
        ).all()
    assert sorted(actions) == ["created", "deleted", "updated"]


def test_confirmation_validation_and_unknown_ids(
    client: TestClient,
    crew: Crew,
    make_candidate,  # type: ignore[no-untyped-def]
) -> None:
    worker = _worker(client, crew.a, make_candidate())
    future = (TODAY + timedelta(days=1)).isoformat()
    assert _confirm(client, crew, worker["id"], confirmed_on=future).status_code == 422
    ghost = str(uuid.uuid4())
    assert _confirm(client, crew, ghost).status_code == 404  # Person nicht vorhanden
    unknown_client = client.post(
        f"{P}/workers/{worker['id']}/prior-period-confirmations",
        json={"client_company_id": ghost},
        headers=crew.a.headers,
    )
    assert unknown_client.status_code == 404


def test_confirmation_routes_need_a_login(client: TestClient) -> None:
    client.cookies.clear()
    ghost = uuid.uuid4()
    assert client.get(f"{P}/workers/{ghost}/prior-period-confirmations").status_code in (401, 403)
    assert client.delete(f"{P}/workers/{ghost}/prior-period-confirmations/{ghost}").status_code in (
        401,
        403,
    )
