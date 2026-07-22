from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from cc_crm.services.api_keys import ApiKeyService


def test_api_key_authenticates_like_a_service_account(client: TestClient, session_factory) -> None:
    with session_factory() as session:
        _api_key, raw_key = ApiKeyService(session).create("Bullhorn Sync")

    response = client.get("/api/v1/candidates", headers={"X-API-Key": raw_key})
    assert response.status_code == 200


def test_revoked_api_key_is_rejected(client: TestClient, session_factory: Session) -> None:
    with session_factory() as session:
        api_key, raw_key = ApiKeyService(session).create("Temporary Agent")
        ApiKeyService(session).revoke(api_key.id)

    response = client.get("/api/v1/candidates", headers={"X-API-Key": raw_key})
    assert response.status_code == 401


def test_unknown_api_key_is_rejected(client: TestClient) -> None:
    response = client.get("/api/v1/candidates", headers={"X-API-Key": "ccrm_not-a-real-key"})
    assert response.status_code == 401


def test_api_key_without_expiry_never_expires(client: TestClient, session_factory) -> None:
    with session_factory() as session:
        _api_key, raw_key = ApiKeyService(session).create("No Expiry Agent")

    response = client.get("/api/v1/candidates", headers={"X-API-Key": raw_key})
    assert response.status_code == 200


def test_api_key_with_future_expiry_is_accepted(client: TestClient, session_factory) -> None:
    with session_factory() as session:
        _api_key, raw_key = ApiKeyService(session).create(
            "Future Expiry Agent", expires_at=datetime.now(UTC) + timedelta(days=30)
        )

    response = client.get("/api/v1/candidates", headers={"X-API-Key": raw_key})
    assert response.status_code == 200


def test_api_key_with_past_expiry_is_rejected_like_revoked(
    client: TestClient, session_factory
) -> None:
    with session_factory() as session:
        _api_key, raw_key = ApiKeyService(session).create(
            "Expired Agent", expires_at=datetime.now(UTC) - timedelta(days=1)
        )

    response = client.get("/api/v1/candidates", headers={"X-API-Key": raw_key})
    assert response.status_code == 401
