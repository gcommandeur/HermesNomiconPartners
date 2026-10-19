# ruff: noqa: F811
"""Hermes als OAuth-Anbieter fuer Claude: Registrierung, PKCE, Zustimmung, Token,
Bindung an den Nutzer, Entzug."""

from __future__ import annotations

import base64
import hashlib
import secrets
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from urllib.parse import parse_qs, urlparse

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from cc_crm.core.config import get_settings
from cc_crm.models.ai_proposal import AiProposal
from cc_crm.models.oauth import OAuthToken
from cc_crm.models.user import User
from tests.api.test_team_lead import Team, team  # noqa: F401

ORIGIN = "http://crm.example"
BASE = "/api/v1"
CALLBACK = "https://claude.ai/api/mcp/auth_callback"


@pytest.fixture
def ai_on(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    monkeypatch.setenv("CC_CRM_AI_ENABLED", "true")
    monkeypatch.setenv("CC_CRM_CORS_ORIGINS", f'["{ORIGIN}"]')
    get_settings.cache_clear()
    yield
    monkeypatch.delenv("CC_CRM_AI_ENABLED", raising=False)
    get_settings.cache_clear()


def _pkce() -> tuple[str, str]:
    verifier = secrets.token_urlsafe(48)
    digest = hashlib.sha256(verifier.encode()).digest()
    return verifier, base64.urlsafe_b64encode(digest).rstrip(b"=").decode()


def _register(client: TestClient, redirect_uri: str = CALLBACK) -> str:
    response = client.post(
        f"{BASE}/oauth/register",
        json={"client_name": "Claude", "redirect_uris": [redirect_uri]},
    )
    assert response.status_code == 201, response.text
    return response.json()["client_id"]


def _authorize(client: TestClient, client_id: str, challenge: str, **over: str) -> str:
    """Startet /authorize wie Claude (ohne Hermes-Login) und liefert die Anfrage-ID."""
    params = {
        "client_id": client_id,
        "redirect_uri": CALLBACK,
        "response_type": "code",
        "code_challenge": challenge,
        "code_challenge_method": "S256",
        "state": "xyz",
        **over,
    }
    response = client.get(f"{BASE}/oauth/authorize", params=params, follow_redirects=False)
    assert response.status_code in (302, 307), response.text
    location = urlparse(response.headers["location"])
    assert f"{location.scheme}://{location.netloc}{location.path}" == f"{ORIGIN}/oauth/zustimmung"
    return parse_qs(location.query)["request"][0]


def _approve(client: TestClient, headers: dict[str, str], request_id: str, approve: bool = True):
    return client.post(
        f"{BASE}/oauth/consent",
        json={"request_id": request_id, "approve": approve},
        headers=headers,
    )


def _token(client: TestClient, **form: str):
    return client.post(f"{BASE}/oauth/token", data=form)


def _connect(client: TestClient, headers: dict[str, str]) -> dict:
    """Voller Ablauf; liefert die Token-Antwort."""
    client_id = _register(client)
    verifier, challenge = _pkce()
    request_id = _authorize(client, client_id, challenge)
    decision = _approve(client, headers, request_id)
    assert decision.status_code == 200, decision.text
    redirect = urlparse(decision.json()["redirect_url"])
    assert f"{redirect.scheme}://{redirect.netloc}{redirect.path}" == CALLBACK
    query = parse_qs(redirect.query)
    assert query["state"] == ["xyz"]
    response = _token(
        client,
        grant_type="authorization_code",
        client_id=client_id,
        code=query["code"][0],
        redirect_uri=CALLBACK,
        code_verifier=verifier,
    )
    assert response.status_code == 200, response.text
    body = response.json()
    body["client_id"] = client_id
    return body


def _mcp(client: TestClient, access: str, method: str = "tools/list", **params):
    return client.post(
        f"{BASE}/mcp",
        json={"jsonrpc": "2.0", "id": 1, "method": method, "params": params},
        headers={"Authorization": f"Bearer {access}"},
    )


def test_everything_is_off_by_default(client: TestClient) -> None:
    for path in (
        "/oauth/protected-resource",
        "/oauth/.well-known/openid-configuration",
        "/oauth/.well-known/oauth-authorization-server",
    ):
        assert client.get(f"{BASE}{path}").status_code == 404, path
    assert client.post(f"{BASE}/oauth/register", json={}).status_code == 404
    assert (
        client.post(f"{BASE}/oauth/token", data={"grant_type": "x", "client_id": "y"}).status_code
        == 404
    )


def test_unauthenticated_mcp_call_points_to_the_metadata(client: TestClient, ai_on: None) -> None:
    response = client.post(f"{BASE}/mcp", json={"jsonrpc": "2.0", "id": 1, "method": "ping"})
    assert response.status_code == 401
    assert response.headers["www-authenticate"] == (
        f'Bearer resource_metadata="{ORIGIN}{BASE}/oauth/protected-resource"'
    )
    resource = client.get(f"{BASE}/oauth/protected-resource").json()
    assert resource["resource"] == f"{ORIGIN}{BASE}/mcp"
    assert resource["authorization_servers"] == [f"{ORIGIN}{BASE}/oauth"]
    for path in ("openid-configuration", "oauth-authorization-server"):
        meta = client.get(f"{BASE}/oauth/.well-known/{path}").json()
        assert meta["issuer"] == f"{ORIGIN}{BASE}/oauth"
        assert meta["code_challenge_methods_supported"] == ["S256"]
        assert meta["token_endpoint_auth_methods_supported"] == ["none"]
        assert meta["registration_endpoint"].endswith("/oauth/register")
        assert "refresh_token" in meta["grant_types_supported"]


def test_registration_only_accepts_claude_callbacks(client: TestClient, ai_on: None) -> None:
    for bad in (
        "https://evil.example/cb",
        "http://claude.ai/api/mcp/auth_callback",
        "https://claude.ai.evil.example/api/mcp/auth_callback",
        "javascript:alert(1)",
    ):
        response = client.post(f"{BASE}/oauth/register", json={"redirect_uris": [bad]})
        assert response.status_code == 400, bad
        assert response.json()["error"] == "invalid_redirect_uri"
    assert client.post(f"{BASE}/oauth/register", json={"redirect_uris": []}).status_code == 400
    # Claude Code: Loopback mit beliebigem Port.
    assert _register(client, "http://localhost:3118/callback")
    assert _register(client, "http://127.0.0.1:5555/callback")


def test_authorize_rejects_bad_requests(client: TestClient, ai_on: None) -> None:
    client_id = _register(client)
    _, challenge = _pkce()
    base = {"client_id": client_id, "redirect_uri": CALLBACK, "code_challenge": challenge}
    url = f"{BASE}/oauth/authorize"
    assert (
        client.get(
            url, params={**base, "redirect_uri": "https://evil.example/cb"}, follow_redirects=False
        ).status_code
        == 400
    )
    assert (
        client.get(
            url, params={**base, "code_challenge_method": "plain"}, follow_redirects=False
        ).status_code
        == 400
    )
    assert (
        client.get(
            url, params={**base, "code_challenge": "kurz"}, follow_redirects=False
        ).status_code
        == 400
    )
    assert (
        client.get(
            url, params={**base, "client_id": "unbekannt"}, follow_redirects=False
        ).status_code
        == 400
    )
    assert (
        client.get(
            url, params={**base, "response_type": "token"}, follow_redirects=False
        ).status_code
        == 400
    )


def test_full_flow_binds_the_token_to_the_user_and_works_only_on_mcp(
    client: TestClient, team: Team, session_factory, ai_on: None
) -> None:
    tokens = _connect(client, team.a.headers)
    assert tokens["token_type"] == "Bearer" and tokens["scope"] == "mcp"
    assert tokens["access_token"].startswith("hmo_") and tokens["refresh_token"].startswith("hmr_")

    names = {t["name"] for t in _mcp(client, tokens["access_token"]).json()["result"]["tools"]}
    assert {"search_candidates", "propose_note"} <= names

    # Nur /mcp: auf der uebrigen API ist das Token wertlos.
    bearer = {"Authorization": f"Bearer {tokens['access_token']}"}
    for path in ("/candidates", "/auth/me", "/ai-proposals"):
        assert client.get(f"{BASE}{path}", headers=bearer).status_code == 401, path

    # Eine Browser-Sitzung ist umgekehrt kein MCP-Zugang.
    assert (
        client.post(
            f"{BASE}/mcp",
            json={"jsonrpc": "2.0", "id": 1, "method": "ping"},
            headers=team.a.headers,
        ).status_code
        == 401
    )

    # Die Werkzeuge laufen als der Nutzer (Vorschlag gehoert Nutzerin A).
    candidate = client.post(
        f"{BASE}/candidates", json={"first_name": "K", "last_name": "L"}, headers=team.a.headers
    ).json()
    result = _mcp(
        client,
        tokens["access_token"],
        "tools/call",
        name="propose_note",
        arguments={"candidate_id": candidate["id"], "text": "Hallo"},
    )
    assert result.status_code == 200
    with session_factory() as session:
        proposal = session.scalars(select(AiProposal)).one()
        assert str(proposal.created_by_user_id) == team.a.id
        stored = session.scalars(select(OAuthToken)).one()
        assert str(stored.user_id) == team.a.id
        assert tokens["access_token"] not in (stored.access_hash, stored.refresh_hash)  # nur Hashes
        assert stored.last_used_at is not None


def test_wrong_pkce_verifier_and_code_reuse_are_refused(
    client: TestClient, team: Team, ai_on: None
) -> None:
    client_id = _register(client)
    verifier, challenge = _pkce()
    request_id = _authorize(client, client_id, challenge)
    code = parse_qs(
        urlparse(_approve(client, team.a.headers, request_id).json()["redirect_url"]).query
    )["code"][0]
    form = {
        "grant_type": "authorization_code",
        "client_id": client_id,
        "code": code,
        "redirect_uri": CALLBACK,
    }

    wrong = _token(client, **form, code_verifier=_pkce()[0])
    assert wrong.status_code == 400 and wrong.json()["error"] == "invalid_grant"
    other_redirect = _token(
        client,
        **{**form, "redirect_uri": "https://claude.com/api/mcp/auth_callback"},
        code_verifier=verifier,
    )
    assert other_redirect.status_code == 400
    ok = _token(client, **form, code_verifier=verifier)
    assert ok.status_code == 200
    access = ok.json()["access_token"]
    assert _mcp(client, access).status_code == 200

    # Zweiter Tausch desselben Codes: abgelehnt UND die daraus entstandenen Tokens sind tot.
    again = _token(client, **form, code_verifier=verifier)
    assert again.status_code == 400 and again.json()["error"] == "invalid_grant"
    assert _mcp(client, access).status_code == 401


def test_refresh_rotates_and_old_refresh_token_dies(
    client: TestClient, team: Team, ai_on: None
) -> None:
    tokens = _connect(client, team.a.headers)
    response = _token(
        client,
        grant_type="refresh_token",
        client_id=tokens["client_id"],
        refresh_token=tokens["refresh_token"],
    )
    assert response.status_code == 200, response.text
    new = response.json()
    assert new["refresh_token"] != tokens["refresh_token"]
    assert _mcp(client, new["access_token"]).status_code == 200
    assert _mcp(client, tokens["access_token"]).status_code == 401  # alter Zugang ersetzt
    old = _token(
        client,
        grant_type="refresh_token",
        client_id=tokens["client_id"],
        refresh_token=tokens["refresh_token"],
    )
    assert old.status_code == 400 and old.json()["error"] == "invalid_grant"
    other_client = _register(client)
    foreign = _token(
        client,
        grant_type="refresh_token",
        client_id=other_client,
        refresh_token=new["refresh_token"],
    )
    assert foreign.status_code == 400


def test_denied_consent_and_expired_requests(
    client: TestClient, team: Team, session_factory, ai_on: None
) -> None:
    client_id = _register(client)
    _, challenge = _pkce()
    request_id = _authorize(client, client_id, challenge)
    denied = _approve(client, team.a.headers, request_id, approve=False).json()["redirect_url"]
    query = parse_qs(urlparse(denied).query)
    assert query["error"] == ["access_denied"] and query["state"] == ["xyz"] and "code" not in query
    assert _approve(client, team.a.headers, request_id).status_code == 404  # Anfrage verbraucht

    expired_id = _authorize(client, client_id, challenge)
    from cc_crm.models.oauth import OAuthAuthorization

    with session_factory() as session:
        row = session.get(OAuthAuthorization, __import__("uuid").UUID(expired_id))
        row.expires_at = datetime.now(UTC) - timedelta(minutes=1)
        session.commit()
    assert _approve(client, team.a.headers, expired_id).status_code == 404
    # Zustimmung erfordert den Hermes-Login.
    fresh = _authorize(client, client_id, challenge)
    assert (
        client.post(
            f"{BASE}/oauth/consent",
            json={"request_id": fresh, "approve": True},
            headers={"Authorization": "Bearer ungueltig"},
        ).status_code
        == 401
    )
    info = client.get(f"{BASE}/oauth/consent/{fresh}", headers=team.a.headers).json()
    assert info["client_name"] == "Claude" and info["redirect_host"] == "claude.ai"
    assert info["user_email"]


def test_expired_access_token_and_deactivated_user_are_refused(
    client: TestClient, team: Team, session_factory, ai_on: None
) -> None:
    tokens = _connect(client, team.a.headers)
    with session_factory() as session:
        token = session.scalars(select(OAuthToken)).one()
        token.access_expires_at = datetime.now(UTC) - timedelta(minutes=1)
        session.commit()
    assert _mcp(client, tokens["access_token"]).status_code == 401
    refreshed = _token(
        client,
        grant_type="refresh_token",
        client_id=tokens["client_id"],
        refresh_token=tokens["refresh_token"],
    ).json()
    assert _mcp(client, refreshed["access_token"]).status_code == 200

    with session_factory() as session:  # Entzug bei Deaktivierung
        session.get(User, __import__("uuid").UUID(team.a.id)).is_active = False
        session.commit()
    assert _mcp(client, refreshed["access_token"]).status_code == 401
    assert (
        _token(
            client,
            grant_type="refresh_token",
            client_id=tokens["client_id"],
            refresh_token=refreshed["refresh_token"],
        ).status_code
        == 400
    )


def test_user_can_list_and_revoke_own_connections_only(
    client: TestClient, team: Team, ai_on: None
) -> None:
    mine = _connect(client, team.a.headers)
    _connect(client, team.c.headers)
    listing = client.get(f"{BASE}/oauth/connections", headers=team.a.headers).json()
    assert len(listing) == 1 and listing[0]["client_name"] == "Claude"
    assert "access" not in str(listing)
    foreign = client.get(f"{BASE}/oauth/connections", headers=team.c.headers).json()[0]["id"]
    assert (
        client.delete(f"{BASE}/oauth/connections/{foreign}", headers=team.a.headers).status_code
        == 404
    )
    assert (
        client.delete(
            f"{BASE}/oauth/connections/{listing[0]['id']}", headers=team.a.headers
        ).status_code
        == 204
    )
    assert _mcp(client, mine["access_token"]).status_code == 401
    assert client.get(f"{BASE}/oauth/connections", headers=team.a.headers).json() == []
