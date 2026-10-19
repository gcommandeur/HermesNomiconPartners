# NOMICON: Arbeitnehmerueberlassung - nur in der Nomicon-Kopie.
"""Equal Pay mit Folge: Aufgabe "Lohn pruefen und angleichen", Vorwarnung, Bestaetigung."""

from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy.orm import Session

from cc_crm.core.errors import BusinessRuleError, ConflictError
from cc_crm.models.enums import TaskStatus
from cc_crm.models.staffing import StaffingAssignmentStatus
from cc_crm.services.staffing_deadline_job import run_deadline_job
from cc_crm.services.staffing_equal_pay import StaffingEqualPayService
from tests.services.test_staffing_deadline_job import (
    _assignment,
    _client,
    _tasks,
    _user,
    _worker,
    session,
)

D = date
_ = session  # Fixture (per Import registriert)


def _equal_pay_tasks(session: Session):  # type: ignore[no-untyped-def]
    return [t for t in _tasks(session) if t.title.startswith("Equal Pay")]


def test_task_is_created_once_with_names_and_date_but_without_wages(session: Session) -> None:
    owner = _user(session, "dispo@x.example")
    worker, client = _worker(session), _client(session)  # Stundenlohn 14.50 am Arbeitnehmer
    assignment = _assignment(session, worker, client, D(2025, 1, 1), owner=owner)
    assignment.billing_rate = Decimal("29.00")
    assignment.hourly_wage = Decimal("14.50")
    session.commit()

    run_deadline_job(session, D(2025, 10, 1))  # Equal Pay gilt ab 1.10.2025
    tasks = _equal_pay_tasks(session)
    assert len(tasks) == 1
    task = tasks[0]
    assert task.owner_user_id == owner.id
    assert task.title == (
        "Equal Pay gilt ab 01.10.2025: Lohn von Mira Muster bei Logistik GmbH prüfen und angleichen"
    )
    assert task.priority.value == "high"
    text = f"{task.title} {task.description}"
    for forbidden in ("14.50", "14,50", "29.00", "29,00", "€", "EUR"):
        assert forbidden not in text
    assert "kein Rechtsrat" in text

    run_deadline_job(session, D(2025, 10, 2))
    run_deadline_job(session, D(2025, 12, 1))
    assert len(_equal_pay_tasks(session)) == 1  # einmalig je Paar


def test_confirmation_completes_the_task_and_nothing_new_comes(session: Session) -> None:
    owner = _user(session, "dispo@x.example")
    worker, client = _worker(session), _client(session)
    assignment = _assignment(session, worker, client, D(2025, 1, 1), owner=owner)
    run_deadline_job(session, D(2025, 10, 1))
    assert [t.status for t in _equal_pay_tasks(session)] == [TaskStatus.OPEN]

    StaffingEqualPayService(session).confirm(assignment.id, owner, today=D(2025, 10, 5))
    session.refresh(assignment)
    assert assignment.equal_pay_confirmed_on == D(2025, 10, 5)
    assert assignment.equal_pay_confirmed_by_user_id == owner.id
    assert [t.status for t in _equal_pay_tasks(session)] == [TaskStatus.DONE]

    run_deadline_job(session, D(2025, 11, 1))
    assert len(_equal_pay_tasks(session)) == 1  # keine zweite Aufgabe
    assert [t.status for t in _equal_pay_tasks(session)] == [TaskStatus.DONE]


def test_no_task_when_already_confirmed(session: Session) -> None:
    owner = _user(session, "dispo@x.example")
    worker, client = _worker(session), _client(session)
    assignment = _assignment(session, worker, client, D(2025, 1, 1), owner=owner)
    StaffingEqualPayService(session).confirm(assignment.id, owner, today=D(2025, 10, 1))
    run_deadline_job(session, D(2025, 10, 15))
    assert _equal_pay_tasks(session) == []


