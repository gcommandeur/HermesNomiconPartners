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


def test_non_admin_cannot_list_users(client: TestClient) -> None:
    response = client.get("/api/v1/users")
    assert response.status_code == 403


def test_admin_can_list_users_without_feed_tokens(client: TestClient, admin_token: str) -> None:
    response = client.get("/api/v1/users", headers=auth_header(admin_token))
    assert response.status_code == 200
    body = response.json()
    assert len(body) >= 2
    for user in body:
        assert "calendar_feed_token" not in user
        assert "is_admin" in user
        assert "is_active" in user


def test_admin_can_toggle_other_users_admin_flag(client: TestClient, admin_token: str) -> None:
    me = client.get("/api/v1/auth/me").json()

    response = client.patch(
        f"/api/v1/users/{me['id']}",
        json={"is_admin": True},
        headers=auth_header(admin_token),
    )
    assert response.status_code == 200
    assert response.json()["is_admin"] is True


def test_admin_cannot_demote_self(client: TestClient, admin_token: str) -> None:
    admin_me = client.get("/api/v1/auth/me", headers=auth_header(admin_token)).json()

    response = client.patch(
        f"/api/v1/users/{admin_me['id']}",
        json={"is_admin": False},
        headers=auth_header(admin_token),
    )
    assert response.status_code == 422
    # Sicherstellen, dass der Admin-Status wirklich unveraendert blieb.
    still_admin = client.get("/api/v1/auth/me", headers=auth_header(admin_token)).json()
    assert still_admin["is_admin"] is True


def test_owner_can_rotate_own_feed_token(client: TestClient) -> None:
    before = client.get("/api/v1/auth/me").json()
    response = client.post(f"/api/v1/users/{before['id']}/rotate-calendar-feed-token")
    assert response.status_code == 200
    new_token = response.json()["calendar_feed_token"]
    assert new_token != before["calendar_feed_token"]

    after = client.get("/api/v1/auth/me").json()
    assert after["calendar_feed_token"] == new_token


def test_non_admin_cannot_rotate_others_feed_token(
    client: TestClient, admin_token: str
) -> None:
    admin_me = client.get("/api/v1/auth/me", headers=auth_header(admin_token)).json()
    response = client.post(f"/api/v1/users/{admin_me['id']}/rotate-calendar-feed-token")
    assert response.status_code == 403
