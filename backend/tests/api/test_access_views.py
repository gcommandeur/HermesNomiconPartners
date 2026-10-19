# NOMICON: Ansichten (Direct, Ueberlassung, Gesamt) - nur in der Nomicon-Kopie.
"""Freischaltung der Ansichten: Durchsetzung auf jeder zugeordneten Route, Vergabe nur durch Admins,
Audit-Log, Admins nicht aussperrbar, Gesamt nur fuer Admins."""

from __future__ import annotations

import uuid
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from cc_crm.core.security import hash_password
from cc_crm.models.access_views import UserViewAccess
from cc_crm.models.recruiting import AuditLog
from cc_crm.models.user import User
from cc_crm.services.auth import AuthService
from tests.api.test_owner_filter import auth_header

API = "/api/v1"
NOT_ALLOWED = "Diese Ansicht ist für dein Konto nicht freigeschaltet."
METHODS = ("get", "post", "put", "patch", "delete")

# Route -> Ansicht (siehe docs/ANSICHTEN.md). Praefixe der OpenAPI-Pfade ohne /api/v1.
DIRECT_PREFIXES = (
    "/submissions",
    "/vacancies",
    "/sourcing",
    "/feedback",
    "/interviews",
    "/offers",
    "/placements",
    "/fees",
)
STAFFING_PREFIXES = ("/staffing",)  # NICHT "/public/timesheets" (Token-Zugang ohne Login)
MANAGEMENT_PREFIXES = ("/commission", "/management")


def _user(
    session_factory: sessionmaker[Session], email: str, role: str, views: tuple[str, ...] | None
) -> tuple[str, dict[str, str]]:
    """views=None: nie konfiguriert (Standard greift)."""
    with session_factory() as session:
        user = User(email=email, hashed_password=hash_password("x"), role=role)
        session.add(user)
        session.commit()
        for view in views or ():
            session.add(UserViewAccess(user_id=user.id, view=view))
        session.commit()
        _, token = AuthService(session).login(email, "x")
        return str(user.id), auth_header(token)


def _operations(client: TestClient, prefixes: tuple[str, ...]) -> list[tuple[str, str, Any]]:
    paths: dict[str, Any] = client.app.openapi()["paths"]  # type: ignore[attr-defined]
    found = []
    for path, item in paths.items():
        rel = path.removeprefix(API)
        if not any(rel == p or rel.startswith(p + "/") for p in prefixes):
            continue
        for method in METHODS:
            if method in item:
                found.append((method.upper(), path, item[method]))
    return found


def _fill(path: str, operation: dict[str, Any]) -> str:
    url = path
    for parameter in operation.get("parameters", []):
        if parameter.get("in") != "path":
            continue
        schema = parameter.get("schema", {})
        if schema.get("enum"):
            value = str(schema["enum"][0])
        elif schema.get("format") == "uuid":
            value = str(uuid.uuid4())
        else:
            value = "x"
        url = url.replace("{" + parameter["name"] + "}", value)
    return url


def _call(client: TestClient, method: str, url: str, headers: dict[str, str]) -> Any:
    body = {} if method in ("POST", "PUT", "PATCH") else None
    return client.request(method, url, json=body, headers=headers)


@pytest.mark.parametrize(
    ("prefixes", "granted", "minimum"),
    [
        (DIRECT_PREFIXES, ("staffing",), 20),  # ohne Direct: alles Direct-Zugeordnete 403
        (STAFFING_PREFIXES, ("direct",), 25),  # ohne Ueberlassung: alles /staffing 403
        (MANAGEMENT_PREFIXES, ("direct", "staffing"), 4),  # Gesamt: nie fuer Nicht-Admins
    ],
)
def test_every_mapped_route_is_forbidden_without_the_view(
    client: TestClient,
    session_factory: sessionmaker[Session],
    prefixes: tuple[str, ...],
    granted: tuple[str, ...],
    minimum: int,
) -> None:
    _, headers = _user(session_factory, f"x{prefixes[0][1:4]}@n.example", "member", granted)
    operations = _operations(client, prefixes)
    assert len(operations) >= minimum, len(operations)  # Suche nicht wirkungslos
    wrong = []
    for method, path, operation in operations:
        response = _call(client, method, _fill(path, operation), headers)
        if response.status_code != 403 or response.json().get("detail") not in (
            NOT_ALLOWED,
            "Nur für Admins zugänglich.",
            "Nur fuer Admins zugaenglich.",
        ):
            wrong.append((method, path, response.status_code))
    assert not wrong, wrong


