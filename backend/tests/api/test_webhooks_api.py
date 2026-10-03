"""Webhook-Verwaltung: nur Admin, Geheimnis nur einmal sichtbar."""

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session, sessionmaker

from cc_crm.core.config import get_settings
from cc_crm.infrastructure.database import session as db_session_module
from cc_crm.services import webhooks
from tests.api.test_team_lead import Person, _make_user
from tests.jobs import drain_jobs

_KEY = "S3Jm1m3O4ZVQ0xk0y2oUq2k8x6mQ4oY7Qk0rj0s0yX8="


@pytest.fixture(autouse=True)
def _wire(
    monkeypatch: pytest.MonkeyPatch, session_factory: sessionmaker[Session]
) -> Iterator[None]:
    get_settings.cache_clear()
    monkeypatch.setenv("CC_CRM_MAIL_CREDENTIALS_ENCRYPTION_KEY", _KEY)
    monkeypatch.setattr(db_session_module, "SessionLocal", session_factory)
    monkeypatch.setattr(webhooks, "_resolve_host", lambda host: ["93.184.216.34"])
    yield
    get_settings.cache_clear()


def _admin(session_factory: sessionmaker[Session]) -> Person:
    return _make_user(session_factory, "admin@hooks.example", "admin", "Admin")


def test_webhooks_are_admin_only(client: TestClient) -> None:
    assert client.get("/api/v1/webhooks").status_code == 403
    assert (
        client.post("/api/v1/webhooks", json={"name": "x", "url": "https://a.example/h"}).status_code
        == 403
    )


def test_secret_is_shown_only_once_and_never_listed(
    client: TestClient, session_factory: sessionmaker[Session]
) -> None:
    admin = _admin(session_factory)
    created = client.post(
        "/api/v1/webhooks",
        json={"name": "Zapier", "url": "https://hooks.example/abc", "event_types": ["candidate.*"]},
        headers=admin.headers,
    )
    assert created.status_code == 201, created.text
    body = created.json()
    assert body["secret"].startswith("whsec_")

    listing = client.get("/api/v1/webhooks", headers=admin.headers).json()
    assert [row["name"] for row in listing] == ["Zapier"]
    assert "secret" not in listing[0]
    assert "secret_encrypted" not in listing[0]

    rotated = client.post(f"/api/v1/webhooks/{body['id']}/rotate-secret", headers=admin.headers)
    assert rotated.status_code == 200
    assert rotated.json()["secret"] != body["secret"]


def test_unsafe_urls_are_rejected(
    client: TestClient, session_factory: sessionmaker[Session]
) -> None:
    admin = _admin(session_factory)
    response = client.post(
        "/api/v1/webhooks",
        json={"name": "x", "url": "http://hooks.example/abc"},
        headers=admin.headers,
    )
    assert response.status_code >= 400


def test_test_event_is_delivered_and_logged(
    client: TestClient,
    session_factory: sessionmaker[Session],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sent: list[str] = []
    monkeypatch.setattr(webhooks, "_http_post", lambda url, headers, body: sent.append(body) or 200)
    admin = _admin(session_factory)
    endpoint = client.post(
        "/api/v1/webhooks",
        json={"name": "T", "url": "https://hooks.example/t"},
        headers=admin.headers,
    ).json()

    queued = client.post(f"/api/v1/webhooks/{endpoint['id']}/test", headers=admin.headers)
    assert queued.status_code == 200
    drain_jobs(session_factory)

    deliveries = client.get(f"/api/v1/webhooks/{endpoint['id']}/deliveries", headers=admin.headers)
    assert [(row["event_type"], row["status"]) for row in deliveries.json()] == [
        ("ping", "delivered")
    ]
    assert '"type":"ping"' in sent[0]

    deleted = client.delete(f"/api/v1/webhooks/{endpoint['id']}", headers=admin.headers)
    assert deleted.status_code == 204
    assert client.get("/api/v1/webhooks", headers=admin.headers).json() == []
