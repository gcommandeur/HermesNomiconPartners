# NOMICON: Arbeitnehmerueberlassung - nur in der Nomicon-Kopie.
"""Aktive Einsaetze ohne gueltigen Vertrag: der Tagesjob legt eine kurze Aufgabe an (einmalig)."""

from datetime import date
from decimal import Decimal

from sqlalchemy.orm import Session

from cc_crm.models.staffing import StaffingContract, StaffingContractStatus
from cc_crm.services.staffing_deadline_job import run_deadline_job
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


def _contract_tasks(session: Session):  # type: ignore[no-untyped-def]
    return [t for t in _tasks(session) if t.title.startswith("Überlassungsvertrag")]


def test_job_reports_active_assignments_without_a_contract_once(session: Session) -> None:
    owner = _user(session, "dispo@x.example")
    worker, client = _worker(session), _client(session)
    assignment = _assignment(
        session, worker, client, D(2026, 1, 1), end=D(2026, 12, 31), owner=owner
    )
    assignment.contract_id = None  # Altbestand: aktiv, aber ohne Vertrag
    assignment.hourly_wage = Decimal("14.50")
    assignment.billing_rate = Decimal("29.00")
    session.commit()

    run_deadline_job(session, D(2026, 6, 1))
    (task,) = _contract_tasks(session)
    assert task.owner_user_id == owner.id
    assert task.title == "Überlassungsvertrag fehlt: Mira Muster bei Logistik GmbH"
    text = f"{task.title} {task.description}"
    assert "Kein Überlassungsvertrag" in text and "bleibt aktiv" in text
    for forbidden in ("14.50", "29.00", "€"):
        assert forbidden not in text

    run_deadline_job(session, D(2026, 6, 2))
    assert len(_contract_tasks(session)) == 1  # einmalig je Zustand


def test_job_reports_an_expired_contract_and_stays_quiet_for_a_valid_one(session: Session) -> None:
    owner = _user(session, "dispo@x.example")
    worker, client = _worker(session), _client(session)
    other = _worker(session, "Jonas")
    good = StaffingContract(
        client_company_id=client.id, valid_from=D(2025, 1, 1), status=StaffingContractStatus.ACTIVE
    )
    expired = StaffingContract(
        client_company_id=client.id,
        valid_from=D(2025, 1, 1),
        valid_to=D(2026, 3, 31),
        status=StaffingContractStatus.ACTIVE,
    )
    session.add_all([good, expired])
    session.commit()
    ok = _assignment(session, worker, client, D(2026, 1, 1), end=D(2026, 12, 31), owner=owner)
    ok.contract_id = good.id
    late = _assignment(session, other, client, D(2026, 1, 1), end=D(2026, 12, 31), owner=owner)
    late.contract_id = expired.id
    session.commit()

    run_deadline_job(session, D(2026, 6, 1))
    (task,) = _contract_tasks(session)
    assert (
        task.title == "Überlassungsvertrag deckt Einsatz nicht mehr: Jonas Muster bei Logistik GmbH"
    )