def test_public_timesheet_links_need_no_view(client: TestClient) -> None:
    """Der Token-Zugang des Kunden bleibt unberuehrt (kein Login, keine Ansicht)."""
    response = client.get(f"{API}/public/timesheets/{'x' * 20}", headers={"Authorization": ""})
    assert response.status_code != 403


def test_unconfigured_user_gets_the_default_direct(
    client: TestClient, session_factory: sessionmaker[Session]
) -> None:
    _, headers = _user(session_factory, "neu@n.example", "member", None)
    body = client.get(f"{API}/me/views", headers=headers).json()
    assert body == {"views": ["direct"], "default_view": "direct"}
    assert client.get(f"{API}/submissions", headers=headers).status_code == 200
    denied = client.get(f"{API}/staffing/overview", headers=headers)
    assert denied.status_code == 403
    assert denied.json()["detail"] == NOT_ALLOWED


def test_admin_always_has_all_views(
    client: TestClient, session_factory: sessionmaker[Session]
) -> None:
    admin_id, headers = _user(session_factory, "gf@n.example", "admin", None)
    body = client.get(f"{API}/me/views", headers=headers).json()
    assert body["views"] == ["direct", "staffing", "management"]
    assert body["default_view"] == "management"
    # Entzug wird abgelehnt (nicht still ignoriert)
    refused = client.put(
        f"{API}/admin/users/{admin_id}/views", json={"views": ["direct"]}, headers=headers
    )
    assert refused.status_code == 422


def test_admin_grants_and_revokes_with_audit_trail(
    client: TestClient, session_factory: sessionmaker[Session]
) -> None:
    _, admin = _user(session_factory, "gf@n.example", "admin", None)
    member_id, member = _user(session_factory, "m@n.example", "member", None)
    assert client.get(f"{API}/staffing/overview", headers=member).status_code == 403

    granted = client.put(
        f"{API}/admin/users/{member_id}/views",
        json={"views": ["direct", "staffing"], "default_view": "staffing"},
        headers=admin,
    )
    assert granted.status_code == 200, granted.text
    assert granted.json()["views"] == ["direct", "staffing"]
    assert client.get(f"{API}/staffing/overview", headers=member).status_code == 200
    assert client.get(f"{API}/me/views", headers=member).json()["default_view"] == "staffing"

    revoked = client.put(
        f"{API}/admin/users/{member_id}/views", json={"views": ["direct"]}, headers=admin
    )
    assert revoked.status_code == 200
    assert client.get(f"{API}/staffing/overview", headers=member).status_code == 403

    with session_factory() as session:
        entries = session.scalars(
            select(AuditLog)
            .where(
                AuditLog.entity_type == "user_view_access",
                AuditLog.entity_id == uuid.UUID(member_id),
            )
            .order_by(AuditLog.changed_at)
        ).all()
    assert len(entries) == 2
    assert all(entry.changed_by == "gf@n.example" for entry in entries)
    assert entries[0].old_values["views"] == ["direct"]  # type: ignore[index]
    assert entries[0].new_values["views"] == ["direct", "staffing"]  # type: ignore[index]
    assert entries[1].new_values["views"] == ["direct"]  # type: ignore[index]


