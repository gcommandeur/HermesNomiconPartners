"""Prozess-Sharing: ein einzelner Prozess wird gezielt mit einem Kollegen
geteilt (voller Zugriff), additiv zur Sichtbarkeit ueber Owner/Team.

Setup: A (member, Owner), C (member, unbeteiligt), D (member, nie beteiligt),
B (team_lead mit A als Mitarbeiterin), dazu ein Admin."""

import uuid
from dataclasses import dataclass

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from cc_crm.models.recruiting import AuditLog
from tests.api.test_owner_filter import _full_process
from tests.api.test_team_lead import Person, _ids, _make_user


@dataclass
class Setup:
    a: Person
    b: Person
    c: Person
    d: Person
    admin: Person


@pytest.fixture
def setup(client: TestClient, session_factory: sessionmaker[Session]) -> Setup:
    admin = _make_user(session_factory, "gf@share.example", "admin", "Gerda GF")
    a = _make_user(session_factory, "a@share.example", "member", "Anna")
    b = _make_user(session_factory, "b@share.example", "team_lead", "Bernd")
    c = _make_user(session_factory, "c@share.example", "member", "Carla")
    d = _make_user(session_factory, "d@share.example", "member", "Dirk")
    client.patch(f"/api/v1/users/{a.id}", json={"manager_id": b.id}, headers=admin.headers)
    process = _full_process(client, a.headers, "Anna")
    a.process_id = process["id"]
    a.placement_id = client.get(
        f"/api/v1/submissions/{a.process_id}/placement", headers=admin.headers
    ).json()["id"]
    a.fee_id = client.get(
        f"/api/v1/placements/{a.placement_id}/fees", headers=admin.headers
    ).json()[0]["id"]
    return Setup(a=a, b=b, c=c, d=d, admin=admin)


def _share(client: TestClient, s: Setup, who: Person, by: Person | None = None):  # type: ignore[no-untyped-def]
    return client.post(
        f"/api/v1/submissions/{s.a.process_id}/shares",
        json={"shared_with_user_id": who.id},
        headers=(by or s.a).headers,
    )


def _paths(s: Setup) -> list[str]:
    a = s.a
    return [
        f"/api/v1/submissions/{a.process_id}",
        f"/api/v1/submissions/{a.process_id}/placement",
        f"/api/v1/submissions/{a.process_id}/interviews",
        f"/api/v1/submissions/{a.process_id}/offers",
        f"/api/v1/submissions/{a.process_id}/feedback",
        f"/api/v1/placements/{a.placement_id}/fees",
    ]


def test_unrelated_member_has_no_access_without_share(client: TestClient, setup: Setup) -> None:
    for person in (setup.c, setup.d):
        assert _ids(client, person) == set()
        for path in _paths(setup):
            assert client.get(path, headers=person.headers).status_code == 404, path


def test_share_grants_access_everywhere_and_revocation_removes_it(
    client: TestClient, setup: Setup
) -> None:
    response = _share(client, setup, setup.c)
    assert response.status_code == 201, response.text
    share = response.json()
    assert share["shared_with_user_id"] == setup.c.id
    assert share["shared_with_name"] == "Carla"
    assert share["created_by_name"] == "Anna"

    assert _ids(client, setup.c) == {setup.a.process_id}
    for path in _paths(setup):
        assert client.get(path, headers=setup.c.headers).status_code == 200, path
    for endpoint in ("interviews", "offers", "placements", "fees", "feedback"):
        items = client.get(f"/api/v1/{endpoint}", headers=setup.c.headers).json()
        assert len(items) == 1, endpoint
    priority = client.get("/api/v1/submissions/priority-view", headers=setup.c.headers)
    assert all(item["id"] == setup.a.process_id for item in priority.json())
    warranties = client.get("/api/v1/placements/active-warranties", headers=setup.c.headers)
    assert [item["id"] for item in warranties.json()] == [setup.a.placement_id]
    # voller Zugriff: auch schreibend
    patched = client.patch(
        f"/api/v1/submissions/{setup.a.process_id}",
        json={"summary": "von Carla"},
        headers=setup.c.headers,
    )
    assert patched.status_code == 200, patched.text
    invoice = client.post(
        f"/api/v1/fees/{setup.a.fee_id}/invoice-status",
        json={"invoice_status": "cancelled"},
        headers=setup.c.headers,
    )
    assert invoice.status_code == 200, invoice.text
    # D bleibt aussen vor
    assert _ids(client, setup.d) == set()
    assert client.get(_paths(setup)[0], headers=setup.d.headers).status_code == 404

    # Owner widerruft -> sofort weg
    revoked = client.delete(
        f"/api/v1/submissions/{setup.a.process_id}/shares/{share['id']}", headers=setup.a.headers
    )
    assert revoked.status_code == 204
    assert _ids(client, setup.c) == set()
    for path in _paths(setup):
        assert client.get(path, headers=setup.c.headers).status_code == 404, path
    for endpoint in ("interviews", "offers", "placements", "fees", "feedback"):
        assert client.get(f"/api/v1/{endpoint}", headers=setup.c.headers).json() == []


