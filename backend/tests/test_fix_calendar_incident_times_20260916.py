"""Tests fuer scripts/fix_calendar_incident_times_20260916.py (M365-Sync-
Vorfall vom 2026-09-16, Population A - die 7 verifizierten Interview-
Termine).

Schwerpunkte:
1. Dry-Run schreibt das Backup-Artefakt, aber weder CRM-DB noch Graph.
2. --commit korrigiert CRM-DB (start_at/end_at -10h, local_last_synced_at
   in derselben Transaktion) UND schickt die korrigierte Zeit per
   update_event() nach Graph.
3. Ein Backup-Schreibfehler bricht VOR jeder Aenderung ab (Sicherheits-
   voraussetzung aus dem Vorfalls-Auftrag).
4. Ein fehlendes CRM-Event bzw. ein Graph-Lesefehler wird uebersprungen,
   nicht als Fehler des gesamten Laufs behandelt."""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime

import pytest
from cryptography.fernet import Fernet
from sqlalchemy.orm import Session, sessionmaker

from cc_crm.integrations.microsoft_graph.auth import GraphTokens
from cc_crm.integrations.microsoft_graph.client import GraphApiError, GraphEvent
from cc_crm.models.calendar_event import CalendarEvent
from cc_crm.models.enums import MailAccountOAuthStatus, MailAccountProvider
from cc_crm.models.mail import MailAccount
from cc_crm.models.user import User
from cc_crm.services import graph_token_service
from scripts import fix_calendar_incident_times_20260916 as script

_KEY = Fernet.generate_key().decode()


@pytest.fixture(autouse=True)
def _isolate(monkeypatch: pytest.MonkeyPatch, session_factory: sessionmaker[Session]):
    monkeypatch.setattr(script, "SessionLocal", session_factory)
    from cc_crm.core.config import get_settings

    get_settings.cache_clear()
    monkeypatch.setenv("CC_CRM_MAIL_CREDENTIALS_ENCRYPTION_KEY", _KEY)
    monkeypatch.setattr(
        graph_token_service,
        "refresh_access_token",
        lambda *, refresh_token, settings=None: GraphTokens(
            access_token="access-1",
            refresh_token="refresh-1",
            expires_in=3600,
            scope="Calendars.ReadWrite",
        ),
    )
    yield
    get_settings.cache_clear()


def _make_user(session: Session) -> User:
    user = User(email=f"user-{uuid.uuid4().hex[:8]}@commandeur.example", hashed_password="x")
    session.add(user)
    session.commit()
    session.refresh(user)
    return user


def _make_graph_account(session: Session, *, user_id: uuid.UUID) -> MailAccount:
    account = MailAccount(
        address="info@commandeurconsulting.de",
        label="Commandeur Consulting GmbH",
        provider=MailAccountProvider.MICROSOFT_GRAPH,
        encrypted_oauth_refresh_token=Fernet(_KEY.encode()).encrypt(b"refresh-1").decode(),
        oauth_status=MailAccountOAuthStatus.CONNECTED,
        oauth_connected_by_user_id=user_id,
    )
    session.add(account)
    session.commit()
    session.refresh(account)
    return account


def _make_event(
    session: Session, *, user_id: uuid.UUID, graph_event_id: str, start_at: datetime
) -> CalendarEvent:
    event = CalendarEvent(
        title="Pascal Franz",
        start_at=start_at,
        end_at=start_at,
        owner_user_id=user_id,
        created_by_user_id=user_id,
        external_graph_event_id=graph_event_id,
    )
    session.add(event)
    session.commit()
    session.refresh(event)
    return event


def _run(monkeypatch: pytest.MonkeyPatch, *, args: list[str]) -> None:
    monkeypatch.setattr("sys.argv", ["fix_calendar_incident_times_20260916.py", *args])
    script.main()


