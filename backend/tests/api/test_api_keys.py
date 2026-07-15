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
