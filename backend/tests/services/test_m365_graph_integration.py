"""Tests fuer die M365-Postfach-Integration (Auftrag "M365-Postfach-
Integration"): OAuth-Flow (state, Start, Callback), Token-Refresh mit
NEEDS_RECONNECT-Handling, Provider-Weiche in mail_sync.py/mail_send.py,
und der bidirektionale Kalender-Sync.

Alle echten Microsoft-Graph-HTTP-Aufrufe sind gemockt (monkeypatch auf die
jeweils aufrufende Stelle, gleiches Muster wie test_mail_send.py/
test_mail_sync.py mit ihren injizierbaren smtp_sender/fetcher) - kein Test
hier oeffnet eine echte Netzwerkverbindung."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest
from cryptography.fernet import Fernet
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from cc_crm.integrations.microsoft_graph.auth import GraphReauthRequiredError, GraphTokens
from cc_crm.integrations.microsoft_graph.client import GraphEvent, GraphMessage
from cc_crm.integrations.microsoft_graph.oauth_state import (
    InvalidOAuthStateError,
    create_oauth_state,
    verify_oauth_state,
)
from cc_crm.models.calendar_event import CalendarEvent
from cc_crm.models.enums import MailAccountOAuthStatus, MailAccountProvider
from cc_crm.models.mail import MailAccount
from cc_crm.models.user import User
from cc_crm.services import calendar_graph_sync, graph_token_service, mail_oauth
from cc_crm.services.graph_token_service import get_valid_access_token
from cc_crm.services.mail_send import send_mail
from cc_crm.services.mail_sync import fetch_mail

_KEY = Fernet.generate_key().decode()


@pytest.fixture(autouse=True)
def _encryption_key(monkeypatch: pytest.MonkeyPatch) -> None:
    from cc_crm.core.config import get_settings

    get_settings.cache_clear()
    monkeypatch.setenv("CC_CRM_MAIL_CREDENTIALS_ENCRYPTION_KEY", _KEY)
    yield
    get_settings.cache_clear()


def _make_user(session: Session, **overrides: object) -> User:
    defaults: dict[str, object] = {
        "email": f"user-{uuid.uuid4().hex[:8]}@commandeur.example",
        "hashed_password": "x",
    }
    defaults.update(overrides)
    user = User(**defaults)
    session.add(user)
    session.commit()
    session.refresh(user)
    return user


def _make_graph_account(
    session: Session, *, user_id: uuid.UUID, **overrides: object
) -> MailAccount:
    defaults: dict[str, object] = {
        "address": "info@commandeurconsulting.de",
        "label": "Commandeur Consulting GmbH",
        "provider": MailAccountProvider.MICROSOFT_GRAPH,
        "encrypted_oauth_refresh_token": Fernet(_KEY.encode()).encrypt(b"refresh-1").decode(),
        "oauth_status": MailAccountOAuthStatus.CONNECTED,
        "oauth_connected_by_user_id": user_id,
    }
    defaults.update(overrides)
    account = MailAccount(**defaults)
    session.add(account)
    session.commit()
    session.refresh(account)
    return account


class TestOAuthState:
    def test_verify_returns_the_encoded_user_id(self) -> None:
        user_id = uuid.uuid4()
        state = create_oauth_state(user_id)
        assert verify_oauth_state(state) == user_id

    def test_verify_rejects_tampered_state(self) -> None:
        with pytest.raises(InvalidOAuthStateError):
            verify_oauth_state("nicht-signiert")

    def test_verify_rejects_expired_state(self, monkeypatch: pytest.MonkeyPatch) -> None:
        state = create_oauth_state(uuid.uuid4())
        # Negativ statt 0: Fernets Ablaufpruefung vergleicht auf Sekunden-
        # granularitaet ("verstrichene Zeit > ttl") - ein Test, der schneller
        # als 1s laeuft, wuerde bei ttl=0 faelschlich noch als "nicht
        # abgelaufen" durchgehen.
        monkeypatch.setattr(
            "cc_crm.integrations.microsoft_graph.oauth_state.OAUTH_STATE_TTL_SECONDS", -1
        )
        with pytest.raises(InvalidOAuthStateError):
            verify_oauth_state(state)


class TestGraphTokenService:
    def test_get_valid_access_token_refreshes_and_rotates_refresh_token(
        self, session_factory: sessionmaker[Session]
    ) -> None:
        with session_factory() as session:
            user = _make_user(session)
            account = _make_graph_account(session, user_id=user.id)

            def fake_refresh(*, refresh_token: str, settings: object = None) -> GraphTokens:
                assert refresh_token == "refresh-1"
                return GraphTokens(
                    access_token="access-2",
                    refresh_token="refresh-2",
                    expires_in=3600,
                    scope="Mail.Send",
                )

            import cc_crm.services.graph_token_service as module

            monkeypatch_target = module.refresh_access_token
            module.refresh_access_token = fake_refresh  # type: ignore[assignment]
            try:
                token = get_valid_access_token(session, account)
            finally:
                module.refresh_access_token = monkeypatch_target  # type: ignore[assignment]

            assert token == "access-2"
            assert account.oauth_status == MailAccountOAuthStatus.CONNECTED
            from cc_crm.services.mail_credentials import decrypt_password

            assert decrypt_password(account.encrypted_oauth_refresh_token) == "refresh-2"

    def test_reauth_required_sets_needs_reconnect(
        self, session_factory: sessionmaker[Session]
    ) -> None:
        with session_factory() as session:
            user = _make_user(session)
            account = _make_graph_account(session, user_id=user.id)

            def fake_refresh(*, refresh_token: str, settings: object = None) -> GraphTokens:
                raise GraphReauthRequiredError("invalid_grant")

            import cc_crm.services.graph_token_service as module

            original = module.refresh_access_token
            module.refresh_access_token = fake_refresh  # type: ignore[assignment]
            try:
                with pytest.raises(GraphReauthRequiredError):
                    get_valid_access_token(session, account)
            finally:
                module.refresh_access_token = original  # type: ignore[assignment]

            assert account.oauth_status == MailAccountOAuthStatus.NEEDS_RECONNECT

    def test_missing_refresh_token_raises_without_calling_microsoft(
        self, session_factory: sessionmaker[Session], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        called = False

        def fake_refresh(*, refresh_token: str, settings: object = None) -> GraphTokens:
            nonlocal called
            called = True
            raise AssertionError("sollte nicht aufgerufen werden")

        monkeypatch.setattr(graph_token_service, "refresh_access_token", fake_refresh)

        with session_factory() as session:
            user = _make_user(session)
            account = _make_graph_account(
                session, user_id=user.id, encrypted_oauth_refresh_token=None
            )
            with pytest.raises(GraphReauthRequiredError):
                get_valid_access_token(session, account)
        assert called is False


class TestMailOAuth:
    def test_start_oauth_flow_builds_authorization_url_with_state(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("CC_CRM_MS_GRAPH_CLIENT_ID", "client-1")
        monkeypatch.setenv("CC_CRM_MS_GRAPH_TENANT_ID", "tenant-1")
        monkeypatch.setenv("CC_CRM_MS_GRAPH_CLIENT_SECRET", "secret-1")
        from cc_crm.core.config import get_settings

        get_settings.cache_clear()
        try:
            url = mail_oauth.start_oauth_flow(
                redirect_uri="https://example.test/callback", current_user_id=uuid.uuid4()
            )
        finally:
            get_settings.cache_clear()
        assert "login.microsoftonline.com/tenant-1" in url
        assert "client_id=client-1" in url
        assert "state=" in url

    def test_handle_oauth_callback_creates_new_graph_account(
        self, session_factory: sessionmaker[Session], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        with session_factory() as session:
            user = _make_user(session)
            state = create_oauth_state(user.id)

            monkeypatch.setattr(
                mail_oauth,
                "exchange_code_for_tokens",
                lambda *, code, redirect_uri, settings=None: GraphTokens(
                    access_token="access-1",
                    refresh_token="refresh-1",
                    expires_in=3600,
                    scope="Mail.Send",
                ),
            )
            monkeypatch.setattr(
                mail_oauth,
                "fetch_own_profile",
                lambda access_token: {
                    "mail": "info@commandeurconsulting.de",
                    "displayName": "Commandeur Consulting GmbH",
                },
            )

            account = mail_oauth.handle_oauth_callback(
                session, code="abc", state=state, redirect_uri="https://example.test/callback"
            )

            assert account.address == "info@commandeurconsulting.de"
            assert account.provider == MailAccountProvider.MICROSOFT_GRAPH
            assert account.oauth_connected_by_user_id == user.id
            assert account.oauth_status == MailAccountOAuthStatus.CONNECTED

    def test_handle_oauth_callback_converts_existing_imap_account_in_place(
        self, session_factory: sessionmaker[Session], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Migrationspfad (M365-Integrationsplan Abschnitt 7): ein bereits
        bestehendes IMAP-Konto derselben Adresse wird umgewandelt statt
        dupliziert - die id bleibt erhalten."""
        with session_factory() as session:
            user = _make_user(session)
            existing = MailAccount(
                address="info@commandeurconsulting.de",
                label="info (IMAP)",
                imap_host="imap.example.com",
                smtp_host="smtp.example.com",
                username="info@commandeurconsulting.de",
                encrypted_password=Fernet(_KEY.encode()).encrypt(b"altes-passwort").decode(),
            )
            session.add(existing)
            session.commit()
            existing_id = existing.id
            state = create_oauth_state(user.id)

            monkeypatch.setattr(
                mail_oauth,
                "exchange_code_for_tokens",
                lambda *, code, redirect_uri, settings=None: GraphTokens(
                    access_token="access-1",
                    refresh_token="refresh-1",
                    expires_in=3600,
                    scope="Mail.Send",
                ),
            )
            monkeypatch.setattr(
                mail_oauth,
                "fetch_own_profile",
                lambda access_token: {
                    "mail": "info@commandeurconsulting.de",
                    "displayName": "Info",
                },
            )

            account = mail_oauth.handle_oauth_callback(
                session, code="abc", state=state, redirect_uri="https://example.test/callback"
            )

            assert account.id == existing_id
            assert account.provider == MailAccountProvider.MICROSOFT_GRAPH
            assert account.imap_host is None
            assert account.encrypted_password is None


