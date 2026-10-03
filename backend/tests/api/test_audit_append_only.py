"""Audit-Log ist append-only (Migration f4b7d1a8c2e5, Postgres-Trigger) und die
DSGVO-Anonymisierung schwaerzt die Werte frueherer Aenderungen am Kandidaten.

Der Trigger existiert nur unter Postgres - diese Tests laufen im CI-Job
"backend-postgres" (oder lokal mit CC_CRM_TEST_DATABASE_URL), unter SQLite
werden sie uebersprungen. Das Schwaerzen selbst wird zusaetzlich auch unter
SQLite geprueft (ohne Trigger)."""

import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session, sessionmaker

from cc_crm.core.security import hash_password
from cc_crm.models.recruiting import AuditLog
from cc_crm.models.user import User
from cc_crm.services.auth import AuthService

pytestmark = pytest.mark.filterwarnings("ignore")


def _is_postgres(session: Session) -> bool:
    return session.get_bind().dialect.name == "postgresql"


@pytest.fixture
def admin_headers(session_factory: sessionmaker[Session]) -> dict[str, str]:
    with session_factory() as session:
        session.add(
            User(email="admin@audit.example", hashed_password=hash_password("x"), role="admin")
        )
        session.commit()
        _, token = AuthService(session).login("admin@audit.example", "x")
    return {"Authorization": f"Bearer {token}"}


def _add_audit_row(session: Session) -> uuid.UUID:
    row = AuditLog(
        entity_type="candidate",
        entity_id=uuid.uuid4(),
        action="updated",
        changed_by="x@example.com",
        old_values={"email": "alt@example.com"},
        new_values={"email": "neu@example.com"},
    )
    session.add(row)
    session.commit()
    return row.id


def test_update_and_delete_are_rejected(session_factory: sessionmaker[Session]) -> None:
    with session_factory() as session:
        if not _is_postgres(session):
            pytest.skip("Trigger nur unter Postgres")
        row_id = _add_audit_row(session)
    for statement in (
        "UPDATE audit_logs SET action = 'manipuliert'",
        "UPDATE audit_logs SET old_values = '{}'::json",
        "DELETE FROM audit_logs",
    ):
        with session_factory() as session, pytest.raises(DBAPIError) as raised:
            session.execute(text(statement))
            session.commit()
        assert "append-only" in str(raised.value)
    with session_factory() as session:
        row = session.get(AuditLog, row_id)
        assert row is not None and row.action == "updated"


def test_redaction_flag_only_allows_changing_the_values(
    session_factory: sessionmaker[Session],
) -> None:
    with session_factory() as session:
        if not _is_postgres(session):
            pytest.skip("Trigger nur unter Postgres")
        row_id = _add_audit_row(session)
    # Mit Flag: Werte schwaerzen geht ...
    with session_factory() as session:
        session.execute(text("SET LOCAL cc_crm.audit_redaction = 'on'"))
        session.execute(text("UPDATE audit_logs SET new_values = '{\"email\": \"x\"}'::json"))
        session.commit()
    # ... jede andere Spalte weiterhin nicht, auch nicht mit Flag; Loeschen nie.
    for statement in (
        "UPDATE audit_logs SET action = 'manipuliert'",
        "UPDATE audit_logs SET changed_by = 'jemand-anderes'",
        "DELETE FROM audit_logs",
    ):
        with session_factory() as session, pytest.raises(DBAPIError):
            session.execute(text("SET LOCAL cc_crm.audit_redaction = 'on'"))
            session.execute(text(statement))
            session.commit()
    with session_factory() as session:
        row = session.get(AuditLog, row_id)
        assert row is not None
        assert row.new_values == {"email": "x"}
        assert row.action == "updated"


def test_anonymize_redacts_old_and_new_values_of_earlier_changes(
    client: TestClient,
    session_factory: sessionmaker[Session],
    admin_headers: dict[str, str],
) -> None:
    created = client.post(
        "/api/v1/candidates",
        json={
            "first_name": "Erika",
            "last_name": "Musterfrau",
            "email": "erika.alt@example.com",
            "phone": "+49 170 1234567",
        },
    ).json()
    cid = created["id"]
    changed = client.patch(
        f"/api/v1/candidates/{cid}",
        json={"email": "erika.neu@example.com", "phone": "+49 171 7654321"},
    )
    assert changed.status_code == 200, changed.text

    with session_factory() as session:
        before = session.scalars(
            select(AuditLog).where(AuditLog.entity_id == uuid.UUID(cid))
        ).all()
        assert any("erika.alt@example.com" in str(r.old_values) for r in before)
        count_before = len(before)

    response = client.post(f"/api/v1/candidates/{cid}/anonymize", headers=admin_headers)
    assert response.status_code == 200, response.text

    with session_factory() as session:
        rows = session.scalars(
            select(AuditLog).where(AuditLog.entity_id == uuid.UUID(cid))
        ).all()
        everything = " ".join(f"{r.old_values} {r.new_values}" for r in rows)
        for secret in ("erika.alt", "erika.neu", "170 1234567", "171 7654321"):
            assert secret not in everything
        # Eintraege selbst bleiben (plus der neue "anonymized"-Eintrag), Aktion/Autor unveraendert
        assert len(rows) == count_before + 1
        updated = [r for r in rows if r.action == "updated"]
        assert updated and all(r.changed_by for r in updated)
        assert any(r.action == "anonymized" for r in rows)
        assert any("[entfernt]" in str(r.new_values) for r in updated)
