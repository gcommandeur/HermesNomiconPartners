# ruff: noqa: F811
"""Vorstellungs-Archiv ueber die API: nur Admins (Nicht-Admins 404), Entfernen nur mit Frist,
Antrag und zweitem Admin, Unveraenderlichkeit unter Postgres, kein Auftauchen anderswo."""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient
from sqlalchemy import select, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session, sessionmaker

from cc_crm.core.config import get_settings
from cc_crm.models.candidate import Candidate
from cc_crm.models.client_company import ClientCompany
from cc_crm.models.contact_person import ContactPerson
from cc_crm.models.mail import MailAccount
from cc_crm.models.presentation_record import PresentationRecord
from cc_crm.models.recruiting import AuditLog
from cc_crm.services.mail_send import MailAttachmentRef, send_mail
from cc_crm.services.presentation_archive import ARCHIVE_PREFIX
from cc_crm.services.storage import document_exists, save_document_bytes
from tests.api.test_team_lead import Person, Team, _make_user, team  # noqa: F401

_KEY = Fernet.generate_key().decode()
BASE = "/api/v1/admin/presentation-archive"
PROFILE = b"PK\x03\x04 Profil Nr. 4711"


@pytest.fixture(autouse=True)
def _env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Iterator[None]:
    monkeypatch.setenv("CC_CRM_MAIL_CREDENTIALS_ENCRYPTION_KEY", _KEY)
    monkeypatch.setenv("CC_CRM_DOCUMENTS_STORAGE_DIR", str(tmp_path / "docs"))
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.fixture
def archived(
    client: TestClient, session_factory: sessionmaker[Session], team: Team  # noqa: F811
) -> dict[str, str]:
    with session_factory() as session:
        account = MailAccount(
            address="b@agentur.example",
            label="B",
            imap_host="i",
            smtp_host="s",
            username="b",
            encrypted_password=Fernet(_KEY.encode()).encrypt(b"geheim").decode(),
        )
        company = ClientCompany(name="Kanzlei Archiv")
        candidate = Candidate(
            first_name="Greta",
            last_name="Archiv",
            consent_received=True,
            candidate_number="4711",
        )
        session.add_all([account, company, candidate])
        session.commit()
        contact = ContactPerson(
            client_company_id=company.id, first_name="K", last_name="K", email="k@kanzlei.example"
        )
        session.add(contact)
        session.commit()
        key = save_document_bytes(
            owner_type="candidate", owner_id=candidate.id, filename="p.docx", content=PROFILE
        )
        send_mail(
            session,
            account=account,
            to_address="k@kanzlei.example",
            subject="Profil Nr. 4711",
            body_text="Anbei das Profil.",
            attachments=[MailAttachmentRef(storage_key=key, filename="Nr_4711.docx")],
            candidate_id=candidate.id,
            contact_person_id=contact.id,
            smtp_sender=lambda *_a: None,
            imap_appender=lambda *_a: True,
        )
        record = session.scalars(select(PresentationRecord)).one()
        return {
            "id": str(record.id),
            "file_key": record.files[0]["storage_key"],
            "candidate_id": str(candidate.id),
        }


def _all_routes(rid: str) -> list[tuple[str, str, dict | None]]:
    return [
        ("GET", BASE, None),
        ("GET", f"{BASE}/{rid}", None),
        ("GET", f"{BASE}/{rid}/files/0", None),
        ("GET", f"{BASE}/{rid}/verify", None),
        ("GET", f"{BASE}/count-without-record", None),
        ("GET", f"{BASE}/removal-requests", None),
        ("PUT", f"{BASE}/{rid}/retention", {"retention_until": "2020-01-01"}),
        ("POST", f"{BASE}/{rid}/removal-requests", {"reason": "Aufbewahrung abgelaufen"}),
    ]