class TestMailSendGraphProvider:
    def test_send_mail_uses_graph_and_needs_no_password(
        self, session_factory: sessionmaker[Session], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        sent: dict[str, object] = {}

        monkeypatch.setattr(
            graph_token_service,
            "refresh_access_token",
            lambda *, refresh_token, settings=None: GraphTokens(
                access_token="access-1",
                refresh_token="refresh-1",
                expires_in=3600,
                scope="Mail.Send",
            ),
        )

        import cc_crm.integrations.microsoft_graph.client as graph_client_module

        def fake_send_mail(access_token: str, **kwargs: object) -> None:
            sent["access_token"] = access_token
            sent.update(kwargs)

        monkeypatch.setattr(graph_client_module, "send_mail", fake_send_mail)

        with session_factory() as session:
            user = _make_user(session)
            account = _make_graph_account(session, user_id=user.id)
            record = send_mail(
                session,
                account=account,
                to_address="kandidat@example.com",
                to_name="Max Muster",
                subject="Betreff",
                body_text="Text",
            )
        assert sent["access_token"] == "access-1"
        assert sent["to_address"] == "kandidat@example.com"
        assert record.message_id  # synthetisch erzeugt, siehe mail_send.py::_send_via_graph


class TestMailSyncGraphProvider:
    def test_fetch_mail_dispatches_to_graph_for_graph_accounts(
        self, session_factory: sessionmaker[Session], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(
            graph_token_service,
            "refresh_access_token",
            lambda *, refresh_token, settings=None: GraphTokens(
                access_token="access-1",
                refresh_token="refresh-1",
                expires_in=3600,
                scope="Mail.ReadWrite",
            ),
        )

        import cc_crm.integrations.microsoft_graph.client as graph_client_module
        from cc_crm.integrations.microsoft_graph.client import DeltaMailResult

        def fake_delta(
            access_token: str, *, delta_link: str | None, page_limit: int = 200
        ) -> DeltaMailResult:
            return DeltaMailResult(
                messages=[
                    GraphMessage(
                        internet_message_id="msg-1@example.com",
                        id="graph-msg-1",
                        from_name="Anna Müller",
                        from_address="anna.mueller@example.com",
                        subject="Rückfrage",
                        body_text="Hallo",
                        received_at=datetime(2026, 9, 1, tzinfo=UTC),
                        is_draft=False,
                    )
                ],
                delta_link="delta-token-2",
            )

        monkeypatch.setattr(graph_client_module, "fetch_inbox_delta", fake_delta)

        with session_factory() as session:
            user = _make_user(session)
            account = _make_graph_account(session, user_id=user.id)
            mails = fetch_mail(session, account, None)

        assert len(mails) == 1
        assert mails[0].message_id == "msg-1@example.com"
        assert account.graph_delta_link == "delta-token-2"


class TestCalendarGraphSync:
    def test_sync_pushes_new_crm_event_and_pulls_new_outlook_event_in_one_run(
        self, session_factory: sessionmaker[Session], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Regressionstest fuer den gemeldeten Prod-Vorfall: Push (CRM->Graph)
        funktionierte, Pull (Graph->CRM) nicht. Prueft explizit BEIDE
        Richtungen in einem einzigen sync_account_calendar()-Aufruf, statt
        wie die uebrigen Tests hier nur eine Richtung isoliert."""
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
        from cc_crm.integrations.microsoft_graph.client import DeltaCalendarResult

        create_calls: list[dict[str, object]] = []

        def fake_create_event(access_token: str, **kwargs: object) -> str:
            create_calls.append(kwargs)
            return "graph-evt-pushed"

        outlook_event = GraphEvent(
            id="graph-evt-from-outlook",
            subject="SYNC-TEST Outlook->CRM",
            body_text=None,
            start_at=datetime(2026, 9, 16, 14, 0, tzinfo=UTC),
            end_at=datetime(2026, 9, 16, 14, 30, tzinfo=UTC),
            location=None,
            last_modified_at=datetime(2026, 9, 16, 10, 5, tzinfo=UTC),
        )
        monkeypatch.setattr(calendar_graph_sync, "create_event", fake_create_event)
        monkeypatch.setattr(
            calendar_graph_sync,
            "fetch_calendar_delta",
            lambda access_token, *, delta_link, page_limit=200: DeltaCalendarResult(
                events=[outlook_event], delta_link="cal-delta-1"
            ),
        )

        with session_factory() as session:
            user = _make_user(session)
            account = _make_graph_account(session, user_id=user.id)
            crm_event = CalendarEvent(
                title="SYNC-TEST bitte ignorieren",
                start_at=datetime(2026, 9, 16, 14, 0, tzinfo=UTC),
                end_at=datetime(2026, 9, 16, 14, 30, tzinfo=UTC),
                owner_user_id=user.id,
                created_by_user_id=user.id,
            )
            session.add(crm_event)
            session.commit()
            crm_event_id = crm_event.id

            calendar_graph_sync.sync_account_calendar(session, account)

            # Push: das CRM-eigene Event wurde an Graph geschickt und traegt
            # jetzt dessen Event-ID.
            assert len(create_calls) == 1
            assert create_calls[0]["title"] == "SYNC-TEST bitte ignorieren"
            refreshed_crm_event = session.get(CalendarEvent, crm_event_id)
            assert refreshed_crm_event is not None
            assert refreshed_crm_event.external_graph_event_id == "graph-evt-pushed"

            # Pull: das in Outlook angelegte Event ist jetzt als eigene
            # CalendarEvent-Zeile im CRM vorhanden - der eigentliche Bug.
            pulled_event = session.scalar(
                select(CalendarEvent).where(
                    CalendarEvent.external_graph_event_id == "graph-evt-from-outlook"
                )
            )
            assert pulled_event is not None
            assert pulled_event.title == "SYNC-TEST Outlook->CRM"
            assert pulled_event.owner_user_id == user.id

            all_events = session.scalars(select(CalendarEvent)).all()
            assert len(all_events) == 2

    def test_sync_creates_new_local_event_from_graph_delta(
        self, session_factory: sessionmaker[Session], monkeypatch: pytest.MonkeyPatch
    ) -> None:
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
        from cc_crm.integrations.microsoft_graph.client import DeltaCalendarResult

        graph_event = GraphEvent(
            id="graph-evt-1",
            subject="Interview Max Muster",
            body_text="Notizen",
            start_at=datetime(2026, 9, 20, 10, 0, tzinfo=UTC),
            end_at=datetime(2026, 9, 20, 11, 0, tzinfo=UTC),
            location="Büro",
            last_modified_at=datetime(2026, 9, 15, 8, 0, tzinfo=UTC),
        )
        # calendar_graph_sync importiert fetch_calendar_delta auf Modulebene
        # (anders als mail_sync.py/mail_send.py mit ihren lokalen, lazy
        # Importen) - gepatcht wird deshalb der Name IM Zielmodul, nicht in
        # integrations.microsoft_graph.client selbst.
        monkeypatch.setattr(
            calendar_graph_sync,
            "fetch_calendar_delta",
            lambda access_token, *, delta_link, page_limit=200: DeltaCalendarResult(
                events=[graph_event], delta_link="cal-delta-2"
            ),
        )

        with session_factory() as session:
            user = _make_user(session)
            account = _make_graph_account(session, user_id=user.id)
            calendar_graph_sync.sync_account_calendar(session, account)

            events = session.query(CalendarEvent).all()
            assert len(events) == 1
            assert events[0].title == "Interview Max Muster"
            assert events[0].external_graph_event_id == "graph-evt-1"
            assert events[0].owner_user_id == user.id
            assert account.graph_calendar_delta_link == "cal-delta-2"

    def test_sync_removes_local_event_deleted_on_graph_side(
        self, session_factory: sessionmaker[Session], monkeypatch: pytest.MonkeyPatch
    ) -> None:
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
        from cc_crm.integrations.microsoft_graph.client import DeltaCalendarResult

        with session_factory() as session:
            user = _make_user(session)
            account = _make_graph_account(session, user_id=user.id)
            event = CalendarEvent(
                title="Wird auf Graph geloescht",
                start_at=datetime(2026, 9, 20, 10, 0, tzinfo=UTC),
                owner_user_id=user.id,
                created_by_user_id=user.id,
                external_graph_event_id="graph-evt-2",
                external_graph_last_synced_at=datetime(2026, 9, 1, tzinfo=UTC),
            )
            session.add(event)
            session.commit()

            monkeypatch.setattr(
                calendar_graph_sync,
                "fetch_calendar_delta",
                lambda access_token, *, delta_link, page_limit=200: DeltaCalendarResult(
                    events=[], removed_ids=["graph-evt-2"], delta_link="cal-delta-3"
                ),
            )
            # _push_local_changes wuerde das (noch nicht als neu erkannte)
            # Event sonst per echtem HTTP-Aufruf aktualisieren wollen - hier
            # interessiert nur der Pull-Pfad, deshalb neutral gemacht.
            monkeypatch.setattr(calendar_graph_sync, "update_event", lambda *a, **k: None)

            calendar_graph_sync.sync_account_calendar(session, account)

            remaining = session.query(CalendarEvent).filter(CalendarEvent.id == event.id).first()
            assert remaining is None

    def test_push_delete_to_graph_is_best_effort_and_does_not_raise(
        self, session_factory: sessionmaker[Session], monkeypatch: pytest.MonkeyPatch
    ) -> None:
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
        from cc_crm.integrations.microsoft_graph.client import GraphApiError

        def failing_delete(access_token: str, *, graph_event_id: str) -> None:
            raise GraphApiError("Netzwerkfehler")

        monkeypatch.setattr(calendar_graph_sync, "delete_event", failing_delete)

        with session_factory() as session:
            user = _make_user(session)
            _make_graph_account(session, user_id=user.id)
            event = CalendarEvent(
                title="Termin",
                start_at=datetime(2026, 9, 20, 10, 0, tzinfo=UTC),
                owner_user_id=user.id,
                created_by_user_id=user.id,
                external_graph_event_id="graph-evt-3",
            )
            session.add(event)
            session.commit()

            # Wirft NICHT - best effort (siehe Docstring push_delete_to_graph).
            calendar_graph_sync.push_delete_to_graph(session, event)
