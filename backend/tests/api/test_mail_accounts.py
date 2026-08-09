"""API-Tests fuer die Postfach-Verwaltung.

Schwerpunkt: das Passwort darf NIE ueber die API zurueckkommen, und die
Endpunkte sind durchgaengig Admin-only (dort liegen die Zugangsdaten aller
Firmen-Postfaecher).
"""

from collections.abc import Iterator

import pytest
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session, sessionmaker

from cc_crm.core.config import get_settings
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
