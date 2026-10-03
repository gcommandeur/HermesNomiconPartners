import os
from collections.abc import Generator

# VOR dem Import der App: der TestClient fuehrt den Lifespan aus - ein mitlaufender
# Worker-Thread wuerde parallel auf der geteilten Test-Verbindung arbeiten (Flackern).
# Tests arbeiten Jobs gezielt per tests/jobs.py::drain_jobs ab.
os.environ.setdefault("CC_CRM_EMBEDDED_WORKER", "false")

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from cc_crm.core.security import hash_password
from cc_crm.infrastructure.database import session as db_session_module
from cc_crm.infrastructure.database.session import get_db_session, register_sqlite_unicode_lower
from cc_crm.main import create_app
from cc_crm.models import Base
from cc_crm.models.user import User
from cc_crm.services.auth import AuthService

TEST_USER_EMAIL = "test@commandeur.example"
TEST_USER_PASSWORD = "test1234"


@pytest.fixture(scope="session", autouse=True)
def _fast_password_hashing() -> Generator[None, None, None]:
    """PBKDF2 mit 260.000 Runden pro Hash/Pruefung war der Hauptgrund fuer die
    ca. 10 Minuten Laufzeit der Suite (fast jeder Test legt Nutzer an und meldet
    sie an). In Tests genuegt eine kleine Rundenzahl; hash_password() und
    verify_password() lesen die Konstante bei jedem Aufruf, beide sind also
    konsistent. Produktionscode bleibt unveraendert."""
    from cc_crm.core import security

    original = security._PBKDF2_ITERATIONS
    security._PBKDF2_ITERATIONS = 1_000
    yield
    security._PBKDF2_ITERATIONS = original


# Optionaler Postgres-Lauf (CI-Job "backend-postgres", lokal auf Abruf): zeigt
# CC_CRM_TEST_DATABASE_URL auf eine WEGWERF-Datenbank, laeuft die ganze Suite
# gegen echtes Postgres statt gegen SQLite im Speicher. Das Schema entsteht
# EINMAL pro Lauf ueber `alembic upgrade head` (testet zugleich die
# Migrationen), nach jedem Test werden alle Tabellen geleert. Ohne die Variable
# bleibt alles wie bisher (SQLite).
POSTGRES_TEST_URL = os.environ.get("CC_CRM_TEST_DATABASE_URL")


def _assert_disposable(url: str) -> None:
    """TRUNCATE auf der falschen Datenbank waere katastrophal - nur Datenbanken,
    deren Name "test" enthaelt, werden akzeptiert."""
    database = url.rsplit("/", 1)[-1].split("?")[0]
    if "test" not in database:
        raise RuntimeError(
            f"CC_CRM_TEST_DATABASE_URL zeigt auf '{database}' - der Name muss 'test' enthalten, "
            "weil die Tabellen nach jedem Test geleert werden."
        )


@pytest.fixture(scope="session")
def _postgres_engine() -> Generator[Engine | None, None, None]:
    if not POSTGRES_TEST_URL:
        yield None
        return
    _assert_disposable(POSTGRES_TEST_URL)
    from cc_crm.core.config import get_settings

    get_settings.cache_clear()
    if get_settings().resolved_database_url != POSTGRES_TEST_URL:
        raise RuntimeError(
            "Im Postgres-Lauf muss CC_CRM_DATABASE_URL gleich CC_CRM_TEST_DATABASE_URL sein "
            "(sonst migriert der App-Start eine andere Datenbank)."
        )
    from cc_crm.core.migrations import ensure_database_at_head

    engine = create_engine(POSTGRES_TEST_URL, pool_pre_ping=True)
    with engine.begin() as connection:  # sauberer Start: frisches Schema aus den Migrationen
        connection.execute(text("DROP SCHEMA public CASCADE"))
        connection.execute(text("CREATE SCHEMA public"))
    ensure_database_at_head()
    yield engine
    engine.dispose()


def _truncate_all(engine: Engine) -> None:
    """Leert nur die Tabellen, die Zeilen enthalten (eine Abfrage statt 60
    TRUNCATEs pro Test - TRUNCATE ist in Postgres vergleichsweise teuer)."""
    tables = [name for name in Base.metadata.tables if name != "alembic_version"]
    if not tables:
        return
    probe = " UNION ALL ".join(
        f"SELECT '{name}' AS t WHERE EXISTS (SELECT 1 FROM \"{name}\")" for name in tables
    )
    with engine.begin() as connection:
        # Ein Test, der eine Session offen laesst ("idle in transaction"), haelt
        # Sperren und liesse TRUNCATE endlos warten (unter SQLite gibt es das
        # Problem nicht). Solche liegengebliebenen Verbindungen beenden - der
        # Test ist an dieser Stelle laengst vorbei.
        connection.execute(
            text(
                "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
                "WHERE datname = current_database() AND pid <> pg_backend_pid() "
                "AND state = 'idle in transaction'"
            )
        )
        connection.execute(text("SET LOCAL lock_timeout = '30s'"))
        filled = [row[0] for row in connection.execute(text(probe))]
        if filled:
            quoted = ", ".join(f'"{name}"' for name in filled)
            connection.execute(text(f"TRUNCATE {quoted} RESTART IDENTITY CASCADE"))


@pytest.fixture
def session_factory(
    _postgres_engine: Engine | None,
) -> Generator[sessionmaker[Session], None, None]:
    if _postgres_engine is not None:
        _truncate_all(_postgres_engine)
        factory = sessionmaker(bind=_postgres_engine, autoflush=False, expire_on_commit=False)
        yield factory
        _truncate_all(_postgres_engine)
        return

    engine: Engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    @event.listens_for(engine, "connect")
    def enable_sqlite_foreign_keys(
        dbapi_connection: object,
        _connection_record: object,
    ) -> None:
        cursor = dbapi_connection.cursor()  # type: ignore[attr-defined]
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    register_sqlite_unicode_lower(engine)

    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    yield factory
    Base.metadata.drop_all(engine)
    engine.dispose()


@pytest.fixture
def client(
    session_factory: sessionmaker[Session], monkeypatch: pytest.MonkeyPatch
) -> Generator[TestClient, None, None]:
    app = create_app()

    def override_session() -> Generator[Session, None, None]:
        with session_factory() as session:
            yield session

    app.dependency_overrides[get_db_session] = override_session
    # core/rate_limit.py oeffnet seine eigenen Sessions ausserhalb von
    # FastAPIs Dependency-Injection direkt ueber SessionLocal (gleiches
    # Muster wie Hintergrundjobs, siehe test_cv_preview_scan_jobs.py) - ohne
    # dies wuerden Rate-Limit-Tests in die echte lokale Dev-DB schreiben
    # statt in diese isolierte Test-Engine.
    monkeypatch.setattr(db_session_module, "SessionLocal", session_factory)

    with session_factory() as session:
        session.add(User(email=TEST_USER_EMAIL, hashed_password=hash_password(TEST_USER_PASSWORD)))
        session.commit()
        _, token = AuthService(session).login(TEST_USER_EMAIL, TEST_USER_PASSWORD)

    with TestClient(app) as test_client:
        test_client.headers["Authorization"] = f"Bearer {token}"
        yield test_client
