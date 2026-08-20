"""API-Tests fuer die Postfach-Verwaltung.

Schwerpunkt: das Passwort darf NIE ueber die API zurueckkommen, und die
Endpunkte sind durchgaengig Admin-only (dort liegen die Zugangsdaten aller
Firmen-Postfaecher).
"""

import uuid
from collections.abc import Iterator
from datetime import UTC, datetime

import pytest
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session, sessionmaker

from cc_crm.core.config import get_settings
from cc_crm.models.candidate import Candidate
from cc_crm.models.client_company import ClientCompany
from cc_crm.models.contact_person import ContactPerson
from cc_crm.models.enums import MailDirection, MailMatchStatus
from cc_crm.models.mail import MailAccount, MailMessage
from cc_crm.models.user import User
from cc_crm.services.mail_credentials import decrypt_password

_KEY = Fernet.generate_key().decode()

_PAYLOAD = {
    "address": "info@commandeurconsulting.de",
    "label": "info-linkedin",
    "imap_host": "imap.example.com",
    "smtp_host": "smtp.example.com",
    "username": "info@commandeurconsulting.de",
    "password": "sehr-geheim",
}


@pytest.fixture(autouse=True)
def _encryption_key(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    get_settings.cache_clear()
    monkeypatch.setenv("CC_CRM_MAIL_CREDENTIALS_ENCRYPTION_KEY", _KEY)
    yield
    get_settings.cache_clear()


def _make_admin(session_factory: sessionmaker[Session]) -> None:
    """Der Standard-Testnutzer aus conftest ist ein normaler Nutzer - fuer
    die Admin-Endpunkte muss er zum Admin gemacht werden."""
    with session_factory() as session:
        user = session.query(User).one()
        user.role = "admin"
        session.commit()


class TestPasswordNeverLeaves:
    def test_create_response_contains_no_password_field(
        self, client: TestClient, session_factory: sessionmaker[Session]
    ) -> None:
        _make_admin(session_factory)

        response = client.post("/api/v1/mail-accounts", json=_PAYLOAD)

        assert response.status_code == 201
        body = response.json()
        assert "password" not in body
        assert "encrypted_password" not in body
        # Auch nicht irgendwo im Rohtext der Antwort.
        assert "sehr-geheim" not in response.text

    def test_list_response_contains_no_password(
        self, client: TestClient, session_factory: sessionmaker[Session]
    ) -> None:
        _make_admin(session_factory)
        client.post("/api/v1/mail-accounts", json=_PAYLOAD)

        response = client.get("/api/v1/mail-accounts")

        assert response.status_code == 200
        assert "sehr-geheim" not in response.text
        assert "password" not in response.json()[0]

    def test_password_is_stored_encrypted_and_decryptable(
        self, client: TestClient, session_factory: sessionmaker[Session]
    ) -> None:
        _make_admin(session_factory)
        client.post("/api/v1/mail-accounts", json=_PAYLOAD)

        with session_factory() as session:
            from cc_crm.models.mail import MailAccount

            account = session.query(MailAccount).one()
            assert account.encrypted_password != "sehr-geheim"
            assert decrypt_password(account.encrypted_password) == "sehr-geheim"


class TestAdminOnly:
    def test_non_admin_cannot_list_accounts(self, client: TestClient) -> None:
        """Standard-Testnutzer ist kein Admin - der Zugriff muss scheitern."""
        response = client.get("/api/v1/mail-accounts")
        assert response.status_code == 403

    def test_non_admin_cannot_create_account(self, client: TestClient) -> None:
        response = client.post("/api/v1/mail-accounts", json=_PAYLOAD)
        assert response.status_code == 403


class TestDefaultForCvOut:
    def test_setting_a_new_default_clears_the_previous_one(
        self, client: TestClient, session_factory: sessionmaker[Session]
    ) -> None:
        """Nur EIN Postfach darf CV-OUT-Standard sein - sonst waere die
        Absenderauswahl beim Versand nicht eindeutig."""
        _make_admin(session_factory)
        first = client.post(
            "/api/v1/mail-accounts", json={**_PAYLOAD, "default_for_cv_out": True}
        ).json()
        second = client.post(
            "/api/v1/mail-accounts",
            json={
                **_PAYLOAD,
                "address": "lukas.bergmann@commandeurconsulting.de",
                "label": "lukas",
                "default_for_cv_out": True,
            },
        ).json()

        accounts = {a["id"]: a for a in client.get("/api/v1/mail-accounts").json()}

        assert accounts[second["id"]]["default_for_cv_out"] is True
        assert accounts[first["id"]]["default_for_cv_out"] is False

    def test_duplicate_address_is_rejected(
        self, client: TestClient, session_factory: sessionmaker[Session]
    ) -> None:
        _make_admin(session_factory)
        client.post("/api/v1/mail-accounts", json=_PAYLOAD)

        response = client.post("/api/v1/mail-accounts", json=_PAYLOAD)

        # 422 laut projektweitem BusinessRuleError-Handler (error_handlers.py).
        assert response.status_code == 422
        assert "bereits verbunden" in response.json()["detail"]


class TestUpdateAndDelete:
    def test_update_without_password_keeps_the_stored_one(
        self, client: TestClient, session_factory: sessionmaker[Session]
    ) -> None:
        """Wichtig fuers Bearbeiten in der Maske: wer nur den Port aendert,
        darf nicht das Passwort verlieren."""
        _make_admin(session_factory)
        created = client.post("/api/v1/mail-accounts", json=_PAYLOAD).json()

        response = client.patch(
            f"/api/v1/mail-accounts/{created['id']}", json={"imap_port": 143}
        )

        assert response.status_code == 200
        assert response.json()["imap_port"] == 143
        with session_factory() as session:
            from cc_crm.models.mail import MailAccount

            account = session.query(MailAccount).one()
            assert decrypt_password(account.encrypted_password) == "sehr-geheim"

    def test_delete_removes_the_account(
        self, client: TestClient, session_factory: sessionmaker[Session]
    ) -> None:
        _make_admin(session_factory)
        created = client.post("/api/v1/mail-accounts", json=_PAYLOAD).json()

        assert client.delete(f"/api/v1/mail-accounts/{created['id']}").status_code == 204
        assert client.get("/api/v1/mail-accounts").json() == []


class TestMessageList:
    """GET /mail-accounts/{id}/messages - nachvollziehbare Liste der
    eingelesenen Mails (siehe schemas/mail.py::MailMessageRead)."""

    def _account_id(self, client: TestClient) -> str:
        return str(client.post("/api/v1/mail-accounts", json=_PAYLOAD).json()["id"])

    def test_non_admin_cannot_list_messages(self, client: TestClient) -> None:
        response = client.get(f"/api/v1/mail-accounts/{'0' * 8}-0000-0000-0000-{'0' * 12}/messages")
        assert response.status_code == 403

    def test_unknown_account_returns_404(
        self, client: TestClient, session_factory: sessionmaker[Session]
    ) -> None:
        _make_admin(session_factory)
        response = client.get(f"/api/v1/mail-accounts/{'0' * 8}-0000-0000-0000-{'0' * 12}/messages")
        assert response.status_code == 404

    def test_matched_message_carries_resolved_candidate_name(
        self, client: TestClient, session_factory: sessionmaker[Session]
    ) -> None:
        _make_admin(session_factory)
        account_id = self._account_id(client)

        with session_factory() as session:
            candidate = Candidate(first_name="Anna", last_name="Müller")
            session.add(candidate)
            session.flush()
            session.add(
                MailMessage(
                    mail_account_id=uuid.UUID(account_id),
                    message_id="msg-1@example.com",
                    direction=MailDirection.INBOUND,
                    from_name="Anna Müller",
                    from_address="anna.mueller@example.com",
                    subject="Rückfrage",
                    received_at=datetime(2026, 8, 1, tzinfo=UTC),
                    match_status=MailMatchStatus.MATCHED,
                    matched_candidate_id=candidate.id,
                )
            )
            session.commit()

        response = client.get(f"/api/v1/mail-accounts/{account_id}/messages")

        assert response.status_code == 200
        body = response.json()
        assert len(body) == 1
        assert body[0]["match_status"] == "matched"
        assert body[0]["matched_candidate_name"] == "Anna Müller"
        assert body[0]["matched_candidate_id"] == str(candidate.id)

    def test_pending_review_message_has_no_link_but_keeps_sender_name(
        self, client: TestClient, session_factory: sessionmaker[Session]
    ) -> None:
        """Kernfall: LinkedIn-Mail ohne Namenstreffer - kein Link, aber der
        Absendername muss sichtbar bleiben, damit klar ist, wer manuelles
        Eingreifen braucht."""
        _make_admin(session_factory)
        account_id = self._account_id(client)

        with session_factory() as session:
            session.add(
                MailMessage(
                    mail_account_id=uuid.UUID(account_id),
                    message_id="msg-2@example.com",
                    direction=MailDirection.INBOUND,
                    from_name="Wildfremde Person",
                    from_address="hit-reply@linkedin.com",
                    subject="Message replied: Rolle",
                    received_at=datetime(2026, 8, 1, tzinfo=UTC),
                    match_status=MailMatchStatus.PENDING_REVIEW,
                    is_linkedin=True,
                )
            )
            session.commit()

        response = client.get(f"/api/v1/mail-accounts/{account_id}/messages")

        body = response.json()
        assert body[0]["match_status"] == "pending_review"
        assert body[0]["from_name"] == "Wildfremde Person"
        assert body[0]["matched_candidate_id"] is None

    def test_matched_contact_person_carries_its_client_company_id(
        self, client: TestClient, session_factory: sessionmaker[Session]
    ) -> None:
        """Kontaktpersonen haben keine eigene Detailseite - die Oberflaeche
        verlinkt stattdessen zu ihrer Kanzlei, deshalb muss die Kanzlei-ID
        mitkommen."""
        _make_admin(session_factory)
        account_id = self._account_id(client)

        with session_factory() as session:
            company = ClientCompany(name="Kanzlei Muster")
            session.add(company)
            session.flush()
            contact = ContactPerson(
                first_name="Bernd",
                last_name="Schmidt",
                email="b.schmidt@kanzlei-muster.de",
                client_company_id=company.id,
            )
            session.add(contact)
            session.flush()
            session.add(
                MailMessage(
                    mail_account_id=uuid.UUID(account_id),
                    message_id="msg-3@example.com",
                    direction=MailDirection.INBOUND,
                    from_address="b.schmidt@kanzlei-muster.de",
                    subject="Rückfrage",
                    received_at=datetime(2026, 8, 1, tzinfo=UTC),
                    match_status=MailMatchStatus.MATCHED,
                    matched_contact_person_id=contact.id,
                )
            )
            session.commit()
            company_id = str(company.id)

        response = client.get(f"/api/v1/mail-accounts/{account_id}/messages")

        body = response.json()
        assert body[0]["matched_contact_person_name"] == "Bernd Schmidt"
        assert body[0]["matched_contact_person_client_company_id"] == company_id

    def test_filter_by_match_status(
        self, client: TestClient, session_factory: sessionmaker[Session]
    ) -> None:
        _make_admin(session_factory)
        account_id = self._account_id(client)

        with session_factory() as session:
            session.add_all(
                [
                    MailMessage(
                        mail_account_id=uuid.UUID(account_id),
                        message_id="matched@x",
                        direction=MailDirection.INBOUND,
                        received_at=datetime(2026, 8, 1, tzinfo=UTC),
                        match_status=MailMatchStatus.MATCHED,
                    ),
                    MailMessage(
                        mail_account_id=uuid.UUID(account_id),
                        message_id="unmatched@x",
                        direction=MailDirection.INBOUND,
                        received_at=datetime(2026, 8, 1, tzinfo=UTC),
                        match_status=MailMatchStatus.UNMATCHED,
                    ),
                ]
            )
            session.commit()

        response = client.get(
            f"/api/v1/mail-accounts/{account_id}/messages", params={"match_status": "unmatched"}
        )

        body = response.json()
        assert len(body) == 1
        assert body[0]["match_status"] == "unmatched"

    def test_filter_by_multiple_match_statuses(
        self, client: TestClient, session_factory: sessionmaker[Session]
    ) -> None:
        """Frontend-Default ('alles außer Unbekannt') braucht mehrere Werte
        in einer Anfrage statt zwei Seiten zusammenzufuehren."""
        _make_admin(session_factory)
        account_id = self._account_id(client)

        with session_factory() as session:
            session.add_all(
                [
                    MailMessage(
                        mail_account_id=uuid.UUID(account_id),
                        message_id="matched@x",
                        direction=MailDirection.INBOUND,
                        received_at=datetime(2026, 8, 1, tzinfo=UTC),
                        match_status=MailMatchStatus.MATCHED,
                    ),
                    MailMessage(
                        mail_account_id=uuid.UUID(account_id),
                        message_id="pending@x",
                        direction=MailDirection.INBOUND,
                        received_at=datetime(2026, 8, 2, tzinfo=UTC),
                        match_status=MailMatchStatus.PENDING_REVIEW,
                    ),
                    MailMessage(
                        mail_account_id=uuid.UUID(account_id),
                        message_id="unmatched@x",
                        direction=MailDirection.INBOUND,
                        received_at=datetime(2026, 8, 3, tzinfo=UTC),
                        match_status=MailMatchStatus.UNMATCHED,
                    ),
                ]
            )
            session.commit()

        response = client.get(
            f"/api/v1/mail-accounts/{account_id}/messages",
            params=[("match_status", "matched"), ("match_status", "pending_review")],
        )

        statuses = {row["match_status"] for row in response.json()}
        assert statuses == {"matched", "pending_review"}

    def test_ordered_by_received_at_descending(
        self, client: TestClient, session_factory: sessionmaker[Session]
    ) -> None:
        _make_admin(session_factory)
        account_id = self._account_id(client)

        with session_factory() as session:
            session.add_all(
                [
                    MailMessage(
                        mail_account_id=uuid.UUID(account_id),
                        message_id="older@x",
                        direction=MailDirection.INBOUND,
                        received_at=datetime(2026, 8, 1, tzinfo=UTC),
                        match_status=MailMatchStatus.UNMATCHED,
                    ),
                    MailMessage(
                        mail_account_id=uuid.UUID(account_id),
                        message_id="newer@x",
                        direction=MailDirection.INBOUND,
                        received_at=datetime(2026, 8, 10, tzinfo=UTC),
                        match_status=MailMatchStatus.UNMATCHED,
                    ),
                ]
            )
            session.commit()

        response = client.get(f"/api/v1/mail-accounts/{account_id}/messages")

        body = response.json()
        assert [row["subject"] for row in body] == [None, None]
        message_ids_in_order = [
            "newer@x" if row["received_at"].startswith("2026-08-10") else "older@x" for row in body
        ]
        assert message_ids_in_order == ["newer@x", "older@x"]

    def test_pagination_offset_and_limit(
        self, client: TestClient, session_factory: sessionmaker[Session]
    ) -> None:
        _make_admin(session_factory)
        account_id = self._account_id(client)

        with session_factory() as session:
            account = session.get(MailAccount, uuid.UUID(account_id))
            assert account is not None
            for i in range(5):
                session.add(
                    MailMessage(
                        mail_account_id=uuid.UUID(account_id),
                        message_id=f"m{i}@x",
                        direction=MailDirection.INBOUND,
                        received_at=datetime(2026, 8, 1 + i, tzinfo=UTC),
                        match_status=MailMatchStatus.UNMATCHED,
                    )
                )
            session.commit()

        first_page = client.get(
            f"/api/v1/mail-accounts/{account_id}/messages", params={"limit": 2, "offset": 0}
        ).json()
        second_page = client.get(
            f"/api/v1/mail-accounts/{account_id}/messages", params={"limit": 2, "offset": 2}
        ).json()

        assert len(first_page) == 2
        assert len(second_page) == 2
        assert {row["id"] for row in first_page}.isdisjoint({row["id"] for row in second_page})
