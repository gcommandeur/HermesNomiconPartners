import threading

import pytest
from fastapi.testclient import TestClient

from cc_crm.core.rate_limit import MAX_ATTEMPTS, login_rate_limiter
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

    for _ in range(MAX_ATTEMPTS):
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


def test_login_ignores_spoofed_x_forwarded_for_when_cf_connecting_ip_present(
    client: TestClient,
) -> None:
    """Regressionsschutz fuer die auf Produktion bestaetigte Luecke: hinter
    Cloudflare (CF-Connecting-IP gesetzt) darf ein bei jedem Request neu
    erfundener X-Forwarded-For-Wert das Rate-Limit nicht mehr umgehen."""
    client.headers.pop("Authorization", None)
    login_rate_limiter.reset()

    for i in range(MAX_ATTEMPTS):
        response = client.post(
            "/api/v1/auth/login",
            json={"email": TEST_USER_EMAIL, "password": "wrong-password"},
            headers={
                "CF-Connecting-IP": "203.0.113.9",
                "X-Forwarded-For": f"10.13.37.{i}",  # anderer Fake-Wert pro Request
            },
        )
        assert response.status_code == 401

    blocked = client.post(
        "/api/v1/auth/login",
        json={"email": TEST_USER_EMAIL, "password": "wrong-password"},
        headers={
            "CF-Connecting-IP": "203.0.113.9",
            "X-Forwarded-For": "10.13.37.99",  # wieder ein neuer Fake-Wert
        },
    )
    assert blocked.status_code == 429

    login_rate_limiter.reset()


def test_login_rate_limit_triggers_exactly_one_security_alert(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Die Warnung wird in einem eigenen Thread verschickt (siehe
    api/v1/auth.py), daher hier per Event auf den Aufruf warten statt auf
    eine Race-Condition zu vertrauen."""
    client.headers.pop("Authorization", None)
    login_rate_limiter.reset()

    calls: list[dict[str, str]] = []
    fired = threading.Event()

    def fake_send_security_alert(subject: str, body: str, settings: object | None = None) -> None:
        calls.append({"subject": subject, "body": body})
        fired.set()

    monkeypatch.setattr(
        "cc_crm.api.v1.auth.send_security_alert",
        fake_send_security_alert,
    )

    for _ in range(MAX_ATTEMPTS):
        client.post(
            "/api/v1/auth/login",
            json={"email": TEST_USER_EMAIL, "password": "wrong-password"},
        )
    assert fired.wait(timeout=2), "Sicherheitswarnung wurde nicht innerhalb von 2s ausgeloest"
    assert len(calls) == 1
    assert TEST_USER_EMAIL in calls[0]["body"]

    # Weitere Versuche waehrend der Sperre loesen KEINE erneute Warnung aus.
    client.post(
        "/api/v1/auth/login",
        json={"email": TEST_USER_EMAIL, "password": "wrong-password"},
    )
    assert len(calls) == 1

    login_rate_limiter.reset()


def test_logout_invalidates_token(client: TestClient) -> None:
    token = client.headers["Authorization"].removeprefix("Bearer ")

    logout = client.post("/api/v1/auth/logout", headers={"Authorization": f"Bearer {token}"})
    assert logout.status_code == 204

    after_logout = client.get("/api/v1/candidates", headers={"Authorization": f"Bearer {token}"})
    assert after_logout.status_code == 401
