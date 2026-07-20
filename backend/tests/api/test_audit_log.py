import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session, sessionmaker

from cc_crm.core.security import hash_password
from cc_crm.models.user import User
from cc_crm.services.auth import AuthService


@pytest.fixture
def admin_token(session_factory: sessionmaker[Session]) -> str:
    with session_factory() as session:
        session.add(
            User(
                email="admin@commandeurconsulting.de",
                hashed_password=hash_password("x"),
                role="admin",
            )
        )
        session.commit()
        _, token = AuthService(session).login("admin@commandeurconsulting.de", "x")
        return token


def auth_header(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def test_non_admin_cannot_list_audit_logs(client: TestClient) -> None:
    response = client.get("/api/v1/audit-logs")
    assert response.status_code == 403


def test_admin_field_change_is_logged(client: TestClient, admin_token: str) -> None:
    me = client.get("/api/v1/auth/me").json()
    client.patch(
        f"/api/v1/users/{me['id']}", json={"is_admin": True}, headers=auth_header(admin_token)
    )

    logs = client.get("/api/v1/audit-logs", headers=auth_header(admin_token)).json()
    matching = [
        entry
        for entry in logs
        if entry["entity_type"] == "user" and entry["action"] == "admin_fields_changed"
    ]
    assert len(matching) == 1
    assert matching[0]["changed_by"] == "admin@commandeurconsulting.de"
    assert matching[0]["new_values"]["role"] == "admin"


def test_candidate_deletion_is_logged(client: TestClient, admin_token: str) -> None:
    candidate = client.post(
        "/api/v1/candidates", json={"first_name": "Delete", "last_name": "Me"}
    ).json()
    delete_response = client.delete(f"/api/v1/candidates/{candidate['id']}")
    assert delete_response.status_code == 204

    logs = client.get("/api/v1/audit-logs", headers=auth_header(admin_token)).json()
    matching = [
        entry
        for entry in logs
        if entry["entity_type"] == "candidate"
        and entry["action"] == "deleted"
        and entry["entity_id"] == candidate["id"]
    ]
    assert len(matching) == 1
    assert matching[0]["changed_by"] == "test@commandeur.example"


def test_client_deletion_is_logged(client: TestClient, admin_token: str) -> None:
    company = client.post("/api/v1/clients", json={"name": "Kanzlei zum Loeschen"}).json()
    delete_response = client.delete(f"/api/v1/clients/{company['id']}")
    assert delete_response.status_code == 204

    logs = client.get("/api/v1/audit-logs", headers=auth_header(admin_token)).json()
    matching = [
        entry
        for entry in logs
        if entry["entity_type"] == "client_company" and entry["entity_id"] == company["id"]
    ]
    assert len(matching) == 1
    assert matching[0]["action"] == "deleted"


def test_submission_deletion_is_logged(client: TestClient, admin_token: str) -> None:
    candidate = client.post(
        "/api/v1/candidates", json={"first_name": "Sub", "last_name": "Delete"}
    ).json()
    submission = client.post(
        "/api/v1/submissions", json={"candidate_id": candidate["id"]}
    ).json()
    delete_response = client.delete(f"/api/v1/submissions/{submission['id']}")
    assert delete_response.status_code == 204

    logs = client.get("/api/v1/audit-logs", headers=auth_header(admin_token)).json()
    matching = [
        entry
        for entry in logs
        if entry["entity_type"] == "candidate_submission"
        and entry["action"] == "deleted"
        and entry["entity_id"] == submission["id"]
    ]
    assert len(matching) == 1


def test_calendar_feed_token_rotation_is_logged(client: TestClient, admin_token: str) -> None:
    me = client.get("/api/v1/auth/me").json()
    rotate_response = client.post(f"/api/v1/users/{me['id']}/rotate-calendar-feed-token")
    assert rotate_response.status_code == 200

    logs = client.get("/api/v1/audit-logs", headers=auth_header(admin_token)).json()
    matching = [
        entry
        for entry in logs
        if entry["entity_type"] == "user" and entry["action"] == "calendar_feed_token_rotated"
    ]
    assert len(matching) == 1
    assert matching[0]["changed_by"] == "test@commandeur.example"


def test_audit_logs_list_returns_all_tracked_deletions(
    client: TestClient, admin_token: str
) -> None:
    """Chronologische Liste (siehe Punkt 2 des Auftrags: "eine einfache
    Zeitleiste reicht") - bewusst keine strikte Sortier-Assertion auf
    Millisekunden-Ebene, da schnell aufeinanderfolgende Eintraege in Tests
    denselben (sekundengenauen) changed_at-Zeitstempel erhalten koennen."""
    first = client.post(
        "/api/v1/candidates", json={"first_name": "First", "last_name": "Delete"}
    ).json()
    client.delete(f"/api/v1/candidates/{first['id']}")
    second = client.post(
        "/api/v1/candidates", json={"first_name": "Second", "last_name": "Delete"}
    ).json()
    client.delete(f"/api/v1/candidates/{second['id']}")

    logs = client.get("/api/v1/audit-logs", headers=auth_header(admin_token)).json()
    deleted_ids = {entry["entity_id"] for entry in logs if entry["action"] == "deleted"}
    assert {first["id"], second["id"]}.issubset(deleted_ids)
