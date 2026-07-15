from fastapi.testclient import TestClient

from cc_crm.main import create_app


def test_health() -> None:
    client = TestClient(create_app())

    response = client.get("/api/v1/health")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "service": "cc-crm-api",
    }
