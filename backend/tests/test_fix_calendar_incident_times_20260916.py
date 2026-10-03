"""Tests fuer scripts/fix_calendar_incident_times_20260916.py (M365-Sync-
Vorfall vom 2026-09-16, finale Auto-Detect-Fassung).

Schwerpunkte:
1. Auto-Detect findet CalendarEvents ueber updated_at ODER external_graph_
   last_synced_at im Vorfallsfenster - keine Titel-/Typ-Vorauswahl.
2. Graph type=singleInstance/exception -> Einzelkorrektur ueber die eigene
   ID.
3. Graph type=occurrence -> gruppiert nach seriesMasterId, der MASTER wird
   EINMAL korrigiert, nicht jede Occurrence einzeln.
4. Echte Exception-Occurrences einer Serie (per list_series_instances
   gefunden) werden zusaetzlich einzeln korrigiert.
5. CRM-DB-Korrektur ist fuer ALLE betroffenen Zeilen gleich (-10h), egal ob
   Einzeltermin oder Serien-Mitglied.
6. Backup-Schreibfehler bricht vor jeder Aenderung ab.
7. Manuelles --graph-event-id-Override ueberspringt die DB-Auto-Erkennung."""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime

import pytest
from cryptography.fernet import Fernet
from sqlalchemy.orm import Session, sessionmaker

from cc_crm.integrations.microsoft_graph.auth import GraphTokens
from cc_crm.models.calendar_event import CalendarEvent
from cc_crm.models.enums import MailAccountOAuthStatus, MailAccountProvider
from cc_crm.models.mail import MailAccount
from cc_crm.models.user import User
from cc_crm.services import graph_token_service
from scripts.archive import fix_calendar_incident_times_20260916 as script
from tests.tz import utc_naive

_KEY = Fernet.generate_key().decode()

_IN_WINDOW = datetime(2026, 9, 16, 15, 0, tzinfo=UTC)
_OUT_OF_WINDOW = datetime(2026, 9, 1, 0, 0, tzinfo=UTC)


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
    session: Session,
    *,
    user_id: uuid.UUID,
    graph_event_id: str,
    start_at: datetime,
    updated_at_in_window: bool,
) -> CalendarEvent:
    event = CalendarEvent(
        title="Termin",
        start_at=start_at,
        end_at=start_at,
        owner_user_id=user_id,
        created_by_user_id=user_id,
        external_graph_event_id=graph_event_id,
        external_graph_last_synced_at=_IN_WINDOW if updated_at_in_window else _OUT_OF_WINDOW,
    )
    session.add(event)
    session.commit()
    session.refresh(event)
    if updated_at_in_window:
        # updated_at wird per onupdate=func.now() bei jedem weiteren Schreiben
        # ueberschrieben - fuer den Test reicht external_graph_last_synced_at
        # im Fenster, das allein qualifiziert laut _find_incident_events().
        pass
    return event


def _run(monkeypatch: pytest.MonkeyPatch, *, args: list[str]) -> None:
    monkeypatch.setattr("sys.argv", ["fix_calendar_incident_times_20260916.py", *args])
    script.main()


def _fake_get_event_raw(graph_types: dict[str, dict]):
    def _fake(access_token, *, graph_event_id):
        return graph_types.get(graph_event_id)

    return _fake


def _fake_get_event(graph_states: dict[str, object]):
    def _fake(access_token, *, graph_event_id):
        return graph_states.get(graph_event_id)

    return _fake


