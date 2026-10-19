# ruff: noqa: F811
"""Claude-Vorschlaege: Claude darf nur vorbereiten, Menschen geben frei."""

from __future__ import annotations

import ast
import uuid
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from cc_crm.core.config import get_settings
from cc_crm.models.ai_proposal import AiProposal
from cc_crm.models.mail import MailMessage
from cc_crm.models.note import Note
from cc_crm.models.recruiting import AuditLog
from cc_crm.models.task import Task
from cc_crm.models.user import User
from cc_crm.services.api_keys import ApiKeyService
from tests.api.test_team_lead import Person, Team, team  # noqa: F401

SRC = Path(__file__).resolve().parents[2] / "src" / "cc_crm"


@pytest.fixture
def ai_on(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    monkeypatch.setenv("CC_CRM_AI_ENABLED", "true")
    get_settings.cache_clear()
    yield
    monkeypatch.delenv("CC_CRM_AI_ENABLED", raising=False)
    get_settings.cache_clear()


def _key(session_factory: sessionmaker[Session], person: Person) -> dict[str, str]:
    with session_factory() as session:
        user = session.get(User, uuid.UUID(person.id))
        assert user is not None
        _, raw = ApiKeyService(session).create_mcp_key("Claude", user)
    return {"X-API-Key": raw}


def _call(client: TestClient, headers: dict[str, str], name: str, **arguments: Any) -> dict:
    response = client.post(
        "/api/v1/mcp",
        json={
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {"name": name, "arguments": arguments},
        },
        headers=headers,
    )
    assert response.status_code == 200, response.text
    body = response.json()
    if "error" in body:  # Protokollfehler (z.B. ungueltige ID) zaehlt ebenfalls als Fehler
        return {"isError": True, "content": [{"text": body["error"]["message"]}]}
    return body["result"]


def _candidate(client: TestClient, headers: dict[str, str], **over: Any) -> dict:
    body = {"first_name": "Karla", "last_name": "Kandidatin", "email": "karla@example.com", **over}
    response = client.post("/api/v1/candidates", json=body, headers=headers)
    assert response.status_code == 201, response.text
    return response.json()


def _counts(session_factory: sessionmaker[Session]) -> dict[str, int]:
    with session_factory() as session:
        return {
            "notes": len(session.scalars(select(Note)).all()),
            "tasks": len(session.scalars(select(Task)).all()),
            "mails": len(session.scalars(select(MailMessage)).all()),
        }


def test_proposals_are_stored_but_create_nothing(
    client: TestClient,
    team: Team,
    session_factory,
    ai_on: None,  # noqa: F811
) -> None:
    candidate = _candidate(client, team.a.headers)
    mcp = _key(session_factory, team.a)
    before = _counts(session_factory)

    note = _call(client, mcp, "propose_note", candidate_id=candidate["id"], text="Wechselt gern.")
    task = _call(client, mcp, "propose_task", title="Nachfassen", candidate_id=candidate["id"])
    mail = _call(
        client,
        mcp,
        "propose_mail_draft",
        candidate_id=candidate["id"],
        subject="Hallo",
        body="Text",
    )
    for result in (note, task, mail):
        assert result["isError"] is False
        assert "nichts angelegt oder gesendet" in result["content"][0]["text"]

    assert _counts(session_factory) == before  # keine Notiz, Aufgabe oder Mail entstanden
    pending = client.get("/api/v1/ai-proposals?status=pending", headers=team.a.headers).json()
    assert sorted(item["kind"] for item in pending) == ["mail_draft", "note", "task"]
    mail_item = next(item for item in pending if item["kind"] == "mail_draft")
    assert mail_item["recipient_email"] == "karla@example.com"  # aus dem Datensatz
    assert mail_item["target_label"] == "Karla Kandidatin"
    assert mail_item["created_by_name"]
    summary = client.get("/api/v1/ai-proposals/summary", headers=team.a.headers).json()
    assert summary == {"enabled": True, "pending": 3}


def test_approve_creates_note_and_task_marked_as_from_claude(
    client: TestClient,
    team: Team,
    session_factory,
    ai_on: None,  # noqa: F811
) -> None:
    candidate = _candidate(client, team.a.headers)
    mcp = _key(session_factory, team.a)
    _call(client, mcp, "propose_note", candidate_id=candidate["id"], text="Wechselt gern.")
    _call(
        client,
        mcp,
        "propose_task",
        title="Nachfassen",
        candidate_id=candidate["id"],
        due_at="2026-12-01T09:00:00",
    )
    items = {
        i["kind"]: i for i in client.get("/api/v1/ai-proposals", headers=team.a.headers).json()
    }

    # Mit Bearbeitung freigeben: der Mensch aendert den Text vorher.
    approved = client.post(
        f"/api/v1/ai-proposals/{items['note']['id']}/approve",
        json={"payload": {"text": "Wechselt gern - ab Januar."}},
        headers=team.a.headers,
    )
    assert approved.status_code == 200, approved.text
    assert approved.json()["status"] == "approved"
    task_ok = client.post(
        f"/api/v1/ai-proposals/{items['task']['id']}/approve", json={}, headers=team.a.headers
    )
    assert task_ok.status_code == 200, task_ok.text

    with session_factory() as session:
        note = session.scalars(select(Note).where(Note.body.like("[per Claude]%"))).one()
        assert note.body == "[per Claude] Wechselt gern - ab Januar."
        assert str(note.created_by_user_id) == team.a.id  # der Mensch ist der Autor
        task = session.scalars(select(Task).where(Task.title == "Nachfassen")).one()
        assert task.title == "Nachfassen"
        assert "Vorschlag von Claude" in (task.description or "")
        assert str(task.owner_user_id) == team.a.id
        actions = [row.action for row in session.scalars(select(AuditLog))]
        assert actions.count("ai_proposal_created") == 2
        assert actions.count("ai_proposal_approved") == 2
        for row in session.scalars(select(AuditLog)):
            if row.entity_type == "ai_proposal":
                assert "Wechselt" not in str(row.new_values)  # nie der Text im Audit-Log

    # Bereits entschieden -> nicht nochmal.
    again = client.post(
        f"/api/v1/ai-proposals/{items['note']['id']}/approve", json={}, headers=team.a.headers
    )
    assert again.status_code >= 400


def test_mail_draft_approval_never_sends_anything(
    client: TestClient,
    team: Team,
    session_factory,
    ai_on: None,
    monkeypatch,  # noqa: F811
) -> None:
    candidate = _candidate(client, team.a.headers)
    mcp = _key(session_factory, team.a)
    _call(
        client,
        mcp,
        "propose_mail_draft",
        candidate_id=candidate["id"],
        subject="Hallo",
        body="Entwurf",
    )

    def boom(*args: object, **kwargs: object) -> None:
        raise AssertionError("Hier darf nichts gesendet werden")

    monkeypatch.setattr("cc_crm.services.mail_send.send_mail", boom)
    monkeypatch.setattr("cc_crm.services.mail_send.send_bulk", boom)
    item = client.get("/api/v1/ai-proposals", headers=team.a.headers).json()[0]
    done = client.post(
        f"/api/v1/ai-proposals/{item['id']}/approve", json={}, headers=team.a.headers
    )
    assert done.status_code == 200 and done.json()["result_entity_id"] is None
    assert _counts(session_factory)["mails"] == 0


def test_reject_and_visibility(
    client: TestClient,
    team: Team,
    session_factory,
    ai_on: None,  # noqa: F811
) -> None:
    candidate = _candidate(client, team.a.headers)
    _call(
        client,
        _key(session_factory, team.a),
        "propose_note",
        candidate_id=candidate["id"],
        text="Text",
    )
    proposal = client.get("/api/v1/ai-proposals", headers=team.a.headers).json()[0]
    url = f"/api/v1/ai-proposals/{proposal['id']}"

    # Eine fremde Mitarbeiterin (C) sieht ihn nicht: 404 und leere Liste.
    assert client.get("/api/v1/ai-proposals", headers=team.c.headers).json() == []
    assert client.post(f"{url}/approve", json={}, headers=team.c.headers).status_code == 404
    assert client.post(f"{url}/reject", json={}, headers=team.c.headers).status_code == 404
    # Teamleiter B (von A) und Admin duerfen entscheiden.
    assert [i["id"] for i in client.get("/api/v1/ai-proposals", headers=team.b.headers).json()] == [
        proposal["id"]
    ]
    rejected = client.post(
        f"{url}/reject", json={"decision_note": "unpassend"}, headers=team.b.headers
    )
    assert rejected.status_code == 200 and rejected.json()["status"] == "rejected"
    assert _counts(session_factory)["notes"] == 0
    assert client.get("/api/v1/ai-proposals/summary", headers=team.a.headers).json()["pending"] == 0


def test_validation_and_limits(
    client: TestClient,
    team: Team,
    session_factory,
    ai_on: None,  # noqa: F811
) -> None:
    candidate = _candidate(client, team.a.headers)
    mcp = _key(session_factory, team.a)
    bad = [
        ("propose_note", {"candidate_id": candidate["id"], "text": ""}),
        ("propose_note", {"candidate_id": candidate["id"], "text": "x" * 6000}),
        ("propose_note", {"text": "ohne Bezug"}),
        ("propose_note", {"candidate_id": str(uuid.uuid4()), "text": "unbekannt"}),
        ("propose_task", {"title": "x" * 300}),
        ("propose_mail_draft", {"subject": "S", "body": "B"}),  # ohne Empfaenger
        ("propose_mail_draft", {"candidate_id": candidate["id"], "subject": "", "body": "B"}),
    ]
    for name, args in bad:
        assert _call(client, mcp, name, **args)["isError"] is True, (name, args)
    assert client.get("/api/v1/ai-proposals", headers=team.a.headers).json() == []


def test_mcp_key_cannot_decide_proposals(
    client: TestClient,
    team: Team,
    session_factory,
    ai_on: None,  # noqa: F811
) -> None:
    candidate = _candidate(client, team.a.headers)
    mcp = _key(session_factory, team.a)
    _call(client, mcp, "propose_note", candidate_id=candidate["id"], text="Text")
    with session_factory() as session:
        proposal_id = str(session.scalars(select(AiProposal)).one().id)
    # Mit dem MCP-Schluessel gibt es keinen Zugriff ausserhalb von /mcp.
    response = client.post(f"/api/v1/ai-proposals/{proposal_id}/approve", json={}, headers=mcp)
    assert response.status_code == 401
    assert client.get("/api/v1/ai-proposals", headers=mcp).status_code == 401
    assert _counts(session_factory)["notes"] == 0


def test_summary_reports_disabled_state(client: TestClient) -> None:
    assert client.get("/api/v1/ai-proposals/summary").json() == {"enabled": False, "pending": 0}


def _imported_modules(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    modules: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            modules.add(node.module)
            modules.update(f"{node.module}.{alias.name}" for alias in node.names)
    return modules


FORBIDDEN = (
    "cc_crm.services.mail_send",
    "cc_crm.services.due_reminders",
    "cc_crm.services.outreach_sequences",
    "cc_crm.services.mail_oauth",
    "cc_crm.integrations.microsoft_graph",
    "cc_crm.integrations.email",
    "smtplib",
)


@pytest.mark.parametrize(
    "relative",
    [
        "services/mcp_server.py",
        "services/ai_proposals.py",
        "api/v1/ai_proposals.py",
        "api/v1/mcp.py",
    ],
)
def test_claude_code_paths_never_import_send_services(relative: str) -> None:
    """Harte Sperre: Die Wege, ueber die Claude etwas anstossen kann, importieren
    keinen Sende-Service. Senden bleibt ausschliesslich beim Menschen."""
    imported = _imported_modules(SRC / relative)
    offenders = [m for m in imported for bad in FORBIDDEN if m == bad or m.startswith(bad + ".")]
    assert offenders == [], f"{relative} importiert {offenders}"