def test_prewarning_30_days_before_and_none_earlier(session: Session) -> None:
    owner = _user(session, "dispo@x.example")
    worker, client = _worker(session), _client(session)
    _assignment(session, worker, client, D(2025, 1, 1), owner=owner)  # Equal Pay ab 1.10.2025
    run_deadline_job(session, D(2025, 8, 31))  # 31 Tage vorher: noch nichts
    assert _equal_pay_tasks(session) == []
    run_deadline_job(session, D(2025, 9, 1))  # 30 Tage vorher: Vorwarnung
    soon = _equal_pay_tasks(session)
    assert len(soon) == 1
    assert soon[0].title.startswith("Equal Pay beginnt am 01.10.2025")
    assert soon[0].priority.value == "normal"
    run_deadline_job(session, D(2025, 9, 20))
    assert len(_equal_pay_tasks(session)) == 1  # Vorwarnung einmalig
    run_deadline_job(session, D(2025, 10, 1))  # jetzt gilt es: zusaetzlich die eigentliche Aufgabe
    titles = [t.title for t in _equal_pay_tasks(session)]
    assert len(titles) == 2 and any(t.startswith("Equal Pay gilt ab") for t in titles)


def test_confirmation_of_an_old_chain_does_not_count_for_a_new_one(session: Session) -> None:
    owner = _user(session, "dispo@x.example")
    worker, client = _worker(session), _client(session)
    old = _assignment(
        session,
        worker,
        client,
        D(2024, 1, 1),
        end=D(2024, 12, 31),
        status=StaffingAssignmentStatus.ENDED,
        owner=owner,
    )
    old.equal_pay_confirmed_on = D(2024, 11, 1)
    session.commit()
    _assignment(session, worker, client, D(2025, 6, 1), owner=owner)  # Luecke > 3 Monate: Reset
    run_deadline_job(session, D(2026, 3, 1))  # Equal Pay der NEUEN Kette ab 1.3.2026
    tasks = _equal_pay_tasks(session)
    assert len(tasks) == 1 and tasks[0].title.startswith("Equal Pay gilt ab 01.03.2026")


def test_confirmation_rules(session: Session) -> None:
    owner = _user(session, "dispo@x.example")
    worker, client = _worker(session), _client(session)
    assignment = _assignment(session, worker, client, D(2025, 1, 1), owner=owner)
    service = StaffingEqualPayService(session)
    with pytest.raises(BusinessRuleError, match="Zukunft"):
        service.confirm(assignment.id, owner, D(2025, 10, 10), today=D(2025, 10, 5))
    with pytest.raises(BusinessRuleError, match="vor dem Beginn"):
        service.confirm(assignment.id, owner, D(2024, 12, 31), today=D(2025, 10, 5))
    service.confirm(assignment.id, owner, D(2025, 10, 2), today=D(2025, 10, 5))
    service.clear(assignment.id, owner)
    session.refresh(assignment)
    assert assignment.equal_pay_confirmed_on is None
    assignment.status = StaffingAssignmentStatus.ENDED
    session.commit()
    with pytest.raises(BusinessRuleError, match="nicht mehr änderbar"):
        service.confirm(assignment.id, owner, today=D(2025, 10, 5))


def test_confirmation_only_from_the_cutoff_day(session: Session) -> None:
    owner = _user(session, "dispo@x.example")
    worker, client = _worker(session), _client(session)
    assignment = _assignment(
        session, worker, client, D(2025, 1, 1), owner=owner
    )  # Stichtag 1.10.2025
    service = StaffingEqualPayService(session)
    with pytest.raises(ConflictError, match="erst ab dem Stichtag"):
        service.confirm(assignment.id, owner, today=D(2025, 9, 30))
    with pytest.raises(ConflictError, match="vor dem Stichtag"):
        service.confirm(assignment.id, owner, D(2025, 9, 30), today=D(2025, 10, 1))
    service.confirm(assignment.id, owner, today=D(2025, 10, 1))  # am Stichtag erlaubt
    session.refresh(assignment)
    assert assignment.equal_pay_confirmed_on == D(2025, 10, 1)


def test_old_confirmation_from_an_earlier_chain_does_not_count(session: Session) -> None:
    from cc_crm.services.staffing_equal_pay import pair_equal_pay_confirmed_on

    owner = _user(session, "dispo@x.example")
    worker, client = _worker(session), _client(session)
    assignment = _assignment(session, worker, client, D(2025, 1, 1), owner=owner)
    assignment.equal_pay_confirmed_on = D(2025, 6, 1)  # vor dem Stichtag
    session.commit()
    args = (session, worker.id, client.id, D(2025, 1, 1))
    assert pair_equal_pay_confirmed_on(*args, D(2025, 10, 1)) is None
    assert pair_equal_pay_confirmed_on(*args, D(2025, 5, 1)) == D(2025, 6, 1)
