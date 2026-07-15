from fastapi.testclient import TestClient

from cc_crm.core.rate_limit import login_rate_limiter
from tests.conftest import TEST_USER_EMAIL, TEST_USER_PASSWORD


def test_protected_route_requires_bearer_token(client: TestClient) -> None:
    client.headers.pop("Authorization", None)

    response = client.get("/api/v1/candidates")

    assert response.status_code == 401


def test_login_returns_token_and_me_resolves_user(client: TestClient) -> None:
    client.headers.pop("Authorization", None)

    login = client.post(
        "/api/v1/auth/login",
        json={"email": TEST_USER_EMAIL, "password": TEST_USER_PASSWORD},
    )
    assert login.status_code == 200
    token = login.json()["token"]

    me = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert me.status_code == 200
    assert me.json()["email"] == TEST_USER_EMAIL


def test_login_with_wrong_password_is_rejected(client: TestClient) -> None:
    client.headers.pop("Authorization", None)

    response = client.post(
        "/api/v1/auth/login",
        json={"email": TEST_USER_EMAIL, "password": "wrong-password"},
    )

    assert response.status_code == 401


def test_login_is_rate_limited_after_repeated_failures(client: TestClient) -> None:
    client.headers.pop("Authorization", None)
    login_rate_limiter.reset()

    for _ in range(5):
        response = client.post(
            "/api/v1/auth/login",
            json={"email": TEST_USER_EMAIL, "password": "wrong-password"},
        )
        assert response.status_code == 401

    blocked = client.post(
        "/api/v1/auth/login",
        json={"email": TEST_USER_EMAIL, "password": "wrong-password"},
    )
    assert blocked.status_code == 429

    # Auch ein KORREKTES Passwort wird waehrend der Sperre abgelehnt - das
    # Rate-Limit greift vor jedem Passwort-Vergleich, nicht nur bei falschen
    # Versuchen.
    still_blocked = client.post(
        "/api/v1/auth/login",
        json={"email": TEST_USER_EMAIL, "password": TEST_USER_PASSWORD},
    )
    assert still_blocked.status_code == 429

    login_rate_limiter.reset()


def test_logout_invalidates_token(client: TestClient) -> None:
    token = client.headers["Authorization"].removeprefix("Bearer ")

    logout = client.post("/api/v1/auth/logout", headers={"Authorization": f"Bearer {token}"})
    assert logout.status_code == 204

    after_logout = client.get("/api/v1/candidates", headers={"Authorization": f"Bearer {token}"})
    assert after_logout.status_code == 401
