"""Anmelden mit Microsoft (api/v1/microsoft_login.py, services/microsoft_login.py).

Der HTTP-Verkehr zu Microsoft ist in den Tests ersetzt (Code-Tausch und /me) -
es wird nichts nach aussen gesendet. `client` haengt standardmaessig einen
Bearer-Token an; die Tests entfernen ihn fuer die Aufrufe, die Microsofts
Redirect nachstellen (kein Header, wie im echten Ablauf)."""

from __future__ import annotations

from collections.abc import Generator
from urllib.parse import parse_qs, unquote, urlparse

import pytest
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

from cc_crm.core.config import get_settings
from cc_crm.core.security import hash_password
from cc_crm.integrations.microsoft_graph.oauth_state import create_oauth_state
from cc_crm.models.auth import AuthSession
from cc_crm.models.user import User

LOGIN = "/api/v1/auth/microsoft/login"
CALLBACK = "/api/v1/auth/microsoft/callback"
ORIGIN = "http://crm.example"
# Das `client`-Fixture meldet den Testnutzer an und legt dabei genau eine
# Session an - jede weitere waere durch den SSO-Flow entstanden.
FIXTURE_SESSIONS = 1


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
    """Fake-Microsoft: `profile` ist die Antwort von GET /me."""
    state: dict[str, dict[str, str]] = {"profile": {"mail": "sso@example.com"}}
    monkeypatch.setattr(
        "cc_crm.services.microsoft_login.exchange_code_for_login",
        lambda *, code, redirect_uri: "fake-access-token",
    )
    monkeypatch.setattr(
        "cc_crm.services.microsoft_login.fetch_own_profile", lambda token: state["profile"]
    )
    return state


def _anonymous(client: TestClient) -> TestClient:
    if "authorization" in client.headers:
        del client.headers["authorization"]
    return client


def _add_user(
    session_factory: sessionmaker[Session], email: str = "sso@example.com", *, active: bool = True
) -> None:
    with session_factory() as session:
        session.add(
            User(
                email=email,
                hashed_password=hash_password("pw"),
                display_name="SSO Nutzerin",
                is_active=active,
            )
        )
        session.commit()


def _start(client: TestClient) -> str:
    """Startet den Flow und liefert den `state` aus der Microsoft-URL; die
    nonce landet im Cookie-Jar des Clients."""
    response = client.get(LOGIN, follow_redirects=False)
    assert response.status_code == 307 or response.status_code == 302, response.text
    query = parse_qs(urlparse(response.headers["location"]).query)
    return query["state"][0]


def _count(session_factory: sessionmaker[Session], model: type) -> int:
    with session_factory() as session:
        return session.scalar(select(func.count()).select_from(model)) or 0


def test_login_redirects_to_microsoft_with_lean_scopes_and_nonce_cookie(
    client: TestClient,
) -> None:
    _anonymous(client)
    response = client.get(LOGIN, follow_redirects=False)
    assert response.status_code in (302, 307)
    url = urlparse(response.headers["location"])
    assert url.netloc == "login.microsoftonline.com"
    assert url.path == "/tenant-id/oauth2/v2.0/authorize"
    query = parse_qs(url.query)
    assert query["scope"] == ["openid profile email User.Read"]  # keine Mailbox-Scopes
    assert query["redirect_uri"] == [f"{ORIGIN}/api/v1/auth/microsoft/callback"]
    assert query["client_id"] == ["client-id"]
    assert query["state"][0]
    cookie = response.headers["set-cookie"].lower()
    assert "cc_crm_ms_login=" in cookie and "httponly" in cookie and "samesite=lax" in cookie


