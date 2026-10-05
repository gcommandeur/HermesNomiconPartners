"""Mit Microsoft anmelden verbindet gleichzeitig Postfach und Kalender des Nutzers."""

from __future__ import annotations

import uuid
from collections.abc import Generator
from urllib.parse import parse_qs, urlparse

import pytest
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from cc_crm.core.config import get_settings
from cc_crm.core.security import hash_password
from cc_crm.integrations.microsoft_graph.auth import GraphTokens
from cc_crm.models.enums import MailAccountOAuthStatus, MailAccountProvider
from cc_crm.models.mail import MailAccount
from cc_crm.models.user import User

LOGIN = "/api/v1/auth/microsoft/login"
CALLBACK = "/api/v1/auth/microsoft/callback"
ORIGIN = "http://crm.example"


@pytest.fixture(autouse=True)
def _settings(monkeypatch: pytest.MonkeyPatch) -> Generator[None, None, None]:
    get_settings.cache_clear()
    monkeypatch.setenv("CC_CRM_MAIL_CREDENTIALS_ENCRYPTION_KEY", Fernet.generate_key().decode())
    monkeypatch.setenv("CC_CRM_MS_GRAPH_CLIENT_ID", "client-id")
    monkeypatch.setenv("CC_CRM_MS_GRAPH_TENANT_ID", "tenant-id")
    monkeypatch.setenv("CC_CRM_MS_GRAPH_CLIENT_SECRET", "secret")
    monkeypatch.setenv("CC_CRM_CORS_ORIGINS", f'["{ORIGIN}"]')
    yield
    get_settings.cache_clear()


@pytest.fixture
def microsoft(monkeypatch: pytest.MonkeyPatch) -> dict[str, dict[str, str]]:
    state: dict[str, dict[str, str]] = {
        "profile": {"id": "oid-sso-1", "mail": "sso@example.com", "displayName": "SSO Nutzerin"}
    }
    monkeypatch.setattr(
        "cc_crm.services.microsoft_login.exchange_code_for_login_tokens",
        lambda *, code, redirect_uri: GraphTokens(
            access_token="access-1",
            refresh_token="refresh-1",
            expires_in=3600,
            scope="Mail.Send Calendars.ReadWrite",
        ),
    )
    monkeypatch.setattr(
        "cc_crm.services.microsoft_login.fetch_own_profile", lambda token: state["profile"]
    )
    return state


def _add_user(session_factory: sessionmaker[Session], email: str = "sso@example.com") -> str:
    with session_factory() as session:
        user = User(email=email, hashed_password=hash_password("pw"), display_name="SSO")
        session.add(user)
        session.commit()
        return str(user.id)


def _login(client: TestClient) -> None:
    if "authorization" in client.headers:
        del client.headers["authorization"]
    start = client.get(LOGIN, follow_redirects=False)
    query = parse_qs(urlparse(start.headers["location"]).query)
    response = client.get(
        CALLBACK, params={"code": "abc", "state": query["state"][0]}, follow_redirects=False
    )
    assert response.headers["location"] == f"{ORIGIN}/sso-complete", response.headers["location"]


def test_login_asks_for_mailbox_and_calendar_scopes(client: TestClient) -> None:
    if "authorization" in client.headers:
        del client.headers["authorization"]
    response = client.get(LOGIN, follow_redirects=False)
    scopes = parse_qs(urlparse(response.headers["location"]).query)["scope"][0].split()
    assert {"offline_access", "Mail.Send", "Calendars.ReadWrite"} <= set(scopes)


def test_login_connects_own_mailbox_and_makes_it_the_default_sender(
    client: TestClient,
    session_factory: sessionmaker[Session],
    microsoft: dict[str, dict[str, str]],
) -> None:
    user_id = _add_user(session_factory)
    _login(client)
    with session_factory() as session:
        account = session.scalars(select(MailAccount)).one()
        user = session.scalars(select(User).where(User.email == "sso@example.com")).one()
        assert account.address == "sso@example.com"
        assert account.provider == MailAccountProvider.MICROSOFT_GRAPH
        assert account.oauth_status == MailAccountOAuthStatus.CONNECTED
        assert str(account.oauth_connected_by_user_id) == user_id
        assert account.encrypted_oauth_refresh_token
        assert "refresh-1" not in account.encrypted_oauth_refresh_token  # verschluesselt
        assert user.default_send_account_id == account.id

    token = client.cookies.get("cc_crm_token")
    status = client.get("/api/v1/me/outlook", headers={"Authorization": f"Bearer {token}"})
    assert status.json() == {"state": "connected", "address": "sso@example.com"}


def test_login_does_not_take_over_a_mailbox_connected_by_someone_else(
    client: TestClient,
    session_factory: sessionmaker[Session],
    microsoft: dict[str, dict[str, str]],
) -> None:
    _add_user(session_factory)
    other_id = _add_user(session_factory, "other@example.com")
    with session_factory() as session:
        session.add(
            MailAccount(
                address="sso@example.com",
                label="Geteilt",
                provider=MailAccountProvider.MICROSOFT_GRAPH,
                oauth_status=MailAccountOAuthStatus.CONNECTED,
                oauth_connected_by_user_id=uuid.UUID(other_id),
            )
        )
        session.commit()
    _login(client)  # Anmeldung klappt trotzdem
    with session_factory() as session:
        account = session.scalars(select(MailAccount)).one()
        assert str(account.oauth_connected_by_user_id) == other_id


def test_failing_mailbox_connection_never_blocks_the_login(
    client: TestClient,
    session_factory: sessionmaker[Session],
    microsoft: dict[str, dict[str, str]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def boom(*args: object, **kwargs: object) -> None:
        raise RuntimeError("kaputt")

    monkeypatch.setattr("cc_crm.services.microsoft_login.store_connection", boom)
    _add_user(session_factory)
    _login(client)
    with session_factory() as session:
        assert session.scalars(select(MailAccount)).all() == []


def test_user_can_see_and_disconnect_only_their_own_connection(
    client: TestClient,
    session_factory: sessionmaker[Session],
    microsoft: dict[str, dict[str, str]],
) -> None:
    _add_user(session_factory)
    _login(client)
    token = client.cookies.get("cc_crm_token")
    headers = {"Authorization": f"Bearer {token}"}

    assert client.post("/api/v1/me/outlook/disconnect", headers=headers).status_code == 204
    assert client.get("/api/v1/me/outlook", headers=headers).json() == {
        "state": "not_connected",
        "address": None,
    }
    with session_factory() as session:
        account = session.scalars(select(MailAccount)).one()
        user = session.scalars(select(User).where(User.email == "sso@example.com")).one()
        assert account.encrypted_oauth_refresh_token is None
        assert account.is_active is False
        assert user.default_send_account_id is None

    # Ohne Verbindung gibt es nichts zu trennen - kein Fehler.
    assert client.post("/api/v1/me/outlook/disconnect", headers=headers).status_code == 204
