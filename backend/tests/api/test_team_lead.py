"""Rolle "team_lead": sieht die Prozesse von sich und den Mitarbeitern, die ihm
ueber users.manager_id zugeordnet sind - nicht die des ganzen Unternehmens.

Setup: A (member), B (team_lead, A ist B zugeordnet), C (unbeteiligter zweiter
team_lead), dazu ein Admin. Jeder hat einen eigenen Prozess."""

import uuid
from dataclasses import dataclass

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session, sessionmaker

from cc_crm.core.security import hash_password
from cc_crm.models.user import User
from cc_crm.services.auth import AuthService
from tests.api.test_owner_filter import _full_process, auth_header


@dataclass
class Person:
    id: str
    headers: dict[str, str]
    process_id: str = ""
    placement_id: str = ""
    fee_id: str = ""


def _make_user(session_factory: sessionmaker[Session], email: str, role: str, name: str) -> Person:
    with session_factory() as session:
        user = User(email=email, hashed_password=hash_password("x"), role=role, display_name=name)
        session.add(user)
        session.commit()
        _, token = AuthService(session).login(email, "x")
        return Person(id=str(user.id), headers=auth_header(token))


@dataclass
class Team:
    a: Person
    b: Person
    c: Person
    admin: Person


@pytest.fixture
def team(client: TestClient, session_factory: sessionmaker[Session]) -> Team:
    admin = _make_user(session_factory, "gf@team.example", "admin", "Gerda GF")
    a = _make_user(session_factory, "a@team.example", "member", "Anna Mitarbeiterin")
    b = _make_user(session_factory, "b@team.example", "team_lead", "Bernd Teamleiter")
    c = _make_user(session_factory, "c@team.example", "team_lead", "Clara Teamleiterin")
    response = client.patch(
        f"/api/v1/users/{a.id}", json={"manager_id": b.id}, headers=admin.headers
    )
    assert response.status_code == 200, response.text
    for person, name in ((a, "Anna"), (b, "Bernd"), (c, "Clara")):
        submission = _full_process(client, person.headers, name)
        person.process_id = submission["id"]
        placement = client.get(
            f"/api/v1/submissions/{person.process_id}/placement", headers=admin.headers
        ).json()
        person.placement_id = placement["id"]
        person.fee_id = client.get(
            f"/api/v1/placements/{person.placement_id}/fees", headers=admin.headers
        ).json()[0]["id"]
    return Team(a=a, b=b, c=c, admin=admin)


def _ids(client: TestClient, person: Person) -> set[str]:
    response = client.get("/api/v1/submissions", headers=person.headers)
    assert response.status_code == 200, response.text
    return {item["id"] for item in response.json()["items"]}


def test_scope_per_role(client: TestClient, team: Team) -> None:
    a, b, c = team.a.process_id, team.b.process_id, team.c.process_id

    assert _ids(client, team.a) == {a}  # member: nur eigene (wie bisher)
    assert _ids(client, team.b) == {a, b}  # Teamleiter: eigene + Team
    assert _ids(client, team.c) == {c}  # anderer Teamleiter ohne Team
    assert _ids(client, team.admin) == {a, b, c}  # Admin: alles


def test_member_without_manager_behaves_as_before(client: TestClient, team: Team) -> None:
    client.patch(
        f"/api/v1/users/{team.a.id}", json={"manager_id": None}, headers=team.admin.headers
    )
    assert _ids(client, team.a) == {team.a.process_id}


def test_team_lead_can_narrow_to_own_but_not_to_foreign_owner(
    client: TestClient, team: Team
) -> None:
    own = client.get(
        f"/api/v1/submissions?owner_user_id={team.b.id}", headers=team.b.headers
    ).json()["items"]
    assert [item["id"] for item in own] == [team.b.process_id]

    # Fremder Owner (C ist nicht im Scope von B) -> verworfen, Scope bleibt.
    foreign = client.get(
        f"/api/v1/submissions?owner_user_id={team.c.id}", headers=team.b.headers
    ).json()["items"]
    assert {item["id"] for item in foreign} == {team.a.process_id, team.b.process_id}