def test_only_admins_see_the_archive(
    client: TestClient, team: Team, archived: dict[str, str]  # noqa: F811
) -> None:
    rid = archived["id"]
    for person in (team.a, team.b):  # member und team_lead
        for method, url, body in _all_routes(rid):
            response = client.request(method, url, json=body, headers=person.headers)
            assert response.status_code == 404, (person.id, method, url, response.text)
    for method, url, body in _all_routes(rid):
        # Der Standard-Client ist ein angemeldeter Nicht-Admin -> ebenfalls 404.
        assert client.request(method, url, json=body).status_code in (401, 403, 404)

    listing = client.get(BASE, headers=team.admin.headers)
    assert listing.status_code == 200
    page = listing.json()
    assert page["total"] == 1
    item = page["items"][0]
    assert item["client_name"] == "Kanzlei Archiv"
    assert item["candidate_number"] == "4711"
    assert item["file_count"] == 1

    detail = client.get(f"{BASE}/{rid}", headers=team.admin.headers).json()
    assert detail["mail_body_text"] == "Anbei das Profil."
    assert detail["files"][0]["filename"] == "Nr_4711.docx"
    download = client.get(f"{BASE}/{rid}/files/0", headers=team.admin.headers)
    assert download.status_code == 200 and download.content == PROFILE
    verify = client.get(f"{BASE}/{rid}/verify", headers=team.admin.headers).json()
    assert verify["all_ok"] is True


def test_archive_appears_nowhere_else(
    client: TestClient,
    team: Team,  # noqa: F811
    archived: dict[str, str],
    session_factory: sessionmaker[Session],
) -> None:
    key = archived["file_key"]
    for person in (team.a, team.admin):
        documents = client.get(
            f"/api/v1/documents?owner_type=candidate&owner_id={archived['candidate_id']}",
            headers=person.headers,
        )
        assert key not in documents.text
        assert "presentation-archive" not in documents.text
    from cc_crm.models.operational import Document

    with session_factory() as session:
        assert session.scalars(select(Document).where(Document.storage_key == key)).all() == []
    assert key.startswith(f"{ARCHIVE_PREFIX}/")
    # Kandidat und Kanzlei zeigen den Eintrag nicht (kein Feld, keine Suche).
    detail = client.get(f"/api/v1/candidates/{archived['candidate_id']}", headers=team.a.headers)
    assert "presentation" not in detail.text.lower()


def test_removal_needs_retention_reason_and_a_second_admin(
    client: TestClient,
    session_factory: sessionmaker[Session],
    team: Team,  # noqa: F811
    archived: dict[str, str],
    tmp_path: Path,
) -> None:
    rid, admin = archived["id"], team.admin.headers
    second = _make_user(session_factory, "gf2@team.example", "admin", "Zweiter Admin")

    # Ohne Frist: abgelehnt. Mit laufender Frist: abgelehnt. Zu kurze Begruendung: abgelehnt.
    body = {"reason": "Aufbewahrungsfrist abgelaufen"}
    first = client.post(f"{BASE}/{rid}/removal-requests", json=body, headers=admin)
    assert first.status_code >= 400
    future = (datetime.now(UTC) + timedelta(days=30)).date().isoformat()
    assert client.put(
        f"{BASE}/{rid}/retention", json={"retention_until": future}, headers=admin
    ).status_code == 200
    running = client.post(f"{BASE}/{rid}/removal-requests", json=body, headers=admin)
    assert running.status_code >= 400
    client.put(f"{BASE}/{rid}/retention", json={"retention_until": "2020-01-01"}, headers=admin)
    short = client.post(f"{BASE}/{rid}/removal-requests", json={"reason": "weg"}, headers=admin)
    assert short.status_code >= 400

    request = client.post(f"{BASE}/{rid}/removal-requests", json=body, headers=admin)
    assert request.status_code == 201, request.text
    request_id = request.json()["id"]
    # Derselbe Admin darf nicht selbst freigeben; Nicht-Admins sehen den Antrag nicht (404).
    same = client.post(f"{BASE}/removal-requests/{request_id}/approve", json={}, headers=admin)
    assert same.status_code >= 400
    assert (
        client.post(
            f"{BASE}/removal-requests/{request_id}/approve", json={}, headers=team.a.headers
        ).status_code
        == 404
    )
    assert document_exists(archived["file_key"])

    approved = client.post(
        f"{BASE}/removal-requests/{request_id}/approve", json={"note": "ok"}, headers=second.headers
    )
    assert approved.status_code == 200, approved.text
    assert approved.json()["status"] == "approved"
    assert not document_exists(archived["file_key"])
    assert client.get(f"{BASE}/{rid}", headers=admin).status_code == 404

    with session_factory() as session:
        entries = session.scalars(
            select(AuditLog).where(AuditLog.entity_type == "presentation_record")
        ).all()
        actions = {e.action for e in entries}
        assert {"presentation_retention_set", "presentation_removal_requested",
                "presentation_removed"} <= actions
        serialized = str([(e.old_values, e.new_values) for e in entries])
    for personal in ("Greta", "k@kanzlei.example", "Anbei das Profil", "4711"):
        assert personal not in serialized