def test_only_admins_may_grant_and_management_is_admin_only(
    client: TestClient, session_factory: sessionmaker[Session]
) -> None:
    _, admin = _user(session_factory, "gf@n.example", "admin", None)
    member_id, member = _user(session_factory, "m@n.example", "member", None)
    lead_id, lead = _user(session_factory, "l@n.example", "team_lead", None)
    body = {"views": ["direct", "staffing"]}
    for headers in (member, lead):
        assert (
            client.put(
                f"{API}/admin/users/{member_id}/views", json=body, headers=headers
            ).status_code
            == 403
        )
        assert client.get(f"{API}/admin/view-access", headers=headers).status_code == 403
    # Gesamt: Server lehnt die Vergabe an Nicht-Admins ab
    for target in (member_id, lead_id):
        response = client.put(
            f"{API}/admin/users/{target}/views",
            json={"views": ["direct", "management"]},
            headers=admin,
        )
        assert response.status_code == 422, response.text
    # Selbst eine direkt in die Datenbank geschriebene Freigabe wirkt fuer Nicht-Admins nicht
    with session_factory() as session:
        session.add(UserViewAccess(user_id=uuid.UUID(member_id), view="management"))
        session.add(UserViewAccess(user_id=uuid.UUID(member_id), view="direct"))
        session.commit()
    assert client.get(f"{API}/me/views", headers=member).json()["views"] == ["direct"]
    assert client.get(f"{API}/commission/report", headers=member).status_code == 403


def test_view_matrix_defaults_and_unknown_values(
    client: TestClient, session_factory: sessionmaker[Session]
) -> None:
    _, admin = _user(session_factory, "gf@n.example", "admin", None)
    member_id, _ = _user(session_factory, "m@n.example", "member", ("direct",))
    matrix = client.get(f"{API}/admin/view-access", headers=admin).json()
    assert {"gf@n.example", "m@n.example"} <= {row["email"] for row in matrix}
    assert (
        client.put(
            f"{API}/admin/users/{member_id}/views", json={"views": ["nope"]}, headers=admin
        ).status_code
        == 422
    )
    assert (
        client.put(
            f"{API}/admin/users/{member_id}/views", json={"views": []}, headers=admin
        ).status_code
        == 422
    )
    assert (
        client.put(
            f"{API}/admin/users/{member_id}/views",
            json={"views": ["direct"], "default_view": "staffing"},
            headers=admin,
        ).status_code
        == 422
    )

    # einstellbarer Standard fuer neue Nutzer
    assert client.get(f"{API}/admin/view-access/defaults", headers=admin).json() == {
        "views": ["direct"]
    }
    saved = client.put(
        f"{API}/admin/view-access/defaults",
        json={"views": ["direct", "staffing"]},
        headers=admin,
    )
    assert saved.status_code == 200
    _, fresh = _user(session_factory, "frisch@n.example", "member", None)
    assert client.get(f"{API}/me/views", headers=fresh).json()["views"] == ["direct", "staffing"]
    assert (
        client.put(
            f"{API}/admin/view-access/defaults", json={"views": ["management"]}, headers=admin
        ).status_code
        == 422
    )


def test_user_remembers_selected_view_server_side(
    client: TestClient, session_factory: sessionmaker[Session]
) -> None:
    _, headers = _user(session_factory, "m@n.example", "member", ("direct", "staffing"))
    response = client.put(f"{API}/me/view", json={"view": "staffing"}, headers=headers)
    assert response.status_code == 200
    assert client.get(f"{API}/me/views", headers=headers).json()["default_view"] == "staffing"
    refused = client.put(f"{API}/me/view", json={"view": "management"}, headers=headers)
    assert refused.status_code == 422


def test_wage_stays_hidden_with_the_staffing_view(
    client: TestClient, session_factory: sessionmaker[Session]
) -> None:
    """Die Ansicht schaltet Module frei, nie Lohn oder Marge: Lohn und Marge bleiben Admin-Sache."""
    _, headers = _user(session_factory, "m@n.example", "member", ("direct", "staffing"))
    assert client.get(f"{API}/commission/report", headers=headers).status_code == 403
    overview = client.get(f"{API}/staffing/overview", headers=headers)
    assert overview.status_code == 200
    text = overview.text
    assert "hourly_wage" not in text and "margin" not in text
