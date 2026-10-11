# NOMICON: Arbeitnehmerueberlassung - nur in der Nomicon-Kopie.
"""Einstellungen und taeglicher Job der Ueberlassungsfristen (mit Datenbank)."""

from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from cc_crm.core.errors import BusinessRuleError
from cc_crm.core.security import hash_password
from cc_crm.models.candidate import Candidate
from cc_crm.models.client_company import ClientCompany
from cc_crm.models.staffing import (
    StaffingAssignment,
    StaffingAssignmentStatus,
    StaffingLicense,
    StaffingWorker,
)
from cc_crm.models.task import Task
from cc_crm.models.user import User
from cc_crm.services.staffing_deadline_job import pair_deadline, run_deadline_job
from cc_crm.services.staffing_deadlines import DeadlineConfig, Traffic
from cc_crm.services.staffing_settings import load_config, save_config

D = date


@pytest.fixture
def session(session_factory: sessionmaker[Session]):  # type: ignore[no-untyped-def]
    with session_factory() as s:
        yield s


def _user(session: Session, email: str, role: str = "member") -> User:
    user = User(email=email, hashed_password=hash_password("x"), role=role)
    session.add(user)
    session.commit()
    return user


def _worker(session: Session, first: str = "Mira") -> StaffingWorker:
    candidate = Candidate(first_name=first, last_name="Muster")
    session.add(candidate)
    session.flush()
    worker = StaffingWorker(candidate_id=candidate.id, hourly_wage=Decimal("14.50"))
    session.add(worker)
    session.commit()
    return worker


def _client(session: Session, name: str = "Logistik GmbH") -> ClientCompany:
    client = ClientCompany(name=name)
    session.add(client)
    session.commit()
    return client


def _assignment(
    session: Session,
    worker: StaffingWorker,
    client: ClientCompany,
    start: date,
    *,
    end: date | None = None,
    status: StaffingAssignmentStatus = StaffingAssignmentStatus.ACTIVE,
    owner: User | None = None,
) -> StaffingAssignment:
    assignment = StaffingAssignment(
        worker_id=worker.id,
        client_company_id=client.id,
        start_date=start,
        planned_end_date=end if status != StaffingAssignmentStatus.ENDED else None,
        actual_end_date=end if status == StaffingAssignmentStatus.ENDED else None,
        status=status,
        owner_user_id=owner.id if owner else None,
    )
    session.add(assignment)
    session.commit()
    return assignment


# --- Einstellungen --------------------------------------------------------------------------


def test_settings_default_save_and_reload(session: Session) -> None:
    assert load_config(session) == DeadlineConfig()
    changed = DeadlineConfig(max_months=12, equal_pay_months=6, yellow_days=45, red_days=15)
    save_config(session, changed)
    assert load_config(session) == changed
    save_config(session, DeadlineConfig())
    assert load_config(session) == DeadlineConfig()


@pytest.mark.parametrize(
    "config",
    [
        DeadlineConfig(max_months=9, equal_pay_months=9),
        DeadlineConfig(red_days=90, yellow_days=60),
        DeadlineConfig(max_months=0),
        DeadlineConfig(reset_gap_months=-1),
    ],
)
def test_settings_reject_inconsistent_values(session: Session, config: DeadlineConfig) -> None:
    with pytest.raises(BusinessRuleError):
        save_config(session, config)
    assert load_config(session) == DeadlineConfig()


def test_settings_fall_back_to_default_for_garbage(session: Session) -> None:
    from cc_crm.models.app_setting import AppSetting

    session.add(AppSetting(key="staffing_max_assignment_months", value="achtzehn"))
    session.add(AppSetting(key="staffing_yellow_days", value=True))
    session.commit()
    assert load_config(session) == DeadlineConfig()


# --- Fristen je Paar ------------------------------------------------------------------------


def test_pair_deadline_ignores_aborted_and_other_clients(session: Session) -> None:
    worker, client, other = _worker(session), _client(session), _client(session, "Andere AG")
    _assignment(
        session,
        worker,
        client,
        D(2025, 1, 1),
        end=D(2025, 3, 31),
        status=StaffingAssignmentStatus.ENDED,
    )
    _assignment(
        session,
        worker,
        client,
        D(2025, 7, 1),
        end=D(2025, 8, 31),
        status=StaffingAssignmentStatus.ABORTED,
    )  # zaehlt nicht
    _assignment(session, worker, other, D(2024, 1, 1))  # anderer Kunde, eigener Zaehler
    result = pair_deadline(session, worker.id, client.id, D(2025, 4, 15))
    assert result.chain_start == D(2025, 1, 1)
    assert result.counted_days == 90
    other_result = pair_deadline(session, worker.id, other.id, D(2025, 4, 15))
    assert other_result.chain_start == D(2024, 1, 1)


# --- Taeglicher Job -------------------------------------------------------------------------


def _tasks(session: Session) -> list[Task]:
    return list(session.scalars(select(Task).order_by(Task.title)).all())


