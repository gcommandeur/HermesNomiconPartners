# ruff: noqa: F811
"""Datenabfluss an Claude festnageln (Review 2026-10-04, Punkt 7).

Die Datenschutz-Freigabe des Nutzers bezieht sich auf die JETZIGE Feldliste der MCP-Werkzeuge.
Dieser Test haelt die exakten Schluesselmengen der Rueckgaben fest: kommt ein Feld dazu, wird er
rot - das ist dann eine BEWUSSTE Entscheidung (Konstante hier aendern UND Datenschutz-Freigabe
pruefen), nie ein Versehen. Zusaetzlich: gesperrte Werte (E-Mail, Telefon, LinkedIn, Gehalt,
Kuendigungsfrist) tauchen in keiner Ausgabe auf.

Bekannte, bewusst freigegebene Textfelder (siehe Bericht zu Punkt 7): `short_profile` (der
anonymisierte Profiltext, KI-erzeugt und vom Berater geprueft, aber technisch nicht auf
Anonymitaet geprueft) und die Kanzlei-Felder `name`/`website` (ein Kanzleiname kann Familiennamen
enthalten)."""

from __future__ import annotations

import json
import uuid
from typing import Any

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session, sessionmaker

from cc_crm.models.client_company import ClientCompany
from cc_crm.models.task import Task
from tests.api.test_mcp import _call, _mcp_key, ai_on  # noqa: F401  (Fixture)
from tests.api.test_team_lead import Team, team  # noqa: F401

CANDIDATE_BRIEF = frozenset(
    {
        "id",
        "name",
        "job_title",
        "qualification",
        "city",
        "postal_code",
        "status",
        "cv_available",
        "last_contact_at",
    }
)
CANDIDATE_DETAIL = CANDIDATE_BRIEF | {"short_profile"}
CLIENT_LIST_ITEM = frozenset({"id", "name", "city", "status", "kanzleigruppe", "website"})
CLIENT_DETAIL = frozenset(
    {"id", "name", "city", "postal_code", "status", "kanzleigruppe", "website"}
)
PROCESS_ITEM = frozenset({"id", "candidate_id", "client_company_id", "status", "created_at"})
TASK_ITEM = frozenset({"id", "title", "due_at", "priority"})
COCKPIT_TOP = frozenset({"period", "kpis", "recruiting_kpis"})

# Werte, die nie an Claude gehen duerfen (siehe Kandidat in `_data`).
FORBIDDEN = (
    "geheim@privat.example",
    "+49 170 5550199",
    "linkedin.com/in/geheim",
    "Gehalt-Wunsch",
    "Frist-3-Monate",
)


def _payload(response: dict[str, Any]) -> tuple[Any, str]:
    text = response["result"]["content"][0]["text"]
    return json.loads(text), text


def _data(client: TestClient, session_factory: sessionmaker[Session], team: Team) -> dict[str, str]:
    created = client.post(
        "/api/v1/candidates",
        json={
            "first_name": "Wilma",
            "last_name": "Whitelist",
            "email": "geheim@privat.example",
            "phone": "+49 170 5550199",
            "linkedin_url": "https://linkedin.com/in/geheim",
            "salary_expectation": "Gehalt-Wunsch 99.000",
            "notice_period": "Frist-3-Monate",
            "job_title": "Steuerfachwirtin",
            "short_profile": "Anonymisiertes Profil mit DATEV-Erfahrung",
        },
        headers=team.a.headers,
    )
    assert created.status_code == 201, created.text
    candidate_id = created.json()["id"]
    # Prozess OHNE Kanzlei (Quick-Log-Fall) - client_company_id muss null sein, nicht "None".
    process = client.post(
        "/api/v1/submissions", json={"candidate_id": candidate_id}, headers=team.a.headers
    )
    assert process.status_code == 201, process.text
    with session_factory() as session:
        company = ClientCompany(
            name="Kanzlei Weiss & Partner", city="Mainz", website="https://weiss.example"
        )
        session.add(company)
        session.add(Task(title="Wilma anrufen", owner_user_id=uuid.UUID(team.a.id)))
        session.commit()
        company_id = str(company.id)
    return {"candidate_id": candidate_id, "client_id": company_id}


def test_candidate_outputs_have_exactly_the_approved_fields(
    client: TestClient, session_factory: sessionmaker[Session], team: Team, ai_on: None
) -> None:
    ids = _data(client, session_factory, team)
    headers = _mcp_key(session_factory, team.a)

    found, found_text = _payload(_call(client, headers, "search_candidates", query="Whitelist"))
    assert set(found) == {"total", "items"}
    assert found["items"], "Vorbedingung: der Kandidat wird gefunden"
    assert {frozenset(item) for item in found["items"]} == {CANDIDATE_BRIEF}

    detail, detail_text = _payload(
        _call(client, headers, "get_candidate", candidate_id=ids["candidate_id"])
    )
    assert frozenset(detail) == CANDIDATE_DETAIL
    assert detail["short_profile"] == "Anonymisiertes Profil mit DATEV-Erfahrung"

    for value in FORBIDDEN:
        assert value not in found_text + detail_text, value


def test_client_outputs_have_exactly_the_approved_fields(
    client: TestClient, session_factory: sessionmaker[Session], team: Team, ai_on: None
) -> None:
    ids = _data(client, session_factory, team)
    headers = _mcp_key(session_factory, team.a)
    listing, _ = _payload(_call(client, headers, "search_clients", query="Weiss"))
    assert set(listing) == {"total", "items"}
    assert listing["items"], "Vorbedingung: die Kanzlei wird gefunden"
    assert {frozenset(item) for item in listing["items"]} == {CLIENT_LIST_ITEM}
    detail, _ = _payload(_call(client, headers, "get_client", client_id=ids["client_id"]))
    assert frozenset(detail) == CLIENT_DETAIL


def test_process_task_and_cockpit_outputs_have_exactly_the_approved_fields(
    client: TestClient, session_factory: sessionmaker[Session], team: Team, ai_on: None
) -> None:
    _data(client, session_factory, team)
    headers = _mcp_key(session_factory, team.a)

    processes, _ = _payload(_call(client, headers, "list_my_processes"))
    assert set(processes) == {"total", "items"}
    assert len(processes["items"]) >= 2  # Fixture-Prozess (mit Kanzlei) + Prozess ohne Kanzlei
    assert {frozenset(item) for item in processes["items"]} == {PROCESS_ITEM}
    # Kein Text "None" statt null: ein Prozess ohne Kanzlei hat client_company_id = null.
    assert any(item["client_company_id"] is None for item in processes["items"])
    assert all(item["client_company_id"] != "None" for item in processes["items"])

    tasks, _ = _payload(_call(client, headers, "list_open_tasks"))
    assert set(tasks) == {"items"}
    assert tasks["items"], "Vorbedingung: die Aufgabe wird gefunden"
    assert {frozenset(item) for item in tasks["items"]} == {TASK_ITEM}

    cockpit, _ = _payload(_call(client, headers, "cockpit_summary"))
    assert frozenset(cockpit) == COCKPIT_TOP