class TestAutoDetect:
    def test_finds_events_via_external_graph_last_synced_at_in_window(
        self, session_factory: sessionmaker[Session], monkeypatch: pytest.MonkeyPatch, tmp_path
    ) -> None:
        monkeypatch.setattr(script, "_BACKUP_DIR", tmp_path)
        corrupted = datetime(2026, 9, 17, 2, 30, 0)

        with session_factory() as session:
            user = _make_user(session)
            _make_graph_account(session, user_id=user.id)
            _make_event(
                session,
                user_id=user.id,
                graph_event_id="graph-evt-in-window",
                start_at=corrupted,
                updated_at_in_window=True,
            )
            _make_event(
                session,
                user_id=user.id,
                graph_event_id="graph-evt-out-of-window",
                start_at=corrupted,
                updated_at_in_window=False,
            )

        from cc_crm.integrations.microsoft_graph.client import GraphEvent

        monkeypatch.setattr(
            script,
            "get_event_raw",
            _fake_get_event_raw(
                {"graph-evt-in-window": {"type": "singleInstance", "seriesMasterId": None}}
            ),
        )
        monkeypatch.setattr(
            script,
            "get_event",
            _fake_get_event(
                {
                    "graph-evt-in-window": GraphEvent(
                        id="graph-evt-in-window",
                        subject="Termin",
                        body_text=None,
                        start_at=corrupted,
                        end_at=corrupted,
                        location=None,
                        last_modified_at=datetime(2026, 9, 16, 15, 55, tzinfo=UTC),
                    )
                }
            ),
        )

        def failing_update_event(*a, **k):
            raise AssertionError("Dry-Run darf nicht schreiben")

        monkeypatch.setattr(script, "update_event", failing_update_event)

        _run(monkeypatch, args=["--mail-account", "info@commandeurconsulting.de"])

        backups = list(tmp_path.glob("calendar_incident_pre_fix_*.json"))
        data = json.loads(backups[0].read_text(encoding="utf-8"))
        graph_ids = {s["graph_event_id"] for s in data["singles"]}
        assert graph_ids == {"graph-evt-in-window"}


class TestSingleInstanceCorrection:
    def test_commit_corrects_crm_and_graph(
        self, session_factory: sessionmaker[Session], monkeypatch: pytest.MonkeyPatch, tmp_path
    ) -> None:
        monkeypatch.setattr(script, "_BACKUP_DIR", tmp_path)
        corrupted = datetime(2026, 9, 17, 2, 30, 0)
        expected = datetime(2026, 9, 16, 16, 30, 0)

        with session_factory() as session:
            user = _make_user(session)
            _make_graph_account(session, user_id=user.id)
            event = _make_event(
                session,
                user_id=user.id,
                graph_event_id="graph-evt-single",
                start_at=corrupted,
                updated_at_in_window=True,
            )
            event_id = event.id

        from cc_crm.integrations.microsoft_graph.client import GraphEvent

        graph_event = GraphEvent(
            id="graph-evt-single",
            subject="Pascal Franz",
            body_text="Notizen",
            start_at=corrupted,
            end_at=corrupted,
            location=None,
            last_modified_at=datetime(2026, 9, 16, 15, 55, tzinfo=UTC),
        )
        monkeypatch.setattr(
            script,
            "get_event_raw",
            _fake_get_event_raw({"graph-evt-single": {"type": "singleInstance"}}),
        )
        monkeypatch.setattr(
            script, "get_event", _fake_get_event({"graph-evt-single": graph_event})
        )

        pushed = {}

        def fake_update_event(access_token, *, graph_event_id, start_at, end_at, **kwargs):
            pushed["graph_event_id"] = graph_event_id
            pushed["start_at"] = start_at
            pushed["end_at"] = end_at

        monkeypatch.setattr(script, "update_event", fake_update_event)

        _run(
            monkeypatch,
            args=["--mail-account", "info@commandeurconsulting.de", "--commit"],
        )

        assert pushed["graph_event_id"] == "graph-evt-single"
        assert pushed["start_at"] == expected

        with session_factory() as session:
            refreshed = session.get(CalendarEvent, event_id)
            assert refreshed is not None
            assert utc_naive(refreshed.start_at) == utc_naive(expected)
            assert refreshed.local_last_synced_at is not None