def test_job_creates_one_task_per_threshold_for_the_owner(session: Session) -> None:
    owner, _admin = _user(session, "dispo@x.example"), _user(session, "gf@x.example", "admin")
    worker, client = _worker(session), _client(session)
    _assignment(session, worker, client, D(2025, 1, 1), owner=owner)  # Frist 30.6.2026

    # 1.6.2026: 29 Tage Rest -> rot; Equal Pay (seit 1.10.2025) ebenfalls faellig
    first = run_deadline_job(session, D(2026, 6, 1))
    tasks = _tasks(session)
    assert first.pairs_checked == 1
    assert first.tasks_created == len(tasks) == 2
    assert {t.owner_user_id for t in tasks} == {owner.id}
    titles = " | ".join(t.title for t in tasks)
    assert "Ueberlassungsfrist: Mira Muster bei Logistik GmbH" in titles
    assert "Equal Pay ab jetzt" in titles
    red = next(t for t in tasks if t.title.startswith("Ueberlassungsfrist"))
    assert "30.06.2026" in (red.description or "")
    assert "kein Rechtsrat" in (red.description or "")

    # Idempotent: nochmal am selben und am naechsten Tag -> nichts Neues
    assert run_deadline_job(session, D(2026, 6, 1)).tasks_created == 0
    assert run_deadline_job(session, D(2026, 6, 2)).tasks_created == 0

    # Ueberschritten ist eine neue Stufe -> genau eine weitere Aufgabe
    after = run_deadline_job(session, D(2026, 7, 5))
    assert after.tasks_created == 1
    assert "ueberschritten" in (_tasks(session)[-1].description or "") or any(
        "ueberschritten" in (t.description or "") for t in _tasks(session)
    )


def test_job_yellow_and_green(session: Session) -> None:
    owner = _user(session, "dispo@x.example")
    worker, client = _worker(session), _client(session)
    _assignment(session, worker, client, D(2025, 1, 1), owner=owner)
    assert pair_deadline(session, worker.id, client.id, D(2026, 4, 30)).traffic == Traffic.GREEN
    # Gruen, Equal Pay laeuft aber schon: nur die Equal-Pay-Aufgabe
    assert run_deadline_job(session, D(2026, 4, 30)).tasks_created == 1
    # Gelb (59 Tage): zusaetzlich eine Aufgabe
    assert run_deadline_job(session, D(2026, 5, 2)).tasks_created == 1
    # Rot (29 Tage): noch eine
    assert run_deadline_job(session, D(2026, 6, 1)).tasks_created == 1
    assert len(_tasks(session)) == 3


def test_job_without_owner_goes_to_active_admins_only(session: Session) -> None:
    admin = _user(session, "gf@x.example", "admin")
    inactive = _user(session, "alt@x.example", "admin")
    inactive.is_active = False
    _user(session, "member@x.example")
    session.commit()
    worker, client = _worker(session), _client(session)
    _assignment(session, worker, client, D(2025, 1, 1), owner=None)
    run_deadline_job(session, D(2026, 6, 1))
    assert {t.owner_user_id for t in _tasks(session)} == {admin.id}


def test_job_ignores_ended_pairs_and_expired_chains(session: Session) -> None:
    owner = _user(session, "dispo@x.example")
    worker, client = _worker(session), _client(session)
    _assignment(
        session,
        worker,
        client,
        D(2024, 1, 1),
        end=D(2024, 6, 30),
        status=StaffingAssignmentStatus.ENDED,
        owner=owner,
    )
    result = run_deadline_job(session, D(2026, 6, 1))
    assert (result.pairs_checked, result.tasks_created) == (0, 0)  # kein aktiver/geplanter Einsatz


def test_job_uses_configured_values(session: Session) -> None:
    owner = _user(session, "dispo@x.example")
    worker, client = _worker(session), _client(session)
    _assignment(session, worker, client, D(2025, 1, 1), owner=owner)
    save_config(
        session, DeadlineConfig(max_months=12, equal_pay_months=6, yellow_days=60, red_days=30)
    )
    run_deadline_job(session, D(2025, 11, 15))  # Frist 31.12.2025: 46 Tage -> gelb (+ Equal Pay)
    assert any("Ueberlassungsfrist" in t.title for t in _tasks(session))


def test_job_license_reminders(session: Session) -> None:
    admin = _user(session, "gf@x.example", "admin")
    _user(session, "member@x.example")
    session.add(
        StaffingLicense(
            authority="Bundesagentur fuer Arbeit",
            file_number="AUeG-123",
            valid_from=D(2024, 1, 1),
            valid_to=D(2026, 12, 31),
            reminder_days=90,
        )
    )
    session.add(  # unbefristet: nie Erinnerung
        StaffingLicense(authority="Unbefristet", valid_from=D(2020, 1, 1), valid_to=None)
    )
    session.commit()
    assert run_deadline_job(session, D(2026, 9, 30)).tasks_created == 0  # 92 Tage Rest
    assert run_deadline_job(session, D(2026, 10, 2)).tasks_created == 1  # 90 Tage
    tasks = _tasks(session)
    assert len(tasks) == 1
    assert tasks[0].owner_user_id == admin.id
    assert "laeuft ab" in tasks[0].title
    assert "AUeG-123" in (tasks[0].description or "")
    assert run_deadline_job(session, D(2026, 10, 3)).tasks_created == 0  # keine Dublette
    # Verlaengerung (neues valid_to) -> bei Annaeherung wieder eine neue Aufgabe
    lic = session.scalars(
        select(StaffingLicense).where(StaffingLicense.file_number == "AUeG-123")
    ).one()
    lic.valid_to = D(2027, 12, 31)
    session.commit()
    assert run_deadline_job(session, D(2026, 10, 4)).tasks_created == 0
    assert run_deadline_job(session, D(2027, 10, 5)).tasks_created == 1
    assert run_deadline_job(session, D(2028, 1, 5)).tasks_created == 1  # abgelaufen
