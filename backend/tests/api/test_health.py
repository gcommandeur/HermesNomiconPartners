from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from cc_crm.infrastructure.database.session import get_db_session
from cc_crm.main import create_app


def test_health() -> None:
    client = TestClient(create_app())

    response = client.get("/api/v1/health")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "service": "cc-crm-api",
        "detail": None,
    }


def test_health_reports_error_when_database_unreachable() -> None:
    """Simuliert eine kaputte DB-Verbindung ueber eine echte, aber garantiert
    nicht erreichbare Postgres-URL (Port 1 auf localhost - kein Dienst lauscht
    dort, die Verbindung schlaegt sofort fehl statt zu haengen) - kein
    gemocktes execute(), sondern ein echter Verbindungsfehler durch die
    gesamte Session-Schicht."""
    app = create_app()
    broken_engine = create_engine(
        "postgresql+psycopg://user:pass@127.0.0.1:1/doesnotexist",
        connect_args={"connect_timeout": 1},
    )
    broken_session_factory = sessionmaker(bind=broken_engine)

    def override_get_db_session():  # type: ignore[no-untyped-def]
        with broken_session_factory() as session:
            yield session

    app.dependency_overrides[get_db_session] = override_get_db_session
    client = TestClient(app)

    response = client.get("/api/v1/health")

    assert response.status_code == 503
    body = response.json()
    assert body["status"] == "error"
    assert body["service"] == "cc-crm-api"
    assert body["detail"]
