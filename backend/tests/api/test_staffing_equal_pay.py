# NOMICON: Arbeitnehmerueberlassung - nur in der Nomicon-Kopie.
"""Equal Pay mit Folge in der API: Bestaetigen, Rechte, Anzeige, keine Lohnwerte in Texten."""

import json
import uuid
from datetime import timedelta

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from cc_crm.models.enums import TaskStatus
from cc_crm.models.recruiting import AuditLog
from cc_crm.models.task import Task
from cc_crm.services.staffing_deadline_job import run_deadline_job
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


def _reached(client: TestClient, crew: Crew, make_candidate, **worker_extra: object) -> dict:  # type: ignore[no-untyped-def]
    """Einsatz von Anna Disponentin, dessen Equal-Pay-Datum (9 Monate) schon vorbei ist."""
    worker = _worker(client, crew.admin, make_candidate(), **worker_extra)
    return _assignment(
        client,
        crew.admin,
        worker["id"],
        crew.client_id,
        owner_user_id=crew.a.id,
        start_date=(TODAY - timedelta(days=300)).isoformat(),
        billing_rate="28.00",
    )


def test_member_can_confirm_and_it_shows_everywhere(
    client: TestClient,
    crew: Crew,
    make_candidate,  # type: ignore[no-untyped-def]
    session_factory: sessionmaker[Session],
) -> None:
    assignment = _reached(client, crew, make_candidate, hourly_wage="14.50")
    url = f"{P}/assignments/{assignment['id']}"
    before = client.get(url, headers=crew.a.headers).json()
    assert before["deadline"]["equal_pay_reached"] is True
    assert before["deadline"]["equal_pay_open"] is True
    assert before["equal_pay_confirmed_on"] is None
    pair = client.get(f"{P}/deadlines", headers=crew.a.headers).json()[0]
    assert pair["equal_pay_open"] is True and pair["assignment_id"] == assignment["id"]
    tasks = client.get(f"{P}/tasks", headers=crew.a.headers).json()["tasks"]
    assert any(t["kind"] == "equal_pay" and t["title"].startswith("Equal Pay offen") for t in tasks)

    # Ein Mitarbeiter ohne Lohnrechte darf bestaetigen
    confirmed = client.post(f"{url}/equal-pay-confirmation", json={}, headers=crew.a.headers)
    assert confirmed.status_code == 200, confirmed.text
    body = confirmed.json()
    assert body["equal_pay_confirmed_on"] == TODAY.isoformat()
    assert body["deadline"]["equal_pay_open"] is False
    assert body["deadline"]["equal_pay_confirmed_on"] == TODAY.isoformat()
    assert body["hourly_wage"] is None and body["billing_rate"] is None  # Lohn bleibt Admin-only

    pair = client.get(f"{P}/deadlines", headers=crew.a.headers).json()[0]
    assert pair["equal_pay_open"] is False
    tasks = client.get(f"{P}/tasks", headers=crew.a.headers).json()["tasks"]
    assert not any(t["kind"] == "equal_pay" for t in tasks)

    with session_factory() as session:
        actions = session.scalars(
            select(AuditLog.action).where(AuditLog.entity_id == uuid.UUID(assignment["id"]))
        ).all()
    assert "equal_pay_confirmed" in actions

    cleared = client.delete(f"{url}/equal-pay-confirmation", headers=crew.a.headers)
    assert cleared.status_code == 200
    assert cleared.json()["equal_pay_confirmed_on"] is None
    assert cleared.json()["deadline"]["equal_pay_open"] is True


def test_confirmation_validation_and_rights(
    client: TestClient,
    crew: Crew,
    make_candidate,  # type: ignore[no-untyped-def]
) -> None:
    assignment = _reached(client, crew, make_candidate)
    url = f"{P}/assignments/{assignment['id']}/equal-pay-confirmation"
    future = client.post(
        url, json={"confirmed_on": (TODAY + timedelta(days=1)).isoformat()}, headers=crew.a.headers
    )
    assert future.status_code == 422
    before_start = client.post(
        url,
        json={"confirmed_on": (TODAY - timedelta(days=400)).isoformat()},
        headers=crew.a.headers,
    )
    assert before_start.status_code == 422
    # Fremde (anderer Teamleiter) sehen den Einsatz nicht: 404 wie ueberall
    assert client.post(url, json={}, headers=crew.c.headers).status_code == 404
    assert client.delete(url, headers=crew.c.headers).status_code == 404
    # Ein explizites Datum in der Vergangenheit ist erlaubt
    day = (TODAY - timedelta(days=2)).isoformat()
    ok = client.post(url, json={"confirmed_on": day}, headers=crew.a.headers)
    assert ok.status_code == 200 and ok.json()["equal_pay_confirmed_on"] == day


def test_task_texts_never_contain_wage_or_margin_values(
    client: TestClient,
    crew: Crew,
    make_candidate,  # type: ignore[no-untyped-def]
    session_factory: sessionmaker[Session],
) -> None:
    assignment = _reached(client, crew, make_candidate, hourly_wage="14.50")
    assert assignment["billing_rate"] == "28.00"  # Admin sieht den Satz
    with session_factory() as session:
        run_deadline_job(session, TODAY)
        texts = [
            f"{t.title} {t.description}"
            for t in session.scalars(select(Task).where(Task.title.startswith("Equal Pay")))
        ]
        statuses = [t.status for t in session.scalars(select(Task))]
    assert texts, "die Equal-Pay-Aufgabe muss entstanden sein"
    assert TaskStatus.OPEN in statuses
    for text in texts:
        for value in ("14.50", "14,50", "28.00", "28,00", "€", "EUR"):
            assert value not in text

    # Auch die Aufgabenliste der Ansicht (Admin UND Mitarbeiter) bleibt frei von Lohnwerten
    for headers in (crew.admin.headers, crew.a.headers):
        dump = json.dumps(client.get(f"{P}/tasks", headers=headers).json())
        for value in ("14.50", "28.00", "hourly_wage", "billing_rate"):
            assert value not in dump


def test_confirmation_before_the_cutoff_day_is_a_409(
    client: TestClient,
    crew: Crew,
    make_candidate,  # type: ignore[no-untyped-def]
) -> None:
    worker = _worker(client, crew.a, make_candidate())
    assignment = _assignment(client, crew.a, worker["id"], crew.client_id)  # Beginn heute - 10
    url = f"{P}/assignments/{assignment['id']}/equal-pay-confirmation"
    early = client.post(url, json={}, headers=crew.a.headers)
    assert early.status_code == 409
    assert "erst ab dem Stichtag" in early.json()["detail"]