def test_login_without_configuration_redirects_with_error(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("CC_CRM_MS_GRAPH_CLIENT_SECRET")
    get_settings.cache_clear()
    _anonymous(client)
    response = client.get(LOGIN, follow_redirects=False)
    assert response.headers["location"].startswith(f"{ORIGIN}/login?error=")
    assert not client.cookies.get("cc_crm_ms_login")


def test_successful_login_issues_a_session_for_the_matching_user(
    client: TestClient,
    session_factory: sessionmaker[Session],
    microsoft: dict[str, dict[str, str]],
) -> None:
    _add_user(session_factory)
    _anonymous(client)
    state = _start(client)
    response = client.get(CALLBACK, params={"code": "abc", "state": state}, follow_redirects=False)
    assert response.status_code in (302, 307)
    assert response.headers["location"] == f"{ORIGIN}/sso-complete"
    cookie_header = " ".join(response.headers.get_list("set-cookie")).lower()
    assert "cc_crm_token=" in cookie_header
    assert "httponly" in cookie_header and "samesite=lax" in cookie_header
    assert "max-age=86400" in cookie_header
    token = client.cookies.get("cc_crm_token")
    assert token
    me = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert me.status_code == 200, me.text
    assert me.json()["email"] == "sso@example.com"
    assert me.json()["display_name"] == "SSO Nutzerin"


def test_login_matches_case_insensitively_and_falls_back_to_upn(
    client: TestClient,
    session_factory: sessionmaker[Session],
    microsoft: dict[str, dict[str, str]],
) -> None:
    _add_user(session_factory)
    microsoft["profile"] = {"mail": None, "userPrincipalName": "SSO@Example.com"}  # type: ignore[dict-item]
    _anonymous(client)
    state = _start(client)
    response = client.get(CALLBACK, params={"code": "abc", "state": state}, follow_redirects=False)
    assert response.headers["location"] == f"{ORIGIN}/sso-complete"


def test_unknown_email_gets_a_clear_error_and_no_account_or_session(
    client: TestClient,
    session_factory: sessionmaker[Session],
    microsoft: dict[str, dict[str, str]],
) -> None:
    microsoft["profile"] = {"mail": "fremd@example.com"}
    users_before = _count(session_factory, User)
    _anonymous(client)
    state = _start(client)
    response = client.get(CALLBACK, params={"code": "abc", "state": state}, follow_redirects=False)
    location = response.headers["location"]
    assert location.startswith(f"{ORIGIN}/login?error=")
    assert "Kein Konto für diese E-Mail-Adresse" in unquote(location)
    assert "cc_crm_token" not in " ".join(response.headers.get_list("set-cookie"))
    assert _count(session_factory, User) == users_before  # nichts automatisch angelegt
    assert _count(session_factory, AuthSession) == FIXTURE_SESSIONS


def test_inactive_user_cannot_log_in_and_gets_the_same_message(
    client: TestClient,
    session_factory: sessionmaker[Session],
    microsoft: dict[str, dict[str, str]],
) -> None:
    _add_user(session_factory, active=False)
    _anonymous(client)
    state = _start(client)
    response = client.get(CALLBACK, params={"code": "abc", "state": state}, follow_redirects=False)
    assert "Kein Konto für diese E-Mail-Adresse" in unquote(response.headers["location"])
    assert "cc_crm_token" not in " ".join(response.headers.get_list("set-cookie"))
    assert _count(session_factory, AuthSession) == FIXTURE_SESSIONS


class TestCsrfProtection:
    def _assert_rejected(
        self, response, session_factory: sessionmaker[Session]  # noqa: ANN001
    ) -> None:
        assert response.headers["location"].startswith(f"{ORIGIN}/login?error=")
        assert "cc_crm_token" not in " ".join(response.headers.get_list("set-cookie"))
        assert _count(session_factory, AuthSession) == FIXTURE_SESSIONS

    def test_callback_without_the_browser_cookie_is_rejected(
        self,
        client: TestClient,
        session_factory: sessionmaker[Session],
        microsoft: dict[str, dict[str, str]],
    ) -> None:
        """Angreifer-Szenario: gueltiger state/code des Angreifers im Browser
        des Opfers - dieser hat die nonce nie als Cookie bekommen."""
        _add_user(session_factory)
        _anonymous(client)
        state = _start(client)
        client.cookies.clear()  # anderer Browser
        response = client.get(
            CALLBACK, params={"code": "abc", "state": state}, follow_redirects=False
        )
        self._assert_rejected(response, session_factory)

    def test_state_from_another_login_start_is_rejected(
        self,
        client: TestClient,
        session_factory: sessionmaker[Session],
        microsoft: dict[str, dict[str, str]],
    ) -> None:
        _add_user(session_factory)
        _anonymous(client)
        attacker_state = _start(client)
        client.cookies.clear()
        _start(client)  # Opfer-Browser startet seinen eigenen Flow (andere nonce)
        response = client.get(
            CALLBACK, params={"code": "abc", "state": attacker_state}, follow_redirects=False
        )
        self._assert_rejected(response, session_factory)

    @pytest.mark.parametrize("bad_state", ["", "kaputt", "gAAAAA-nicht-gueltig"])
    def test_tampered_or_missing_state_is_rejected(
        self,
        client: TestClient,
        session_factory: sessionmaker[Session],
        microsoft: dict[str, dict[str, str]],
        bad_state: str,
    ) -> None:
        _add_user(session_factory)
        _anonymous(client)
        _start(client)
        params = {"code": "abc", "state": bad_state} if bad_state else {"code": "abc"}
        response = client.get(CALLBACK, params=params, follow_redirects=False)
        self._assert_rejected(response, session_factory)

    def test_mailbox_connect_state_cannot_be_used_for_login(
        self,
        client: TestClient,
        session_factory: sessionmaker[Session],
        microsoft: dict[str, dict[str, str]],
    ) -> None:
        import uuid

        _add_user(session_factory)
        _anonymous(client)
        _start(client)
        response = client.get(
            CALLBACK,
            params={"code": "abc", "state": create_oauth_state(uuid.uuid4())},
            follow_redirects=False,
        )
        self._assert_rejected(response, session_factory)

    def test_microsoft_error_response_is_shown_without_a_session(
        self, client: TestClient, session_factory: sessionmaker[Session]
    ) -> None:
        _anonymous(client)
        response = client.get(
            CALLBACK,
            params={"error": "access_denied", "error_description": "Abgebrochen"},
            follow_redirects=False,
        )
        assert "Abgebrochen" in unquote(response.headers["location"])
        assert _count(session_factory, AuthSession) == FIXTURE_SESSIONS


def test_microsoft_login_is_public_and_password_login_still_works(
    client: TestClient, session_factory: sessionmaker[Session]
) -> None:
    """Regression: die neuen Routen verlangen keinen Bearer-Token, und der
    bestehende Passwort-Login (Schritt 1 von E-Mail+Passwort+2FA) laeuft
    unveraendert weiter."""
    _anonymous(client)
    assert client.get(LOGIN, follow_redirects=False).status_code != 401
    _add_user(session_factory, "pw@example.com")
    wrong = client.post("/api/v1/auth/login", json={"email": "pw@example.com", "password": "x"})
    assert wrong.status_code == 401


def test_login_state_cannot_be_used_to_connect_a_mailbox() -> None:
    """Gegenrichtung: ein Login-State darf den Postfach-Connect nicht
    freischalten (dort wird eine Nutzer-ID erwartet)."""
    from cc_crm.integrations.microsoft_graph.oauth_state import (
        InvalidOAuthStateError,
        create_login_state,
        verify_login_state,
        verify_oauth_state,
    )

    state = create_login_state("irgendeine-nonce")
    assert verify_login_state(state) == "irgendeine-nonce"
    with pytest.raises(InvalidOAuthStateError):
        verify_oauth_state(state)
    with pytest.raises(InvalidOAuthStateError):
        verify_login_state(create_oauth_state(__import__("uuid").uuid4()))