class TestFixCalendarIncidentTimes:
    def test_dry_run_writes_backup_but_no_db_or_graph_write(
        self,
        session_factory: sessionmaker[Session],
        monkeypatch: pytest.MonkeyPatch,
        tmp_path,
    ) -> None:
        monkeypatch.setattr(script, "_BACKUP_DIR", tmp_path)
        # Korrumpiert: Do 02:30 statt echt Mi 16:30 (=+10h, siehe Vorfall).
        corrupted = datetime(2026, 9, 17, 2, 30, 0)

        with session_factory() as session:
            user = _make_user(session)
            _make_graph_account(session, user_id=user.id)
            event = _make_event(
                session, user_id=user.id, graph_event_id="graph-evt-pascal", start_at=corrupted
            )
            event_id = event.id

        monkeypatch.setattr(
            script,
            "get_event",
            lambda access_token, *, graph_event_id: GraphEvent(
                id=graph_event_id,
                subject="Pascal Franz",
                body_text=None,
                start_at=corrupted,
                end_at=corrupted,
                location=None,
                last_modified_at=datetime(2026, 9, 16, 15, 55, tzinfo=UTC),
            ),
        )

        def failing_update_event(*a, **k):
            raise AssertionError("update_event() darf im Dry-Run nicht aufgerufen werden")

        monkeypatch.setattr(script, "update_event", failing_update_event)

        _run(
            monkeypatch,
            args=[
                "--mail-account",
                "info@commandeurconsulting.de",
                "--graph-event-id",
                "graph-evt-pascal",
            ],
        )

        backups = list(tmp_path.glob("calendar_incident_pre_fix_*.json"))
        assert len(backups) == 1
        data = json.loads(backups[0].read_text(encoding="utf-8"))
        assert data[0]["graph_event_id"] == "graph-evt-pascal"
        assert data[0]["crm_start_at"] == str(corrupted)
        assert data[0]["corrected_start_at"] == str(datetime(2026, 9, 16, 16, 30, 0))

        with session_factory() as session:
            refreshed = session.get(CalendarEvent, event_id)
            assert refreshed is not None
            assert refreshed.start_at == corrupted  # unveraendert

    def test_commit_corrects_crm_and_pushes_to_graph(
        self,
        session_factory: sessionmaker[Session],
        monkeypatch: pytest.MonkeyPatch,
        tmp_path,
    ) -> None:
        monkeypatch.setattr(script, "_BACKUP_DIR", tmp_path)
        corrupted = datetime(2026, 9, 17, 2, 30, 0)
        expected_corrected = datetime(2026, 9, 16, 16, 30, 0)

        with session_factory() as session:
            user = _make_user(session)
            _make_graph_account(session, user_id=user.id)
            event = _make_event(
                session, user_id=user.id, graph_event_id="graph-evt-pascal", start_at=corrupted
            )
            event_id = event.id

        monkeypatch.setattr(
            script,
            "get_event",
            lambda access_token, *, graph_event_id: GraphEvent(
                id=graph_event_id,
                subject="Pascal Franz",
                body_text=None,
                start_at=corrupted,
                end_at=corrupted,
                location=None,
                last_modified_at=datetime(2026, 9, 16, 15, 55, tzinfo=UTC),
            ),
        )

        pushed: dict[str, object] = {}

        def fake_update_event(access_token, *, graph_event_id, start_at, end_at, **kwargs):
            pushed["graph_event_id"] = graph_event_id
            pushed["start_at"] = start_at
            pushed["end_at"] = end_at

        monkeypatch.setattr(script, "update_event", fake_update_event)

        _run(
            monkeypatch,
            args=[
                "--mail-account",
                "info@commandeurconsulting.de",
                "--graph-event-id",
                "graph-evt-pascal",
                "--commit",
            ],
        )

        assert pushed["graph_event_id"] == "graph-evt-pascal"
        assert pushed["start_at"] == expected_corrected
        assert pushed["end_at"] == expected_corrected

        with session_factory() as session:
            refreshed = session.get(CalendarEvent, event_id)
            assert refreshed is not None
            assert refreshed.start_at == expected_corrected
            assert refreshed.end_at == expected_corrected
            assert refreshed.local_last_synced_at is not None

    def test_backup_write_failure_aborts_before_any_change(
        self,
        session_factory: sessionmaker[Session],
        monkeypatch: pytest.MonkeyPatch,
        tmp_path,
    ) -> None:
        corrupted = datetime(2026, 9, 17, 2, 30, 0)

        with session_factory() as session:
            user = _make_user(session)
            _make_graph_account(session, user_id=user.id)
            event = _make_event(
                session, user_id=user.id, graph_event_id="graph-evt-pascal", start_at=corrupted
            )
            event_id = event.id

        monkeypatch.setattr(
            script,
            "get_event",
            lambda access_token, *, graph_event_id: GraphEvent(
                id=graph_event_id,
                subject="Pascal Franz",
                body_text=None,
                start_at=corrupted,
                end_at=corrupted,
                location=None,
                last_modified_at=datetime(2026, 9, 16, 15, 55, tzinfo=UTC),
            ),
        )

        def failing_write_backup(states):
            raise OSError("Festplatte voll (simuliert)")

        monkeypatch.setattr(script, "_write_backup", failing_write_backup)

        def failing_update_event(*a, **k):
            raise AssertionError("update_event() darf nach Backup-Fehler nicht aufgerufen werden")

        monkeypatch.setattr(script, "update_event", failing_update_event)

        _run(
            monkeypatch,
            args=[
                "--mail-account",
                "info@commandeurconsulting.de",
                "--graph-event-id",
                "graph-evt-pascal",
                "--commit",
            ],
        )

        with session_factory() as session:
            refreshed = session.get(CalendarEvent, event_id)
            assert refreshed is not None
            assert refreshed.start_at == corrupted  # unveraendert

    def test_missing_crm_event_is_skipped_not_fatal(
        self,
        session_factory: sessionmaker[Session],
        monkeypatch: pytest.MonkeyPatch,
        tmp_path,
    ) -> None:
        monkeypatch.setattr(script, "_BACKUP_DIR", tmp_path)

        with session_factory() as session:
            user = _make_user(session)
            _make_graph_account(session, user_id=user.id)

        def failing_get_event(access_token, *, graph_event_id):
            raise AssertionError(
                "get_event() sollte fuer ein unbekanntes CRM-Event nicht noetig sein"
            )

        monkeypatch.setattr(script, "get_event", failing_get_event)

        _run(
            monkeypatch,
            args=[
                "--mail-account",
                "info@commandeurconsulting.de",
                "--graph-event-id",
                "graph-evt-unknown",
                "--commit",
            ],
        )

        backups = list(tmp_path.glob("calendar_incident_pre_fix_*.json"))
        data = json.loads(backups[0].read_text(encoding="utf-8"))
        assert data[0]["error"] is not None

    def test_graph_read_error_is_skipped_not_fatal(
        self,
        session_factory: sessionmaker[Session],
        monkeypatch: pytest.MonkeyPatch,
        tmp_path,
    ) -> None:
        monkeypatch.setattr(script, "_BACKUP_DIR", tmp_path)
        corrupted = datetime(2026, 9, 17, 2, 30, 0)

        with session_factory() as session:
            user = _make_user(session)
            _make_graph_account(session, user_id=user.id)
            _make_event(
                session, user_id=user.id, graph_event_id="graph-evt-pascal", start_at=corrupted
            )

        def failing_get_event(access_token, *, graph_event_id):
            raise GraphApiError("Netzwerkfehler (simuliert)")

        monkeypatch.setattr(script, "get_event", failing_get_event)

        _run(
            monkeypatch,
            args=[
                "--mail-account",
                "info@commandeurconsulting.de",
                "--graph-event-id",
                "graph-evt-pascal",
                "--commit",
            ],
        )

        backups = list(tmp_path.glob("calendar_incident_pre_fix_*.json"))
        data = json.loads(backups[0].read_text(encoding="utf-8"))
        assert "Graph-Lesefehler" in data[0]["error"]
