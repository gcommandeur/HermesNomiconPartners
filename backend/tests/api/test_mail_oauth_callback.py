"""Regressionstest fuer den Prod-Vorfall nach Deploy von baabf41: Microsoft
leitet den Browser nach dem Login/Consent DIREKT auf `GET /mail-accounts/
oauth/callback` zurueck, ohne Authorization-Header (kein Umweg ueber den
Next.js-Proxy, kein CRM-Login-Cookie im Spiel - siehe integrations/
microsoft_graph/oauth_state.py). Die Route lag zunaechst faelschlich im
`protected_router` (siehe api/v1/router.py), der global `Depends(
get_current_user)` erzwingt - jeder echte Microsoft-Redirect scheiterte
deshalb sofort mit 401 "Missing bearer token", bevor state/code ueberhaupt
ausgewertet wurden. Fix: eigener `public_router` ohne die Bearer-Pflicht,
Absicherung ausschliesslich ueber den signierten `state`-Parameter.

`client` (siehe conftest.py) haengt standardmaessig einen gueltigen Bearer-
Token an jeden Request - die Tests hier entfernen ihn deshalb bewusst, um
exakt Microsofts Redirect (kein Header) nachzustellen."""

from __future__ import annotations

import uuid

import pytest
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session, sessionmaker

from cc_crm.core.config import get_settings
from cc_crm.integrations.microsoft_graph.auth import GraphTokens
from cc_crm.models.mail import MailAccount
from cc_crm.models.user import User

_KEY = Fernet.generate_key().decode()


@pytest.fixture(autouse=True)
def _encryption_key(monkeypatch: pytest.MonkeyPatch) -> None:
    get_settings.cache_clear()
    monkeypatch.setenv("CC_CRM_MAIL_CREDENTIALS_ENCRYPTION_KEY", _KEY)
    yield
    get_settings.cache_clear()


def _without_auth_header(client: TestClient) -> TestClient:
    """Entfernt den vom `client`-Fixture gesetzten Bearer-Token - simuliert
    exakt Microsofts direkten Redirect ohne Authorization-Header."""
    if "authorization" in client.headers:
        del client.headers["authorization"]
    return client


def test_callback_does_not_require_a_bearer_token(client: TestClient) -> None:
    """Der eigentliche Bug: ohne diesen Fix antwortete dieser Aufruf mit 401
    "Missing bearer token or X-API-Key header", statt state/code
    ueberhaupt erst auszuwerten."""
    _without_auth_header(client)
    response = client.get(
        "/api/v1/mail-accounts/oauth/callback",
        params={"state": "irrelevant-fuer-diesen-test", "code": "irrelevant"},
        follow_redirects=False,
    )
    assert response.status_code != 401, response.text
    # Ungueltiger state -> Redirect zurueck ins Frontend mit ms_error, kein
    # 401/403/500.
    assert response.status_code in (302, 307)
    assert "ms_error" in response.headers["location"]


def test_callback_redirects_with_ms_error_for_a_microsoft_error_response(
    client: TestClient,
) -> None:
    """Microsoft haengt bei einem abgelehnten Consent `error=access_denied`
    statt `code` an den Redirect - auch das darf keine 401/500 sein."""
    _without_auth_header(client)
    response = client.get(
        "/api/v1/mail-accounts/oauth/callback",
        params={"error": "access_denied", "error_description": "Nutzer hat abgelehnt"},
        follow_redirects=False,
    )
    assert response.status_code in (302, 307)
    assert "ms_error" in response.headers["location"]


def test_full_flow_start_then_callback_without_bearer_token_creates_account(
    client: TestClient,
    session_factory: sessionmaker[Session],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Vollstaendiger Ablauf: /oauth/start (authentifiziert, liefert die
    Autorisierungs-URL samt state) -> /oauth/callback (KEIN Auth-Header,
    genau wie Microsofts echter Redirect) mit dem daraus extrahierten state
    und einem Fake-Code (Microsoft-Codes sind Single-Use/kurzlebig, ein
    echter Code aus einer Support-Reproduktion waere sofort verbraucht) -
    Graph-Token-Tausch und -Profilabruf werden gemockt."""
    with session_factory() as session:
        user = session.query(User).one()
        user.role = "admin"
        session.commit()

    monkeypatch.setenv("CC_CRM_MS_GRAPH_CLIENT_ID", "client-1")
    monkeypatch.setenv("CC_CRM_MS_GRAPH_TENANT_ID", "tenant-1")
    monkeypatch.setenv("CC_CRM_MS_GRAPH_CLIENT_SECRET", "secret-1")
    get_settings.cache_clear()

    start_response = client.get("/api/v1/mail-accounts/oauth/start")
    assert start_response.status_code == 200, start_response.text
    authorization_url = start_response.json()["authorization_url"]
    assert "login.microsoftonline.com/tenant-1" in authorization_url
    from urllib.parse import parse_qs, urlparse

    state = parse_qs(urlparse(authorization_url).query)["state"][0]

    import cc_crm.services.mail_oauth as mail_oauth_module

    monkeypatch.setattr(
        mail_oauth_module,
        "exchange_code_for_tokens",
        lambda *, code, redirect_uri, settings=None: GraphTokens(
            access_token="access-1",
            refresh_token="refresh-1",
            expires_in=3600,
            scope="Mail.Send",
        ),
    )
    monkeypatch.setattr(
        mail_oauth_module,
        "fetch_own_profile",
        lambda access_token: {
            "mail": "info@commandeurconsulting.de",
            "displayName": "Commandeur Consulting GmbH",
        },
    )

    _without_auth_header(client)
    callback_response = client.get(
        "/api/v1/mail-accounts/oauth/callback",
        params={"code": "fake-microsoft-code", "state": state},
        follow_redirects=False,
    )
    assert callback_response.status_code in (302, 307)
    assert "ms_connected=info@commandeurconsulting.de" in callback_response.headers["location"]

    with session_factory() as session:
        account = session.query(MailAccount).filter_by(address="info@commandeurconsulting.de").one()
        assert account.provider == "microsoft_graph"
        assert account.oauth_status == "connected"
        assert account.id is not None
        assert isinstance(account.id, uuid.UUID)
