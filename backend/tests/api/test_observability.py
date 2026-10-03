"""Betriebs-Monitoring: Request-ID, JSON-Logzeile, langsame Anfragen/SQL, /readyz."""

import json
import logging

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from cc_crm.core.observability import (
    JsonFormatter,
    RequestLoggingMiddleware,
    install_slow_sql_logging,
    request_state_var,
)
from cc_crm.infrastructure.database.session import get_db_session
from cc_crm.main import create_app


def _records(caplog: pytest.LogCaptureFixture, name: str) -> list[logging.LogRecord]:
    return [r for r in caplog.records if r.name == name]


def test_every_response_carries_a_request_id_and_a_log_line(
    client: TestClient, caplog: pytest.LogCaptureFixture
) -> None:
    with caplog.at_level(logging.INFO, logger="cc_crm.request"):
        response = client.get("/api/v1/auth/me")
    request_id = response.headers["x-request-id"]
    assert len(request_id) == 32
    (record,) = _records(caplog, "cc_crm.request")
    fields = record.fields  # type: ignore[attr-defined]
    assert fields["method"] == "GET"
    assert fields["path"] == "/api/v1/auth/me"
    assert fields["status"] == 200
    assert fields["duration_ms"] >= 0
    assert fields["user_id"]  # aus get_current_user


def test_incoming_request_id_is_kept_only_if_harmless(
    client: TestClient, caplog: pytest.LogCaptureFixture
) -> None:
    ok = client.get("/api/v1/health", headers={"X-Request-ID": "abc-12345678"})
    assert ok.headers["x-request-id"] == "abc-12345678"
    evil = client.get("/api/v1/health", headers={"X-Request-ID": "x\nforged line"})
    assert evil.headers["x-request-id"] != "x\nforged line"
    assert len(evil.headers["x-request-id"]) == 32


def test_log_line_uses_route_template_not_the_real_path(
    client: TestClient, caplog: pytest.LogCaptureFixture
) -> None:
    with caplog.at_level(logging.INFO, logger="cc_crm.request"):
        client.get("/api/v1/submissions/00000000-0000-0000-0000-000000000000")
    (record,) = _records(caplog, "cc_crm.request")
    assert record.fields["path"] == "/api/v1/submissions/{submission_id}"  # type: ignore[attr-defined]
    assert record.fields["status"] == 404  # type: ignore[attr-defined]


def test_slow_requests_are_logged_as_warning(caplog: pytest.LogCaptureFixture) -> None:
    from fastapi import FastAPI

    app = FastAPI()

    @app.get("/slow")
    def slow() -> dict[str, bool]:
        return {"ok": True}

    app.add_middleware(RequestLoggingMiddleware, slow_seconds=0.0)
    with caplog.at_level(logging.INFO, logger="cc_crm.request"):
        TestClient(app).get("/slow")
    (record,) = _records(caplog, "cc_crm.request")
    assert record.levelno == logging.WARNING
    assert record.getMessage() == "slow_request"


def test_json_formatter_emits_one_json_object_with_request_context() -> None:
    from cc_crm.core.observability import request_id_var

    token = request_id_var.set("rid-12345678")
    try:
        record = logging.LogRecord("x", logging.INFO, __file__, 1, "hallo", None, None)
        record.fields = {"status": 200}  # type: ignore[attr-defined]
        data = json.loads(JsonFormatter().format(record))
    finally:
        request_id_var.reset(token)
    assert data["msg"] == "hallo"
    assert data["level"] == "INFO"
    assert data["request_id"] == "rid-12345678"
    assert data["status"] == 200


def test_slow_sql_is_logged_without_parameter_values(caplog: pytest.LogCaptureFixture) -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    install_slow_sql_logging(engine, threshold_seconds=0.0)
    with caplog.at_level(logging.WARNING, logger="cc_crm.sql"), engine.connect() as connection:
        connection.execute(text("SELECT :secret AS value"), {"secret": "geheime-mail@example.com"})
    (record,) = _records(caplog, "cc_crm.sql")
    statement = record.fields["statement"]  # type: ignore[attr-defined]
    assert "SELECT" in statement
    assert "geheime-mail" not in statement
    assert "geheime-mail" not in record.getMessage()


