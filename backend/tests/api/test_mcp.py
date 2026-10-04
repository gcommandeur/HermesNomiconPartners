"""Lesende Claude-Schnittstelle (MCP): standardmaessig aus, nur mit API-Key, nur
Rechte des Key-Besitzers, keine Kontaktdaten, Audit und Tageslimit."""

import uuid
from collections.abc import Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from cc_crm.core.config import get_settings
from cc_crm.models.recruiting import AuditLog
from cc_crm.models.user import User
from cc_crm.services.api_keys import ApiKeyService
from tests.api.test_team_lead import Person, Team, team  # noqa: F401


@pytest.fixture
def ai_on(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    monkeypatch.setenv("CC_CRM_AI_ENABLED", "true")
    get_settings.cache_clear()
    yield
    monkeypatch.delenv("CC_CRM_AI_ENABLED", raising=False)
    get_settings.cache_clear()


def _mcp_key(session_factory: sessionmaker[Session], person: Person) -> dict[str, str]:
    with session_factory() as session:
        user = session.get(User, uuid.UUID(person.id))
        assert user is not None
        _, raw = ApiKeyService(session).create_mcp_key("Claude", user)
    return {"X-API-Key": raw}


def _rpc(
    client: TestClient, headers: dict[str, str], method: str, params: dict[str, Any] | None = None
) -> dict[str, Any]:
    response = client.post(
        "/api/v1/mcp",
        json={"jsonrpc": "2.0", "id": 1, "method": method, "params": params or {}},
        headers=headers,
    )
    assert response.status_code == 200, response.text
    body: dict[str, Any] = response.json()
    return body


def _call(
    client: TestClient, headers: dict[str, str], name: str, **arguments: Any
) -> dict[str, Any]:
    return _rpc(client, headers, "tools/call", {"name": name, "arguments": arguments})


def test_disabled_by_default(client: TestClient, team: Team, session_factory) -> None:  # noqa: F811
    headers = _mcp_key(session_factory, team.a)
    response = client.post(
        "/api/v1/mcp", json={"jsonrpc": "2.0", "id": 1, "method": "ping"}, headers=headers
    )
    assert response.status_code == 404


def test_handshake_and_tool_list(
    client: TestClient,
    team: Team,  # noqa: F811
    session_factory,
    ai_on: None,
) -> None:
    headers = _mcp_key(session_factory, team.a)
    init = _rpc(client, headers, "initialize", {"protocolVersion": "2025-06-18"})
    assert init["result"]["protocolVersion"] == "2025-06-18"
    assert init["result"]["serverInfo"]["name"] == "hermes-crm"
    note = client.post(
        "/api/v1/mcp",
        json={"jsonrpc": "2.0", "method": "notifications/initialized"},
        headers=headers,
    )
    assert note.status_code == 202
    names = {tool["name"] for tool in _rpc(client, headers, "tools/list")["result"]["tools"]}
    assert {"search_candidates", "get_candidate", "list_my_processes", "cockpit_summary"} <= names
    unknown = _call(client, headers, "delete_everything")
    assert unknown["error"]["code"] == -32602


def test_requires_api_key_not_browser_session(
    client: TestClient,
    team: Team,  # noqa: F811
    ai_on: None,
) -> None:
    response = client.post(
        "/api/v1/mcp",
        json={"jsonrpc": "2.0", "id": 1, "method": "ping"},
        headers=team.a.headers,
    )
    # Eine Browser-Sitzung ist kein MCP-Zugang: 401 mit Hinweis auf die OAuth-Anmeldung.
    assert response.status_code == 401
    assert "resource_metadata" in response.headers["www-authenticate"]


def test_mcp_key_is_useless_outside_mcp(
    client: TestClient,
    team: Team,  # noqa: F811
    session_factory,
    ai_on: None,
) -> None:
    headers = _mcp_key(session_factory, team.a)
    for path in ("/api/v1/candidates", "/api/v1/submissions", "/api/v1/auth/me"):
        assert client.get(path, headers=headers).status_code == 401, path


def test_candidates_come_without_contact_data(
    client: TestClient,
    team: Team,  # noqa: F811
    session_factory,
    ai_on: None,
) -> None:
    created = client.post(
        "/api/v1/candidates",
        json={
            "first_name": "Mia",
            "last_name": "Geheimnis",
            "email": "mia.geheimnis@privat.example",
            "phone": "+49 170 5551234",
            "job_title": "Steuerfachangestellte",
            "short_profile": "Bilanzbuchhalterin mit DATEV-Erfahrung",
        },
        headers=team.a.headers,
    )
    assert created.status_code == 201, created.text
    headers = _mcp_key(session_factory, team.a)

    found = _call(client, headers, "search_candidates", query="Geheimnis")
    opened = _call(client, headers, "get_candidate", candidate_id=created.json()["id"])
    text = found["result"]["content"][0]["text"] + opened["result"]["content"][0]["text"]
    assert "Geheimnis" in text  # Vorbedingung: der Kandidat wird gefunden
    assert "DATEV" in text
    assert "privat.example" not in text
    assert "5551234" not in text


def test_processes_follow_the_key_owners_rights(
    client: TestClient,
    team: Team,  # noqa: F811
    session_factory,
    ai_on: None,
) -> None:
    def process_ids(person: Person) -> set[str]:
        result = _call(client, _mcp_key(session_factory, person), "list_my_processes")
        import json

        payload = json.loads(result["result"]["content"][0]["text"])
        return {item["id"] for item in payload["items"]}

    assert process_ids(team.a) == {team.a.process_id}  # Mitarbeiter: nur eigene
    assert process_ids(team.b) == {team.a.process_id, team.b.process_id}  # Teamleiter: + Team
    assert process_ids(team.c) == {team.c.process_id}


def test_calls_are_audited_without_arguments(
    client: TestClient,
    team: Team,  # noqa: F811
    session_factory,
    ai_on: None,
) -> None:
    headers = _mcp_key(session_factory, team.a)
    _call(client, headers, "search_candidates", query="Streng-Geheim-Suchwort")
    with session_factory() as session:
        entries = session.scalars(select(AuditLog).where(AuditLog.action == "mcp_tool_call")).all()
    assert len(entries) == 1
    assert entries[0].new_values == {"tool": "search_candidates"}
    assert "Streng-Geheim" not in str(entries[0].new_values)


def test_daily_limit(
    client: TestClient,
    team: Team,  # noqa: F811
    session_factory,
    ai_on: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("CC_CRM_MCP_DAILY_LIMIT", "2")
    get_settings.cache_clear()
    headers = _mcp_key(session_factory, team.a)
    first = _call(client, headers, "cockpit_summary")
    second = _call(client, headers, "list_open_tasks")
    third = _call(client, headers, "list_open_tasks")
    assert first["result"]["isError"] is False
    assert second["result"]["isError"] is False
    assert third["result"]["isError"] is True
    assert "Tageslimit" in third["result"]["content"][0]["text"]