def test_count_endpoint_is_admin_only(client: TestClient, team: Team) -> None:  # noqa: F811
    assert client.get(f"{BASE}/count-without-record", headers=team.a.headers).status_code == 404
    counts = client.get(f"{BASE}/count-without-record", headers=team.admin.headers).json()
    # Die drei Beispielprozesse des Teams stehen bis zur Placement-Stufe, ohne Archiv-Eintrag.
    assert counts == {"presented_submissions": 3, "without_archive_record": 3}


# --- Postgres: der Trigger macht den Eintrag wirklich unveraenderlich ----------------------------


def _is_postgres(session: Session) -> bool:
    return session.get_bind().dialect.name == "postgresql"


def _insert_record(session: Session) -> PresentationRecord:
    record = PresentationRecord(
        sent_at=datetime.now(UTC),
        recipient_emails=["k@kanzlei.example"],
        mail_subject="Betreff",
        mail_body_text="Text",
        files=[],
    )
    session.add(record)
    session.commit()
    return record


def test_postgres_trigger_blocks_update_and_delete(
    session_factory: sessionmaker[Session],
) -> None:
    with session_factory() as session:
        if not _is_postgres(session):
            pytest.skip("Trigger nur unter Postgres")
        record_id = _insert_record(session).id
    for statement in (
        "UPDATE presentation_records SET mail_body_text = 'manipuliert'",
        "UPDATE presentation_records SET recipient_emails = '[]'::json",
        "UPDATE presentation_records SET sent_at = now()",
        "DELETE FROM presentation_records",
    ):
        with session_factory() as session, pytest.raises(DBAPIError) as raised:
            session.execute(text(statement))
            session.commit()
        assert "unveraenderlich" in str(raised.value)
    with session_factory() as session:
        row = session.get(PresentationRecord, record_id)
        assert row is not None and row.mail_body_text == "Text"


def test_postgres_retention_is_the_only_changeable_field_and_delete_needs_the_flag(
    session_factory: sessionmaker[Session],
) -> None:
    with session_factory() as session:
        if not _is_postgres(session):
            pytest.skip("Trigger nur unter Postgres")
        record_id = _insert_record(session).id
    with session_factory() as session:
        session.execute(text("UPDATE presentation_records SET retention_until = '2030-01-01'"))
        session.commit()
        row = session.get(PresentationRecord, record_id)
        assert row is not None and str(row.retention_until) == "2030-01-01"
    with session_factory() as session:
        session.execute(text("SET LOCAL cc_crm.presentation_removal = 'on'"))
        session.execute(text("DELETE FROM presentation_records"))
        session.commit()
        assert session.get(PresentationRecord, record_id) is None