def test_request_state_is_not_leaked_between_requests(client: TestClient) -> None:
    client.get("/api/v1/auth/me")
    assert request_state_var.get() is None


def _set_schema_version(session_factory: sessionmaker, version: str | None) -> None:
    """SQLite-Tests legen das Schema ueber create_all an (ohne alembic_version);
    im Postgres-Lauf existiert die Tabelle aus den Migrationen."""
    from cc_crm.core.migrations import script_head

    with session_factory() as session:
        session.execute(
            text("CREATE TABLE IF NOT EXISTS alembic_version (version_num VARCHAR(32) NOT NULL)")
        )
        session.execute(text("DELETE FROM alembic_version"))
        session.execute(
            text("INSERT INTO alembic_version (version_num) VALUES (:v)"),
            {"v": version or script_head()},
        )
        session.commit()


def test_readyz_is_ok_when_database_is_at_head(
    client: TestClient, session_factory: sessionmaker
) -> None:
    _set_schema_version(session_factory, None)
    response = client.get("/api/v1/readyz")
    assert response.status_code == 200, response.text
    assert response.json()["status"] == "ok"


def test_readyz_fails_when_schema_is_behind(
    client: TestClient, session_factory: sessionmaker
) -> None:
    _set_schema_version(session_factory, "alt")
    try:
        response = client.get("/api/v1/readyz")
        assert response.status_code == 503
        assert "veraltet" in response.json()["detail"]
    finally:
        _set_schema_version(session_factory, None)


def test_readyz_fails_when_schema_version_is_unknown(
    client: TestClient, session_factory: sessionmaker
) -> None:
    """Auf SQLite (create_all) fehlt alembic_version - dann nicht bereit; im
    Postgres-Lauf wird die Tabelle zum Test geleert."""
    with session_factory() as session:
        session.execute(text("DROP TABLE IF EXISTS alembic_version"))
        session.commit()
    try:
        assert client.get("/api/v1/readyz").status_code == 503
    finally:
        # im Postgres-Lauf wird die Tabelle fuer spaetere Tests gebraucht
        _set_schema_version(session_factory, None)


def test_readyz_fails_when_database_is_unreachable() -> None:
    app = create_app()
    broken = create_engine(
        "postgresql+psycopg://user:pass@127.0.0.1:1/x", connect_args={"connect_timeout": 1}
    )
    factory = sessionmaker(bind=broken)

    def override():  # type: ignore[no-untyped-def]
        with factory() as session:
            yield session

    app.dependency_overrides[get_db_session] = override
    response = TestClient(app).get("/api/v1/readyz")
    assert response.status_code == 503
    assert response.json()["status"] == "error"


def test_sentry_is_only_enabled_with_a_dsn() -> None:
    from cc_crm.core.observability import init_sentry

    assert init_sentry(None, environment="test") is False
    assert init_sentry("", environment="test") is False
    # Eine formal gueltige, aber nicht existierende DSN: init meldet "aktiv", es wird
    # nichts gesendet (kein Ereignis ausgeloest).
    assert init_sentry("https://public@o0.ingest.example.invalid/1", environment="test") is True
    import sentry_sdk

    sentry_sdk.init(dsn=None)  # fuer Folgetests wieder abschalten


def test_startup_migration_can_be_switched_off(monkeypatch: pytest.MonkeyPatch) -> None:
    """CC_CRM_MIGRATE_ON_STARTUP=false: der App-Start fuehrt `alembic upgrade head`
    NICHT aus (Migration laeuft stattdessen als Pre-Deploy-Job, docs/DEPLOYMENT.md).
    Standard bleibt: an."""
    from cc_crm.core.config import get_settings

    calls: list[str] = []
    monkeypatch.setattr("cc_crm.main.ensure_database_at_head", lambda: calls.append("migrate"))

    monkeypatch.setenv("CC_CRM_MIGRATE_ON_STARTUP", "false")
    get_settings.cache_clear()
    with TestClient(create_app()):
        pass
    assert calls == []

    monkeypatch.delenv("CC_CRM_MIGRATE_ON_STARTUP")
    get_settings.cache_clear()
    with TestClient(create_app()):
        pass
    assert calls == ["migrate"]
    get_settings.cache_clear()
