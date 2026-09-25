"""API-Tests fuer POST /mail/send (Auftrag "Versand-Endpoint nachziehen").

Der eigentliche Versand (services/mail_send.py::send_mail) laeuft hier mit
seinen ECHTEN Defaults (kein injizierter smtp_sender/imap_appender) - das
entspricht dem bestehenden Muster fuer POST /mail-accounts/{id}/sync
(services/mail_sync.py::fetch_via_imap), der ebenfalls nur auf Service-Ebene
mit einem Fake-fetcher getestet wird, nicht ueber die API. Die Transport-
logik selbst ist bereits umfassend in tests/services/test_mail_send.py
abgedeckt.

Der einzige Happy-Path-Test hier (test_send_mail_end_to_end_with_attachment)
patcht smtplib/imaplib direkt auf Stdlib-Ebene (kein echter Netzwerkzugriff),
um die Endpoint-Verdrahtung selbst (Account-Aufloesung, Anhang-Laden,
Response-Schema) einmal vollstaendig zu pruefen."""

import smtplib
import uuid
from collections.abc import Iterator

import pytest
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session, sessionmaker

from cc_crm.core.config import get_settings
from cc_crm.models.mail import MailMessage
from cc_crm.models.user import User

_KEY = Fernet.generate_key().decode()

_ACCOUNT_PAYLOAD = {
    "address": "lukas.bergmann@commandeurconsulting.de",
    "label": "Lukas Bergmann",
    "imap_host": "imap.example.com",
    "smtp_host": "smtp.example.com",
    "username": "lukas.bergmann@commandeurconsulting.de",
    "password": "sehr-geheim",
    "default_for_cv_out": True,
}


