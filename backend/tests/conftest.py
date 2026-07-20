from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from cc_crm.core.security import hash_password
from cc_crm.infrastructure.database.session import get_db_session, register_sqlite_unicode_lower
from cc_crm.main import create_app
from cc_crm.models import Base
from cc_crm.models.user import User
from cc_crm.services.auth import AuthService

TEST_USER_EMAIL = "test@commandeur.example"
TEST_USER_PASSWORD = "test1234"


@pytest.fixture
def session_factory() -> Generator[sessionmaker[Session], None, None]:
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
def client(session_factory: sessionmaker[Session]) -> Generator[TestClient, None, None]:
    app = create_app()

    def override_session() -> Generator[Session, None, None]:
        with session_factory() as session:
            yield session

    app.dependency_overrides[get_db_session] = override_session

    with session_factory() as session:
        session.add(User(email=TEST_USER_EMAIL, hashed_password=hash_password(TEST_USER_PASSWORD)))
        session.commit()
        _, token = AuthService(session).login(TEST_USER_EMAIL, TEST_USER_PASSWORD)

    with TestClient(app) as test_client:
        test_client.headers["Authorization"] = f"Bearer {token}"
        yield test_client