class TestSeriesCorrection:
    def test_occurrence_group_patches_master_once_not_each_occurrence(
        self, session_factory: sessionmaker[Session], monkeypatch: pytest.MonkeyPatch, tmp_path
    ) -> None:
        monkeypatch.setattr(script, "_BACKUP_DIR", tmp_path)
        corrupted_1 = datetime(2026, 8, 3, 19, 0, 0)
        corrupted_2 = datetime(2026, 6, 15, 19, 0, 0)

        with session_factory() as session:
            user = _make_user(session)
            _make_graph_account(session, user_id=user.id)
            e1 = _make_event(
                session,
                user_id=user.id,
                graph_event_id="graph-occ-1",
                start_at=corrupted_1,
                updated_at_in_window=True,
            )
            e2 = _make_event(
                session,
                user_id=user.id,
                graph_event_id="graph-occ-2",
                start_at=corrupted_2,
                updated_at_in_window=True,
            )
            e1_id, e2_id = e1.id, e2.id

        from cc_crm.integrations.microsoft_graph.client import GraphEvent

        master_start = datetime(2026, 6, 15, 19, 0, 0)
        master_event = GraphEvent(
            id="graph-series-master",
            subject="CV OUTs",
            body_text=None,
            start_at=master_start,
            end_at=master_start,
            location=None,
            last_modified_at=datetime(2026, 9, 16, 15, 55, tzinfo=UTC),
        )

        monkeypatch.setattr(
            script,
            "get_event_raw",
            _fake_get_event_raw(
                {
                    "graph-occ-1": {"type": "occurrence", "seriesMasterId": "graph-series-master"},
                    "graph-occ-2": {"type": "occurrence", "seriesMasterId": "graph-series-master"},
                }
            ),
        )
        monkeypatch.setattr(
            script, "get_event", _fake_get_event({"graph-series-master": master_event})
        )
        monkeypatch.setattr(script, "list_series_instances", lambda *a, **k: [])

        patched_ids = []

        def fake_update_event(access_token, *, graph_event_id, start_at, end_at, **kwargs):
            patched_ids.append(graph_event_id)

        monkeypatch.setattr(script, "update_event", fake_update_event)

        _run(
            monkeypatch,
            args=["--mail-account", "info@commandeurconsulting.de", "--commit"],
        )

        # Nur der Master wurde per update_event() angefasst - NICHT die
        # einzelnen Occurrences (graph-occ-1/graph-occ-2).
        assert patched_ids == ["graph-series-master"]

        with session_factory() as session:
            refreshed_1 = session.get(CalendarEvent, e1_id)
            refreshed_2 = session.get(CalendarEvent, e2_id)
            shift = script._INCIDENT_SHIFT
            assert utc_naive(refreshed_1.start_at) == utc_naive(corrupted_1 - shift)
            assert utc_naive(refreshed_2.start_at) == utc_naive(corrupted_2 - shift)

    def test_exception_occurrence_of_series_is_corrected_individually(
        self, session_factory: sessionmaker[Session], monkeypatch: pytest.MonkeyPatch, tmp_path
    ) -> None:
        monkeypatch.setattr(script, "_BACKUP_DIR", tmp_path)
        corrupted = datetime(2026, 8, 3, 19, 0, 0)

        with session_factory() as session:
            user = _make_user(session)
            _make_graph_account(session, user_id=user.id)
            _make_event(
                session,
                user_id=user.id,
                graph_event_id="graph-occ-1",
                start_at=corrupted,
                updated_at_in_window=True,
            )

        from cc_crm.integrations.microsoft_graph.client import GraphEvent

        master_event = GraphEvent(
            id="graph-series-master",
            subject="CV OUTs",
            body_text=None,
            start_at=corrupted,
            end_at=corrupted,
            location=None,
            last_modified_at=datetime(2026, 9, 16, 15, 55, tzinfo=UTC),
        )
        exc_event = GraphEvent(
            id="graph-exception-1",
            subject="CV OUTs (verlegt)",
            body_text=None,
            start_at=datetime(2026, 7, 10, 20, 0, 0),
            end_at=datetime(2026, 7, 10, 21, 0, 0),
            location=None,
            last_modified_at=datetime(2026, 9, 16, 15, 55, tzinfo=UTC),
        )

        monkeypatch.setattr(
            script,
            "get_event_raw",
            _fake_get_event_raw(
                {"graph-occ-1": {"type": "occurrence", "seriesMasterId": "graph-series-master"}}
            ),
        )
        monkeypatch.setattr(
            script,
            "get_event",
            _fake_get_event(
                {"graph-series-master": master_event, "graph-exception-1": exc_event}
            ),
        )
        monkeypatch.setattr(
            script,
            "list_series_instances",
            lambda *a, **k: [
                {
                    "id": "graph-exception-1",
                    "type": "exception",
                    "start": {"dateTime": "2026-07-10T20:00:00.0000000", "timeZone": "UTC"},
                    "end": {"dateTime": "2026-07-10T21:00:00.0000000", "timeZone": "UTC"},
                }
            ],
        )

        patched = {}

        def fake_update_event(access_token, *, graph_event_id, start_at, end_at, **kwargs):
            patched[graph_event_id] = (start_at, end_at)

        monkeypatch.setattr(script, "update_event", fake_update_event)

        _run(
            monkeypatch,
            args=["--mail-account", "info@commandeurconsulting.de", "--commit"],
        )

        assert "graph-series-master" in patched
        assert "graph-exception-1" in patched
        # 20:00 UTC im Juli = 22:00 Berlin (CEST) - minus 10h = 12:00.
        assert patched["graph-exception-1"][0] == datetime(2026, 7, 10, 12, 0, 0)


