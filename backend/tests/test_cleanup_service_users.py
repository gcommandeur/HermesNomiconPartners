from datetime import datetime

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from cc_crm.models.api_key import ApiKey
from cc_crm.models.calendar_event import CalendarEvent
from cc_crm.models.candidate import Candidate
from cc_crm.models.user import User
from scripts import cleanup_service_users as cleanup_script


def _use_session_factory(
    monkeypatch: pytest.MonkeyPatch, session_factory: sessionmaker[Session]
) -> None:
    monkeypatch.setattr(cleanup_script, "SessionLocal", session_factory)


def _make_keep_user(session: Session) -> User:
    user = User(
        email=cleanup_script.KEEP_EMAIL,
        hashed_password="x",
        display_name="Commandeur",
        role="admin",
    )
    session.add(user)
    session.commit()
    return user


def _make_service_user(session: Session, *, name: str = "Bullhorn Sync") -> User:
    user = User(
        email=f"service+{name.lower().replace(' ', '-')}-abc123@cc-crm.local",
        hashed_password="x",
        display_name=f"Service: {name}",
    )
    session.add(user)
    session.commit()
    return user


def test_dry_run_does_not_delete_anything(
    monkeypatch: pytest.MonkeyPatch, session_factory: sessionmaker[Session]
) -> None:
    _use_session_factory(monkeypatch, session_factory)
    with session_factory() as session:
        _make_keep_user(session)
        service_user = _make_service_user(session)

    stats = cleanup_script.cleanup(commit=False)

    assert stats == {"deleted": 0, "skipped_calendar": 0, "skipped_unrecognized": 0, "errors": 0}
    with session_factory() as session:
        assert session.get(User, service_user.id) is not None


def test_commit_deletes_recognized_service_users_keeps_real_login(
    monkeypatch: pytest.MonkeyPatch, session_factory: sessionmaker[Session]
) -> None:
    _use_session_factory(monkeypatch, session_factory)
    with session_factory() as session:
        keep_user = _make_keep_user(session)
        service_user = _make_service_user(session)
        test_user = User(
            email="test@commandeur.example", hashed_password="x", display_name="Test User"
        )
        session.add(test_user)
        session.commit()

    stats = cleanup_script.cleanup(commit=True)

    assert stats == {"deleted": 2, "skipped_calendar": 0, "skipped_unrecognized": 0, "errors": 0}
    with session_factory() as session:
        assert session.get(User, keep_user.id) is not None
        assert session.get(User, service_user.id) is None
        assert session.get(User, test_user.id) is None


def test_user_with_calendar_events_is_never_deleted(
    monkeypatch: pytest.MonkeyPatch, session_factory: sessionmaker[Session]
) -> None:
    """CASCADE-Risiko (Auftrag): ein User, der Owner/Ersteller eines
    Kalendertermins ist, wird NICHT geloescht - das haerte den Termin
    mitloeschen."""
    _use_session_factory(monkeypatch, session_factory)
    with session_factory() as session:
        _make_keep_user(session)
        service_user = _make_service_user(session)
        session.add(
            CalendarEvent(
                title="Alter Termin",
                start_at=datetime(2026, 1, 1, 10, 0, 0),
                end_at=datetime(2026, 1, 1, 10, 30, 0),
                owner_user_id=service_user.id,
                created_by_user_id=service_user.id,
            )
        )
        session.commit()

    stats = cleanup_script.cleanup(commit=True)

    assert stats == {"deleted": 0, "skipped_calendar": 1, "skipped_unrecognized": 0, "errors": 0}
    with session_factory() as session:
        assert session.get(User, service_user.id) is not None


def test_unrecognized_domain_is_skipped_not_deleted(
    monkeypatch: pytest.MonkeyPatch, session_factory: sessionmaker[Session]
) -> None:
    """Sicherheitsnetz: eine E-Mail ausserhalb der bekannten Service-/
    Test-Domains gilt als potenziell echter Mitarbeiter und wird nie
    automatisch geloescht, selbst mit --commit."""
    _use_session_factory(monkeypatch, session_factory)
    with session_factory() as session:
        _make_keep_user(session)
        real_colleague = User(
            email="kollege@commandeurconsulting.de", hashed_password="x", display_name="Kollege"
        )
        session.add(real_colleague)
        session.commit()

    stats = cleanup_script.cleanup(commit=True)

    assert stats == {"deleted": 0, "skipped_calendar": 0, "skipped_unrecognized": 1, "errors": 0}
    with session_factory() as session:
        assert session.get(User, real_colleague.id) is not None


def test_commit_cleans_up_cascade_referenced_api_key_rows(
    monkeypatch: pytest.MonkeyPatch, session_factory: sessionmaker[Session]
) -> None:
    """ApiKey.user_id ist CASCADE - wird hier explizit vorab geloescht statt
    nur auf DB-Cascade zu vertrauen (die lokal ohne PRAGMA foreign_keys
    nicht greift), sonst bliebe eine verwaiste api_keys-Zeile zurueck."""
    _use_session_factory(monkeypatch, session_factory)
    with session_factory() as session:
        _make_keep_user(session)
        service_user = _make_service_user(session)
        session.add(ApiKey(name="Bullhorn Sync", key_hash="x", user_id=service_user.id))
        session.commit()

    stats = cleanup_script.cleanup(commit=True)

    assert stats["deleted"] == 1
    with session_factory() as session:
        assert session.get(User, service_user.id) is None
        remaining_keys = session.scalars(
            select(ApiKey).where(ApiKey.user_id == service_user.id)
        ).all()
        assert remaining_keys == []


def test_set_null_reference_is_not_a_blocker(
    monkeypatch: pytest.MonkeyPatch, session_factory: sessionmaker[Session]
) -> None:
    """Candidate.owner_user_id ist SET NULL, kein harter Blocker wie
    CalendarEvent - der User darf trotzdem geloescht werden."""
    _use_session_factory(monkeypatch, session_factory)
    with session_factory() as session:
        _make_keep_user(session)
        service_user = _make_service_user(session)
        session.add(
            Candidate(first_name="Anna", last_name="Test", owner_user_id=service_user.id)
        )
        session.commit()

    stats = cleanup_script.cleanup(commit=True)

    assert stats["deleted"] == 1