def test_recipient_can_remove_own_share(client: TestClient, setup: Setup) -> None:
    share = _share(client, setup, setup.c).json()
    url = f"/api/v1/submissions/{setup.a.process_id}/shares/{share['id']}"
    # Unbeteiligter D darf nicht widerrufen (404)
    assert client.delete(url, headers=setup.d.headers).status_code == 404
    assert client.delete(url, headers=setup.c.headers).status_code == 204
    assert _ids(client, setup.c) == set()
    assert client.get(_paths(setup)[0], headers=setup.c.headers).status_code == 404
    assert client.get(f"/api/v1/submissions/{setup.a.process_id}/shares",
                      headers=setup.a.headers).json() == []


def test_share_list_visible_to_everyone_with_access(client: TestClient, setup: Setup) -> None:
    _share(client, setup, setup.c)
    url = f"/api/v1/submissions/{setup.a.process_id}/shares"
    for person in (setup.a, setup.b, setup.c, setup.admin):
        listed = client.get(url, headers=person.headers)
        assert listed.status_code == 200, person.id
        assert [item["shared_with_user_id"] for item in listed.json()] == [setup.c.id]
    assert client.get(url, headers=setup.d.headers).status_code == 404


def test_validation_rules(client: TestClient, setup: Setup) -> None:
    own = _share(client, setup, setup.a)
    assert own.status_code in (400, 409, 422), own.text
    # mit dem Owner selbst (durch Admin ausgeloest, der nicht Owner ist)
    owner = _share(client, setup, setup.a, by=setup.admin)
    assert owner.status_code in (400, 409, 422), owner.text
    ghost = client.post(
        f"/api/v1/submissions/{setup.a.process_id}/shares",
        json={"shared_with_user_id": str(uuid.uuid4())},
        headers=setup.a.headers,
    )
    assert ghost.status_code in (400, 404, 409, 422), ghost.text

    client.patch(f"/api/v1/users/{setup.d.id}", json={"is_active": False},
                 headers=setup.admin.headers)
    inactive = _share(client, setup, setup.d)
    assert inactive.status_code in (400, 404, 409, 422), inactive.text
    assert client.get(f"/api/v1/submissions/{setup.a.process_id}/shares",
                      headers=setup.a.headers).json() == []


def test_duplicate_share_is_idempotent(client: TestClient, setup: Setup) -> None:
    first = _share(client, setup, setup.c)
    second = _share(client, setup, setup.c)
    assert first.status_code == 201 and second.status_code == 201
    assert first.json()["id"] == second.json()["id"]
    listed = client.get(
        f"/api/v1/submissions/{setup.a.process_id}/shares", headers=setup.a.headers
    ).json()
    assert len(listed) == 1


def test_team_lead_via_hierarchy_and_recipient_can_reshare(
    client: TestClient, setup: Setup
) -> None:
    # D ist unbeteiligt und darf weder teilen noch die Freigaben sehen.
    outsider = _share(client, setup, setup.b, by=setup.d)
    assert outsider.status_code == 404
    # B sieht den Prozess nur ueber die Team-Hierarchie und darf trotzdem teilen.
    assert _share(client, setup, setup.c, by=setup.b).status_code == 201
    # C (nur per Freigabe) darf weiterteilen - Vertretung ohne Owner/Admin.
    assert _share(client, setup, setup.d, by=setup.c).status_code == 201
    assert _ids(client, setup.d) == {setup.a.process_id}


def test_team_scope_unchanged_and_admin_unrestricted(client: TestClient, setup: Setup) -> None:
    assert _ids(client, setup.b) == {setup.a.process_id}  # Team-Sicht unveraendert
    assert _ids(client, setup.admin) == {setup.a.process_id}
    _share(client, setup, setup.c)
    assert _ids(client, setup.admin) == {setup.a.process_id}
    for path in _paths(setup):
        assert client.get(path, headers=setup.admin.headers).status_code == 200


def test_audit_log_entries(client: TestClient, setup: Setup, session_factory: sessionmaker[Session]) -> None:
    share = _share(client, setup, setup.c).json()
    _share(client, setup, setup.c)  # idempotent: kein zweiter Eintrag
    client.delete(
        f"/api/v1/submissions/{setup.a.process_id}/shares/{share['id']}", headers=setup.c.headers
    )
    with session_factory() as session:
        rows = session.scalars(
            select(AuditLog)
            .where(AuditLog.action.in_(["share_added", "share_removed"]))
            .order_by(AuditLog.changed_at)
        ).all()
    assert sorted(row.action for row in rows) == ["share_added", "share_removed"]
    added = next(row for row in rows if row.action == "share_added")
    removed = next(row for row in rows if row.action == "share_removed")
    assert str(added.entity_id) == setup.a.process_id
    assert added.changed_by == "a@share.example"
    assert (added.new_values or {})["shared_with_user_id"] == setup.c.id
    assert removed.changed_by == "c@share.example"
    assert (removed.old_values or {})["shared_with_user_id"] == setup.c.id


def test_cockpit_includes_shared_process(client: TestClient, setup: Setup) -> None:
    before = client.get("/api/v1/cockpit", headers=setup.c.headers)
    assert before.status_code == 200, before.text
    _share(client, setup, setup.c)
    after = client.get("/api/v1/cockpit", headers=setup.c.headers)
    assert after.status_code == 200
    assert after.json() != before.json()