def test_direct_id_access_follows_the_team_scope(client: TestClient, team: Team) -> None:
    a = team.a
    paths = [
        f"/api/v1/submissions/{a.process_id}",
        f"/api/v1/submissions/{a.process_id}/placement",
        f"/api/v1/submissions/{a.process_id}/interviews",
        f"/api/v1/placements/{a.placement_id}/fees",
    ]
    for path in paths:
        assert client.get(path, headers=team.b.headers).status_code == 200, path
        assert client.get(path, headers=team.c.headers).status_code == 404, path

    # Rechnung eines Teammitglieds: Teamleiter darf, Fremder nicht (und nichts
    # wird veraendert).
    denied = client.post(
        f"/api/v1/fees/{a.fee_id}/invoice-status",
        json={"invoice_status": "cancelled"},
        headers=team.c.headers,
    )
    assert denied.status_code == 404
    allowed = client.post(
        f"/api/v1/fees/{a.fee_id}/invoice-status",
        json={"invoice_status": "cancelled"},
        headers=team.b.headers,
    )
    assert allowed.status_code == 200, allowed.text


def test_lists_of_children_follow_the_team_scope(client: TestClient, team: Team) -> None:
    for endpoint in ("interviews", "offers", "placements", "fees", "feedback"):
        url = f"/api/v1/{endpoint}"
        assert len(client.get(url, headers=team.a.headers).json()) == 1, endpoint
        assert len(client.get(url, headers=team.b.headers).json()) == 2, endpoint
        assert len(client.get(url, headers=team.c.headers).json()) == 1, endpoint
        assert len(client.get(url, headers=team.admin.headers).json()) == 3, endpoint
    warranties = client.get("/api/v1/placements/active-warranties", headers=team.b.headers)
    assert len(warranties.json()) == 2


def test_priority_view_respects_team_scope(client: TestClient, team: Team) -> None:
    created = []
    for person, name in ((team.a, "Anna"), (team.b, "Bernd"), (team.c, "Clara")):
        candidate = client.post(
            "/api/v1/candidates",
            json={"first_name": "Prio", "last_name": name},
            headers=person.headers,
        ).json()
        submission = client.post(
            "/api/v1/submissions",
            json={"candidate_id": candidate["id"]},
            headers=person.headers,
        ).json()
        client.patch(
            f"/api/v1/submissions/{submission['id']}/closing-score",
            json={"pain_staerke": 5, "entscheidungsklarheit": 5, "markt_fit": 5},
            headers=person.headers,
        )
        created.append(submission["id"])
    prio_a, prio_b, prio_c = created

    def priority(person: Person) -> set[str]:
        response = client.get("/api/v1/submissions/priority-view", headers=person.headers)
        return {item["id"] for item in response.json()}

    assert prio_a in priority(team.admin)  # Setup trifft die Prioritaetsansicht ueberhaupt
    assert priority(team.b) == {prio_a, prio_b}
    assert priority(team.c) == {prio_c}
    assert priority(team.a) == {prio_a}


def test_reassigning_the_manager_takes_effect_immediately(client: TestClient, team: Team) -> None:
    assert team.a.process_id in _ids(client, team.b)

    client.patch(
        f"/api/v1/users/{team.a.id}", json={"manager_id": team.c.id}, headers=team.admin.headers
    )
    assert team.a.process_id not in _ids(client, team.b)
    assert team.a.process_id in _ids(client, team.c)

    client.patch(
        f"/api/v1/users/{team.a.id}", json={"manager_id": None}, headers=team.admin.headers
    )
    assert team.a.process_id not in _ids(client, team.c)


def test_manager_without_team_lead_role_gets_no_extra_visibility(
    client: TestClient, team: Team, session_factory: sessionmaker[Session]
) -> None:
    """Die Zuordnung wirkt nur, wenn der Zugeordnete role="team_lead" hat."""
    demoted = client.patch(
        f"/api/v1/users/{team.b.id}", json={"role": "member"}, headers=team.admin.headers
    )
    assert demoted.status_code == 200
    assert _ids(client, team.b) == {team.b.process_id}


def test_cockpit_default_scope_follows_the_team(client: TestClient, team: Team) -> None:
    def submissions(person: Person) -> int:
        response = client.get("/api/v1/cockpit?period=quarter", headers=person.headers)
        return int(response.json()["kpis"]["submissions"])

    assert submissions(team.a) == 1
    assert submissions(team.b) == 2
    assert submissions(team.c) == 1
    assert submissions(team.admin) == 3


def test_auth_me_exposes_the_role(client: TestClient, team: Team) -> None:
    me = client.get("/api/v1/auth/me", headers=team.b.headers).json()
    assert me["role"] == "team_lead"
    assert me["is_admin"] is False