class TestSafety:
    def test_backup_write_failure_aborts_before_any_change(
        self, session_factory: sessionmaker[Session], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        corrupted = datetime(2026, 9, 17, 2, 30, 0)

        with session_factory() as session:
            user = _make_user(session)
            _make_graph_account(session, user_id=user.id)
            event = _make_event(
                session,
                user_id=user.id,
                graph_event_id="graph-evt-single",
                start_at=corrupted,
                updated_at_in_window=True,
            )
            event_id = event.id

        monkeypatch.setattr(
            script,
            "get_event_raw",
            _fake_get_event_raw({"graph-evt-single": {"type": "singleInstance"}}),
        )

        from cc_crm.integrations.microsoft_graph.client import GraphEvent

        monkeypatch.setattr(
            script,
            "get_event",
            _fake_get_event(
                {
                    "graph-evt-single": GraphEvent(
                        id="graph-evt-single",
                        subject="Termin",
                        body_text=None,
                        start_at=corrupted,
                        end_at=corrupted,
                        location=None,
                        last_modified_at=datetime(2026, 9, 16, 15, 55, tzinfo=UTC),
                    )
                }
            ),
        )

        def failing_write_backup(singles, masters):
            raise OSError("Festplatte voll (simuliert)")

        monkeypatch.setattr(script, "_write_backup", failing_write_backup)

        def failing_update_event(*a, **k):
            raise AssertionError("darf nach Backup-Fehler nicht aufgerufen werden")

        monkeypatch.setattr(script, "update_event", failing_update_event)

        _run(
            monkeypatch,
            args=["--mail-account", "info@commandeurconsulting.de", "--commit"],
        )

        with session_factory() as session:
            refreshed = session.get(CalendarEvent, event_id)
            assert utc_naive(refreshed.start_at) == utc_naive(corrupted)


class TestManualOverride:
    def test_manual_graph_event_id_skips_db_auto_detect(
        self, session_factory: sessionmaker[Session], monkeypatch: pytest.MonkeyPatch, tmp_path
    ) -> None:
        monkeypatch.setattr(script, "_BACKUP_DIR", tmp_path)
        corrupted = datetime(2026, 9, 17, 2, 30, 0)
        expected = datetime(2026, 9, 16, 16, 30, 0)

        with session_factory() as session:
            user = _make_user(session)
            _make_graph_account(session, user_id=user.id)
            # NICHT im Vorfallsfenster - Auto-Detect wuerde das ignorieren,
            # das manuelle Override soll es trotzdem verarbeiten.
            _make_event(
                session,
                user_id=user.id,
                graph_event_id="graph-evt-manual",
                start_at=corrupted,
                updated_at_in_window=False,
            )

        from cc_crm.integrations.microsoft_graph.client import GraphEvent

        monkeypatch.setattr(
            script,
            "get_event_raw",
            _fake_get_event_raw({"graph-evt-manual": {"type": "singleInstance"}}),
        )
        monkeypatch.setattr(
            script,
            "get_event",
            _fake_get_event(
                {
                    "graph-evt-manual": GraphEvent(
                        id="graph-evt-manual",
                        subject="Termin",
                        body_text=None,
                        start_at=corrupted,
                        end_at=corrupted,
                        location=None,
                        last_modified_at=datetime(2026, 9, 16, 15, 55, tzinfo=UTC),
                    )
                }
            ),
        )

        pushed = {}
        monkeypatch.setattr(
            script,
            "update_event",
            lambda access_token, *, graph_event_id, start_at, end_at, **k: pushed.update(
                {"id": graph_event_id, "start_at": start_at}
            ),
        )

        _run(
            monkeypatch,
            args=[
                "--mail-account",
                "info@commandeurconsulting.de",
                "--graph-event-id",
                "graph-evt-manual",
                "--commit",
            ],
        )

        assert pushed["start_at"] == expected