@pytest.fixture(autouse=True)
def _encryption_key(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    get_settings.cache_clear()
    monkeypatch.setenv("CC_CRM_MAIL_CREDENTIALS_ENCRYPTION_KEY", _KEY)
    yield
    get_settings.cache_clear()


def _make_admin(session_factory: sessionmaker[Session]) -> None:
    """Der Standard-Testnutzer aus conftest ist ein normaler Nutzer - fuer
    das Anlegen eines Postfachs (Admin-only) muss er zum Admin gemacht
    werden. /mail/send selbst ist NICHT admin-only, derselbe Nutzer kann
    danach normal weiter testen."""
    with session_factory() as session:
        user = session.query(User).one()
        user.role = "admin"
        session.commit()


def _create_account(client: TestClient) -> dict:
    response = client.post("/api/v1/mail-accounts", json=_ACCOUNT_PAYLOAD)
    assert response.status_code == 201, response.text
    return response.json()


def _create_candidate(client: TestClient, *, consent_received: bool = True) -> dict:
    response = client.post(
        "/api/v1/candidates",
        json={
            "first_name": "Test",
            "last_name": "Empfaenger",
            "consent_received": consent_received,
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def _create_document(client: TestClient, candidate_id: str, document_type: str) -> dict:
    response = client.post(
        "/api/v1/documents",
        json={
            "owner_type": "candidate",
            "owner_id": candidate_id,
            "document_type": document_type,
            "filename": "Nr. 4456.docx" if document_type != "cv" else "CV_Muster.Test.pdf",
            "storage_key": "candidates/test-doc.docx",
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def test_send_mail_without_any_account_configured_fails(client: TestClient) -> None:
    response = client.post(
        "/api/v1/mail/send",
        json={
            "to_address": "kanzlei@example.com",
            "subject": "Test",
            "body_text": "Hallo",
        },
    )
    assert response.status_code == 422, response.text
    assert "Absender-Postfach" in response.json()["detail"]


def test_send_mail_rejects_unknown_account_id(
    client: TestClient, session_factory: sessionmaker[Session]
) -> None:
    _make_admin(session_factory)
    response = client.post(
        "/api/v1/mail/send",
        json={
            "account_id": "00000000-0000-0000-0000-000000000000",
            "to_address": "kanzlei@example.com",
            "subject": "Test",
            "body_text": "Hallo",
        },
    )
    assert response.status_code == 404, response.text


def test_send_mail_rejects_unknown_attachment_document(
    client: TestClient, session_factory: sessionmaker[Session]
) -> None:
    _make_admin(session_factory)
    _create_account(client)
    response = client.post(
        "/api/v1/mail/send",
        json={
            "to_address": "kanzlei@example.com",
            "subject": "Test",
            "body_text": "Hallo",
            "attachment_document_ids": ["00000000-0000-0000-0000-000000000000"],
        },
    )
    assert response.status_code == 404, response.text


def test_send_mail_rejects_cv_document_as_attachment(
    client: TestClient, session_factory: sessionmaker[Session]
) -> None:
    """Kernregel: ein CV-Dokument darf NIE als Mail-Anhang gehen (siehe
    Modul-Docstring api/v1/mail_send.py)."""
    _make_admin(session_factory)
    _create_account(client)
    candidate = _create_candidate(client)
    cv_document = _create_document(client, candidate["id"], "cv")

    response = client.post(
        "/api/v1/mail/send",
        json={
            "to_address": "kanzlei@example.com",
            "subject": "Test",
            "body_text": "Hallo",
            "attachment_document_ids": [cv_document["id"]],
            "candidate_id": candidate["id"],
        },
    )
    assert response.status_code == 422, response.text
    assert "CV" in response.json()["detail"]


class _FakeSMTP:
    """Minimaler Stdlib-Ersatz - keine echte Netzwerkverbindung."""

    sent: list[tuple[str, str]] = []

    def __init__(self, *_args: object, **_kwargs: object) -> None:
        pass

    def __enter__(self) -> "_FakeSMTP":
        return self

    def __exit__(self, *_exc: object) -> bool:
        return False

    def starttls(self) -> None:
        pass

    def login(self, *_args: object, **_kwargs: object) -> None:
        pass

    def send_message(self, message: object, *, from_addr: str, to_addrs: list[str]) -> None:
        _FakeSMTP.sent.append((from_addr, to_addrs[0]))


class _FakeIMAP:
    def __init__(self, *_args: object, **_kwargs: object) -> None:
        pass

    def __enter__(self) -> "_FakeIMAP":
        return self

    def __exit__(self, *_exc: object) -> bool:
        return False

    def login(self, *_args: object, **_kwargs: object) -> None:
        pass

    def append(self, _folder: str, _flags: str, _date: None, _raw: bytes) -> tuple[str, list]:
        return ("OK", [])


def test_send_mail_end_to_end_with_attachment(
    client: TestClient,
    session_factory: sessionmaker[Session],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Einziger echter Happy-Path-Test - patcht smtplib/imaplib direkt
    (kein echtes Netzwerk), um die Endpoint-Verdrahtung (Account-Aufloesung
    ueber default_for_cv_out, Anhang-Laden, Response-Schema) einmal
    vollstaendig zu pruefen."""
    _FakeSMTP.sent = []
    monkeypatch.setattr(smtplib, "SMTP_SSL", _FakeSMTP)
    monkeypatch.setattr(smtplib, "SMTP", _FakeSMTP)
    import imaplib

    monkeypatch.setattr(imaplib, "IMAP4_SSL", _FakeIMAP)
    monkeypatch.setattr(imaplib, "IMAP4", _FakeIMAP)
    # Keine echte Storage-Anbindung (S3/lokal) noetig - nur der Anhang-Inhalt
    # selbst wird gebraucht, nicht wo er herkommt.
    monkeypatch.setattr("cc_crm.services.mail_send.read_document_bytes", lambda _key: b"Testinhalt")

    _make_admin(session_factory)
    account = _create_account(client)
    candidate = _create_candidate(client)
    profile_document = _create_document(client, candidate["id"], "anonymous_profile")

    response = client.post(
        "/api/v1/mail/send",
        json={
            "to_address": "kanzlei@example.com",
            "to_name": "Muster Kanzlei",
            "subject": "Kandidatenprofil Nr. 4456",
            "body_text": "Anbei das anonyme Profil.",
            "attachment_document_ids": [profile_document["id"]],
            "candidate_id": candidate["id"],
        },
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["mail_account_id"] == account["id"]
    assert body["to_address"] == "kanzlei@example.com"
    assert body["matched_candidate_id"] == candidate["id"]
    assert body["created_activity_id"] is not None
    assert _FakeSMTP.sent == [(account["address"], "kanzlei@example.com")]

    with session_factory() as session:
        stored = session.query(MailMessage).filter_by(id=uuid.UUID(body["id"])).one()
        assert stored.subject == "Kandidatenprofil Nr. 4456"


def _create_mailing_group(client: TestClient, recipients: list[dict]) -> dict:
    response = client.post(
        "/api/v1/mailing-groups",
        json={"name": f"Testgruppe {uuid.uuid4().hex[:8]}", "recipients": recipients},
    )
    assert response.status_code == 201, response.text
    return response.json()


class TestSendBulkMail:
    """POST /mail/send-bulk (Auftrag "M365-Postfach-Integration", Compose-UI
    von der Mailing-Seite aus) - reine Anbindung an services/mail_send.py::
    send_bulk, das bereits umfassend in tests/services/test_mail_send.py
    getestet ist."""

    def test_rejects_unknown_mailing_group(
        self, client: TestClient, session_factory: sessionmaker[Session]
    ) -> None:
        _make_admin(session_factory)
        _create_account(client)
        response = client.post(
            "/api/v1/mail/send-bulk",
            json={
                "mailing_group_id": "00000000-0000-0000-0000-000000000000",
                "subject": "Test",
                "body_text": "Hallo",
            },
        )
        assert response.status_code == 404, response.text

    def test_sends_to_all_recipients_of_the_group(
        self,
        client: TestClient,
        session_factory: sessionmaker[Session],
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        _FakeSMTP.sent = []
        monkeypatch.setattr(smtplib, "SMTP_SSL", _FakeSMTP)
        monkeypatch.setattr(smtplib, "SMTP", _FakeSMTP)
        import imaplib

        monkeypatch.setattr(imaplib, "IMAP4_SSL", _FakeIMAP)
        monkeypatch.setattr(imaplib, "IMAP4", _FakeIMAP)

        _make_admin(session_factory)
        _create_account(client)
        candidate = _create_candidate(client)
        client_response = client.post("/api/v1/clients", json={"name": "Muster Kanzlei"})
        assert client_response.status_code == 201, client_response.text
        client_company = client_response.json()
        group = _create_mailing_group(
            client,
            [
                {
                    "kind": "candidate",
                    "id": candidate["id"],
                    "name": "Test Empfaenger",
                    "email": "kandidat@example.com",
                },
                {
                    "kind": "client",
                    "id": client_company["id"],
                    "name": "Muster Kanzlei",
                    "email": "kanzlei@example.com",
                },
            ],
        )

        response = client.post(
            "/api/v1/mail/send-bulk",
            json={
                "mailing_group_id": group["id"],
                "subject": "Rundmail",
                "body_text": "Hallo zusammen",
            },
        )
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["sent_count"] == 2
        assert body["failed"] == []
        assert {addr for _from, addr in _FakeSMTP.sent} == {
            "kandidat@example.com",
            "kanzlei@example.com",
        }