class TestUserManagement:
    def test_admin_lists_role_and_manager(self, client: TestClient, team: Team) -> None:
        users = {
            item["email"]: item
            for item in client.get("/api/v1/users", headers=team.admin.headers).json()
        }
        assert users["b@team.example"]["role"] == "team_lead"
        assert users["a@team.example"]["manager_id"] == team.b.id
        assert users["a@team.example"]["manager_name"] == "Bernd Teamleiter"
        assert users["c@team.example"]["manager_id"] is None

    def test_manager_cannot_be_the_user_itself(self, client: TestClient, team: Team) -> None:
        response = client.patch(
            f"/api/v1/users/{team.a.id}", json={"manager_id": team.a.id}, headers=team.admin.headers
        )
        assert response.status_code == 422

    def test_manager_must_exist_and_be_active(self, client: TestClient, team: Team) -> None:
        missing = client.patch(
            f"/api/v1/users/{team.a.id}",
            json={"manager_id": str(uuid.uuid4())},
            headers=team.admin.headers,
        )
        assert missing.status_code == 404

        client.patch(
            f"/api/v1/users/{team.c.id}", json={"is_active": False}, headers=team.admin.headers
        )
        inactive = client.patch(
            f"/api/v1/users/{team.a.id}", json={"manager_id": team.c.id}, headers=team.admin.headers
        )
        assert inactive.status_code == 422

    def test_omitting_manager_id_keeps_it_and_null_clears_it(
        self, client: TestClient, team: Team
    ) -> None:
        kept = client.patch(
            f"/api/v1/users/{team.a.id}", json={"is_active": True}, headers=team.admin.headers
        ).json()
        assert kept["manager_id"] == team.b.id

        cleared = client.patch(
            f"/api/v1/users/{team.a.id}", json={"manager_id": None}, headers=team.admin.headers
        ).json()
        assert cleared["manager_id"] is None
        assert cleared["manager_name"] is None

    def test_admin_cannot_demote_self_via_role_or_is_admin(
        self, client: TestClient, team: Team
    ) -> None:
        for body in ({"role": "member"}, {"role": "team_lead"}, {"is_admin": False}):
            response = client.patch(
                f"/api/v1/users/{team.admin.id}", json=body, headers=team.admin.headers
            )
            assert response.status_code == 422, body
        ok = client.patch(
            f"/api/v1/users/{team.admin.id}", json={"role": "admin"}, headers=team.admin.headers
        )
        assert ok.status_code == 200

    def test_invalid_role_and_contradicting_flags_are_rejected(
        self, client: TestClient, team: Team
    ) -> None:
        bad_role = client.patch(
            f"/api/v1/users/{team.a.id}", json={"role": "boss"}, headers=team.admin.headers
        )
        assert bad_role.status_code == 422
        contradiction = client.patch(
            f"/api/v1/users/{team.a.id}",
            json={"role": "member", "is_admin": True},
            headers=team.admin.headers,
        )
        assert contradiction.status_code == 422

    def test_legacy_is_admin_switch_keeps_working_and_spares_team_leads(
        self, client: TestClient, team: Team
    ) -> None:
        promoted = client.patch(
            f"/api/v1/users/{team.a.id}", json={"is_admin": True}, headers=team.admin.headers
        ).json()
        assert promoted["role"] == "admin"
        demoted = client.patch(
            f"/api/v1/users/{team.a.id}", json={"is_admin": False}, headers=team.admin.headers
        ).json()
        assert demoted["role"] == "member"
        # is_admin=False entzieht nur ein vorhandenes Admin-Recht.
        lead = client.patch(
            f"/api/v1/users/{team.b.id}", json={"is_admin": False}, headers=team.admin.headers
        ).json()
        assert lead["role"] == "team_lead"

    def test_non_admin_cannot_change_roles(self, client: TestClient, team: Team) -> None:
        response = client.patch(
            f"/api/v1/users/{team.a.id}", json={"role": "admin"}, headers=team.b.headers
        )
        assert response.status_code == 403

    def test_audit_log_records_role_and_manager_changes(
        self, client: TestClient, team: Team
    ) -> None:
        client.patch(
            f"/api/v1/users/{team.a.id}",
            json={"role": "team_lead", "manager_id": team.c.id},
            headers=team.admin.headers,
        )
        entries = client.get(
            "/api/v1/audit-logs?entity_type=user", headers=team.admin.headers
        ).json()
        entry = next(
            item
            for item in entries
            if item["action"] == "admin_fields_changed"
            and item["entity_id"] == team.a.id
            and item["new_values"]["role"] == "team_lead"
        )
        assert entry["old_values"]["role"] == "member"
        assert entry["old_values"]["manager_id"] == team.b.id
        assert entry["new_values"]["manager_id"] == team.c.id
