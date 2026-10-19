# NOMICON: Arbeitnehmerueberlassung - nur in der Nomicon-Kopie.
"""Vorzeiten beim Kunden: API, Rechte, Protokoll und Wirkung auf die Frist."""

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

_ = (crew, make_candidate)  # Fixtures (per Import registriert)


def _period(client: TestClient, crew: Crew, worker_id: str, **extra: object):  # type: ignore[no-untyped-def]
    payload = {
        "client_company_id": crew.client_id,
        "start_date": (TODAY - timedelta(days=300)).isoformat(),
        "end_date": (TODAY - timedelta(days=60)).isoformat(),
        **extra,
    }
    return client.post(
        f"{P}/workers/{worker_id}/prior-periods", json=payload, headers=crew.a.headers
    )


def test_prior_period_crud_with_audit(
    client: TestClient,
    crew: Crew,
    make_candidate,  # type: ignore[no-untyped-def]
    session_factory: sessionmaker[Session],
) -> None:
    worker = _worker(client, crew.a, make_candidate())
    created = _period(client, crew, worker["id"], source="before_crm", note="Altbestand")
    assert created.status_code == 201, created.text
    body = created.json()
    assert body["client_name"] == "Beispiel Logistik GmbH"
    assert body["source"] == "before_crm"
    assert body["created_by_user_id"] == crew.a.id

    listed = client.get(f"{P}/workers/{worker['id']}/prior-periods", headers=crew.b.headers)
    assert [item["id"] for item in listed.json()] == [body["id"]]  # gemeinsamer Pool

    changed = client.patch(
        f"{P}/prior-periods/{body['id']}",
        json={"end_date": (TODAY - timedelta(days=90)).isoformat(), "note": None},
        headers=crew.a.headers,
    )
    assert changed.status_code == 200, changed.text
    assert changed.json()["end_date"] == (TODAY - timedelta(days=90)).isoformat()
    assert changed.json()["note"] is None

    deleted = client.delete(f"{P}/prior-periods/{body['id']}", headers=crew.a.headers)
    assert deleted.status_code == 204
    assert (
        client.get(f"{P}/workers/{worker['id']}/prior-periods", headers=crew.a.headers).json() == []
    )

    with session_factory() as session:
        actions = session.scalars(
            select(AuditLog.action).where(AuditLog.entity_type == "staffing_prior_period")
        ).all()
    assert sorted(actions) == ["created", "deleted", "updated"]


def test_prior_period_validation(
    client: TestClient,
    crew: Crew,
    make_candidate,  # type: ignore[no-untyped-def]
) -> None:
    worker = _worker(client, crew.a, make_candidate())
    backwards = _period(
        client,
        crew,
        worker["id"],
        start_date=TODAY.isoformat(),
        end_date=(TODAY - timedelta(days=5)).isoformat(),
    )
    assert backwards.status_code == 422
    future = _period(client, crew, worker["id"], end_date=(TODAY + timedelta(days=5)).isoformat())
    assert future.status_code == 422
    assert "abgeschlossen" in future.json()["detail"]
    unknown_client = _period(client, crew, worker["id"], client_company_id=str(uuid.uuid4()))
    assert unknown_client.status_code == 404
    assert _period(client, crew, str(uuid.uuid4())).status_code == 404  # unbekannte Person
    missing = client.patch(f"{P}/prior-periods/{uuid.uuid4()}", json={}, headers=crew.a.headers)
    assert missing.status_code == 404
    assert (
        client.delete(f"{P}/prior-periods/{uuid.uuid4()}", headers=crew.a.headers).status_code
        == 404
    )


def test_prior_period_extends_the_deadline_chain(
    client: TestClient,
    crew: Crew,
    make_candidate,  # type: ignore[no-untyped-def]
) -> None:
    worker = _worker(client, crew.a, make_candidate())
    assignment = _assignment(client, crew.a, worker["id"], crew.client_id)  # Beginn: heute - 10
    before = client.get(f"{P}/assignments/{assignment['id']}", headers=crew.a.headers).json()
    assert before["deadline"]["prior_days"] == 0
    assert before["deadline"]["counted_days"] == 11

    assert _period(client, crew, worker["id"]).status_code == 201  # heute-300 bis heute-60
    after = client.get(f"{P}/assignments/{assignment['id']}", headers=crew.a.headers).json()
    assert after["deadline"]["prior_days"] == 241
    assert after["deadline"]["counted_days"] == 241 + 11
    assert after["deadline"]["chain_start"] == (TODAY - timedelta(days=300)).isoformat()
    # und in der Fristenliste samt Equal-Pay-Datum, das dadurch nach vorn rückt
    deadlines = client.get(f"{P}/deadlines", headers=crew.a.headers).json()
    assert deadlines[0]["prior_days"] == 241


def test_prior_period_routes_need_a_login(client: TestClient) -> None:
    client.cookies.clear()
    ghost = uuid.uuid4()
    assert client.get(f"{P}/workers/{ghost}/prior-periods").status_code in (401, 403)
    assert client.delete(f"{P}/prior-periods/{ghost}").status_code in (401, 403)
