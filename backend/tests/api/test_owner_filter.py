import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session, sessionmaker

from cc_crm.core.security import hash_password
from cc_crm.models.user import User
from cc_crm.services.auth import AuthService


@pytest.fixture
def second_user_token(session_factory: sessionmaker[Session]) -> str:
    with session_factory() as session:
        session.add(User(email="colleague@commandeur.example", hashed_password=hash_password("x")))
        session.commit()
        _, token = AuthService(session).login("colleague@commandeur.example", "x")
        return token


def auth_header(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def test_candidate_owner_defaults_to_current_user(client: TestClient) -> None:
    me = client.get("/api/v1/auth/me").json()
    created = client.post(
        "/api/v1/candidates", json={"first_name": "Owner", "last_name": "Default"}
    )
    assert created.status_code == 201
    assert created.json()["owner_user_id"] == me["id"]


def test_candidate_owner_explicitly_settable_and_changeable(
    client: TestClient, second_user_token: str
) -> None:
    """Default ist der eingeloggte Nutzer, aber im Formular aenderbar - ein
    explizit gesetzter owner_user_id (z.B. ein Kollege) darf NICHT vom
    Default-Mechanismus ueberschrieben werden."""
    colleague = client.get("/api/v1/auth/me", headers=auth_header(second_user_token)).json()

    created = client.post(
        "/api/v1/candidates",
        json={
            "first_name": "Explicit",
            "last_name": "Owner",
            "owner_user_id": colleague["id"],
        },
    )
    assert created.status_code == 201
    assert created.json()["owner_user_id"] == colleague["id"]


def test_candidate_owner_filter_is_convenience_not_visibility(
    client: TestClient, second_user_token: str
) -> None:
    """owner_user_id-Filter darf NUR die Trefferliste einschraenken, wenn
    explizit gesetzt - ohne ihn muss jeder Nutzer weiterhin ALLE Kandidaten
    sehen (kein Kalender-artiges Sichtbarkeits-Verhalten)."""
    me = client.get("/api/v1/auth/me").json()
    colleague = client.get("/api/v1/auth/me", headers=auth_header(second_user_token)).json()

    client.post("/api/v1/candidates", json={"first_name": "Mine", "last_name": "A"})
    client.post(
        "/api/v1/candidates",
        json={"first_name": "Colleague", "last_name": "B"},
        headers=auth_header(second_user_token),
    )

    # Ohne Filter: beide Nutzer sehen BEIDE Kandidaten.
    all_as_me = client.get("/api/v1/candidates").json()
    assert all_as_me["total_count"] == 2
    all_as_colleague = client.get(
        "/api/v1/candidates", headers=auth_header(second_user_token)
    ).json()
    assert all_as_colleague["total_count"] == 2

    # Mit Filter: nur der jeweils eigene Kandidat.
    mine_only = client.get(f"/api/v1/candidates?owner_user_id={me['id']}").json()
    assert mine_only["total_count"] == 1
    assert mine_only["items"][0]["first_name"] == "Mine"

    colleagues_only = client.get(f"/api/v1/candidates?owner_user_id={colleague['id']}").json()
    assert colleagues_only["total_count"] == 1
    assert colleagues_only["items"][0]["first_name"] == "Colleague"


def test_client_owner_filter(client: TestClient, second_user_token: str) -> None:
    me = client.get("/api/v1/auth/me").json()
    client.post("/api/v1/clients", json={"name": "Kanzlei A"})
    client.post(
        "/api/v1/clients", json={"name": "Kanzlei B"}, headers=auth_header(second_user_token)
    )

    all_clients = client.get("/api/v1/clients").json()
    assert all_clients["total_count"] == 2

    mine_only = client.get(f"/api/v1/clients?owner_user_id={me['id']}").json()
    assert mine_only["total_count"] == 1
    assert mine_only["items"][0]["name"] == "Kanzlei A"


def test_submission_owner_filter(client: TestClient, second_user_token: str) -> None:
    me = client.get("/api/v1/auth/me").json()
    candidate = client.post(
        "/api/v1/candidates", json={"first_name": "Sub", "last_name": "Owner"}
    ).json()

    created = client.post(
        "/api/v1/submissions", json={"candidate_id": candidate["id"]}
    )
    assert created.status_code == 201
    assert created.json()["owner_user_id"] == me["id"]

    submissions = client.get("/api/v1/submissions").json()
    assert submissions["total_count"] == 1

    mine_only = client.get(f"/api/v1/submissions?owner_user_id={me['id']}").json()
    assert mine_only["total_count"] == 1

    colleague = client.get("/api/v1/auth/me", headers=auth_header(second_user_token)).json()
    others_only = client.get(f"/api/v1/submissions?owner_user_id={colleague['id']}").json()
    assert others_only["total_count"] == 0


def test_task_owner_filter(client: TestClient, second_user_token: str) -> None:
    me = client.get("/api/v1/auth/me").json()
    created = client.post("/api/v1/tasks", json={"title": "Nachfassen"})
    assert created.status_code == 201
    assert created.json()["owner_user_id"] == me["id"]

    colleague = client.get("/api/v1/auth/me", headers=auth_header(second_user_token)).json()
    client.post(
        "/api/v1/tasks", json={"title": "Andere Aufgabe"}, headers=auth_header(second_user_token)
    )

    all_tasks = client.get("/api/v1/tasks").json()
    assert len(all_tasks) == 2

    mine_only = client.get(f"/api/v1/tasks?owner_user_id={me['id']}").json()
    assert len(mine_only) == 1
    assert mine_only[0]["title"] == "Nachfassen"

    colleagues_only = client.get(f"/api/v1/tasks?owner_user_id={colleague['id']}").json()
    assert len(colleagues_only) == 1
    assert colleagues_only[0]["title"] == "Andere Aufgabe"
