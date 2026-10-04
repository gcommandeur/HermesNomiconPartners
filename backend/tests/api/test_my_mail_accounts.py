"""Mein Postfach: persoenliche IMAP/SMTP-Konten (jeder nur seine eigenen)."""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

import pytest
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from cc_crm.core.config import get_settings
from cc_crm.models.enums import MailAccountProvider
from cc_crm.models.mail import MailAccount
from cc_crm.models.recruiting import AuditLog
from cc_crm.models.user import User
from cc_crm.services import my_mail_accounts as my_service
from cc_crm.services.mail_connection_test import MailCredentials
from cc_crm.services.mail_sync import sync_all_active
from tests.api.test_team_lead import Person, _make_user

BASE = "/api/v1/me/mail-accounts"
PAYLOAD = {
    "address": "lukas@example.com",
    "label": "Lukas privat",
    "imap_host": "imap.example.com",
    "smtp_host": "smtp.example.com",
    "username": "lukas@example.com",
    "password": "ganz-geheim-123",
}


@pytest.fixture(autouse=True)
def _key(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    get_settings.cache_clear()
    monkeypatch.setenv("CC_CRM_MAIL_CREDENTIALS_ENCRYPTION_KEY", Fernet.generate_key().decode())
    yield
    get_settings.cache_clear()


def _other(session_factory: sessionmaker[Session]) -> Person:
    return _make_user(session_factory, "andere@example.com", "member", "Andere")


def _admin(session_factory: sessionmaker[Session]) -> Person:
    return _make_user(session_factory, "admin@example.com", "admin", "Admin")


def _create(client: TestClient, headers: dict[str, str] | None = None, **over: Any) -> dict:
    response = client.post(BASE, json={**PAYLOAD, **over}, headers=headers)
    assert response.status_code == 201, response.text
    return response.json()


def test_create_is_personal_send_only_and_never_returns_the_password(
    client: TestClient, session_factory: sessionmaker[Session]
) -> None:
    created = _create(client)
    assert "password" not in created and "encrypted_password" not in created
    assert PAYLOAD["password"] not in str(created)
    assert created["sync_enabled"] is False
    assert created["default_for_cv_out"] is False
    assert created["is_default_sender"] is True  # erstes Konto wird Standard-Absender

    with session_factory() as session:
        account = session.scalars(select(MailAccount)).one()
        user = session.scalars(select(User)).first()
        assert account.owner_user_id == user.id
        assert account.encrypted_password and PAYLOAD["password"] not in account.encrypted_password
        audit = [
            row for row in session.scalars(select(AuditLog)) if row.entity_type == "mail_account"
        ]
        assert [row.action for row in audit] == ["personal_created"]
        assert PAYLOAD["password"] not in str(audit[0].new_values) + str(audit[0].old_values)

    listing = client.get(BASE).json()
    assert [row["address"] for row in listing] == ["lukas@example.com"]
    assert PAYLOAD["password"] not in str(listing)


def test_users_only_see_and_touch_their_own_accounts(
    client: TestClient, session_factory: sessionmaker[Session]
) -> None:
    other = _other(session_factory)
    mine = _create(client)
    theirs = _create(client, headers=other.headers, address="andere@privat.example")

    assert [row["id"] for row in client.get(BASE).json()] == [mine["id"]]
    assert [row["id"] for row in client.get(BASE, headers=other.headers).json()] == [theirs["id"]]

    url = f"{BASE}/{theirs['id']}"
    assert client.patch(url, json={"label": "x"}).status_code == 404
    assert client.delete(url).status_code == 404
    assert client.post(f"{url}/default").status_code == 404
    assert client.post(f"{url}/test").status_code == 404
    assert client.get(f"{url}/messages").status_code == 404
    assert client.post(f"{url}/sync").status_code == 404
    # Unbekannt sieht genauso aus wie fremd.
    unknown = f"{BASE}/00000000-0000-0000-0000-000000000000"
    assert client.patch(unknown, json={"label": "x"}).status_code == 404


def test_duplicate_address_is_refused(client: TestClient) -> None:
    _create(client)
    again = client.post(BASE, json=PAYLOAD)
    assert again.status_code >= 400


def test_update_default_and_delete(
    client: TestClient, session_factory: sessionmaker[Session]
) -> None:
    first = _create(client)
    second = _create(client, address="zweit@example.com")
    assert second["is_default_sender"] is False

    set_default = client.post(f"{BASE}/{second['id']}/default")
    assert set_default.status_code == 200 and set_default.json()["is_default_sender"] is True
    listing = {row["id"]: row for row in client.get(BASE).json()}
    assert listing[first["id"]]["is_default_sender"] is False

    patched = client.patch(
        f"{BASE}/{second['id']}", json={"label": "Neu", "password": "neues-passwort-9"}
    )
    assert patched.status_code == 200 and patched.json()["label"] == "Neu"
    assert "neues-passwort-9" not in patched.text

    # Deaktiviertes Konto ist nicht mehr Standard und kann es nicht werden.
    assert client.patch(f"{BASE}/{second['id']}", json={"is_active": False}).status_code == 200
    assert client.post(f"{BASE}/{second['id']}/default").status_code >= 400
    assert client.delete(f"{BASE}/{second['id']}").status_code == 204
    with session_factory() as session:
        assert session.scalars(select(User)).first().default_send_account_id is None
        assert len(session.scalars(select(MailAccount)).all()) == 1


def test_connection_test_uses_login_only_and_hides_the_password(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    seen: list[MailCredentials] = []

    def imap(credentials: MailCredentials) -> None:
        seen.append(credentials)
        raise OSError(f"Login fehlgeschlagen fuer {credentials.password}")

    def smtp(credentials: MailCredentials) -> None:
        seen.append(credentials)

    monkeypatch.setattr(my_service, "check_connection", _wrap(imap, smtp))
    body = {k: v for k, v in PAYLOAD.items() if k not in ("address", "label")}
    result = client.post(f"{BASE}/test", json=body).json()
    assert result["imap_ok"] is False and result["smtp_ok"] is True
    assert PAYLOAD["password"] not in str(result)
    assert "***" in result["imap_error"]

    created = _create(client)
    saved = client.post(f"{BASE}/{created['id']}/test").json()
    assert saved["smtp_ok"] is True
    assert seen[-1].password == PAYLOAD["password"]  # intern entschluesselt, nie nach aussen


def _wrap(imap: Any, smtp: Any) -> Any:
    from cc_crm.services.mail_connection_test import check_connection

    return lambda credentials: check_connection(
        credentials, imap_connector=imap, smtp_connector=smtp
    )


def test_only_the_owner_can_send_from_a_personal_account(
    client: TestClient, session_factory: sessionmaker[Session], monkeypatch: pytest.MonkeyPatch
) -> None:
    other = _other(session_factory)
    theirs = _create(client, headers=other.headers, address="andere@privat.example")
    sent: list[str] = []

    def fake_send(session: Session, *, account: MailAccount, **kwargs: Any) -> Any:
        sent.append(account.address)
        raise RuntimeError("stop")  # Antwort nicht noetig, nur die Kontenwahl

    monkeypatch.setattr("cc_crm.api.v1.mail_send.send_mail", fake_send)
    request = {
        "to_address": "kandidat@example.com",
        "subject": "Hallo",
        "body_text": "Text",
        "account_id": theirs["id"],
    }
    # Fremdes persoenliches Konto: 404, es wird nichts gesendet.
    denied = client.post("/api/v1/mail/send", json=request)
    assert denied.status_code == 404
    assert sent == []
    # Auch ein Admin darf nicht aus dem persoenlichen Konto eines anderen senden.
    admin = _admin(session_factory)
    assert client.post("/api/v1/mail/send", json=request, headers=admin.headers).status_code == 404
    assert sent == []

    # Der Besitzer schon (der Versand wird gleich abgebrochen - uns reicht die Kontenwahl).
    with pytest.raises(RuntimeError):
        client.post("/api/v1/mail/send", json=request, headers=other.headers)
    assert sent == ["andere@privat.example"]


def test_default_sender_resolution_uses_the_personal_account(
    client: TestClient, session_factory: sessionmaker[Session]
) -> None:
    from cc_crm.services.mail_accounts import MailAccountService

    created = _create(client)
    with session_factory() as session:
        user = session.scalars(select(User)).first()
        resolved = MailAccountService(session).resolve_send_account(user)
        assert str(resolved.id) == created["id"]


def test_inbox_of_a_personal_account_is_hidden_from_admins_and_not_synced(
    client: TestClient, session_factory: sessionmaker[Session]
) -> None:
    created = _create(client)
    admin = _admin(session_factory)
    assert client.get(
        f"/api/v1/mail-accounts/{created['id']}/messages", headers=admin.headers
    ).status_code == 404
    assert client.post(
        f"/api/v1/mail-accounts/{created['id']}/sync", headers=admin.headers
    ).status_code == 404
    # Der Besitzer sieht seinen (leeren) Posteingang; Abruf ist standardmaessig aus.
    assert client.get(f"{BASE}/{created['id']}/messages").json() == []
    off = client.post(f"{BASE}/{created['id']}/sync")
    assert off.status_code >= 400

    with session_factory() as session:
        fetched: list[str] = []

        def fetcher(account: MailAccount, since: str | None) -> list:
            fetched.append(account.address)
            return []

        sync_all_active(session, fetcher=fetcher)
        assert fetched == []  # sync_enabled=false wird uebersprungen

        account = session.scalars(select(MailAccount)).one()
        account.sync_enabled = True
        session.commit()
        sync_all_active(session, fetcher=fetcher)
        assert fetched == ["lukas@example.com"]


def test_shared_accounts_stay_admin_managed_and_cannot_be_edited_via_me(
    client: TestClient, session_factory: sessionmaker[Session]
) -> None:
    with session_factory() as session:
        shared = MailAccount(
            address="info@firma.example",
            label="Info",
            provider=MailAccountProvider.IMAP_SMTP,
            imap_host="i",
            smtp_host="s",
            username="u",
            encrypted_password="x",
        )
        session.add(shared)
        session.commit()
        shared_id = str(shared.id)
    assert client.get(BASE).json() == []
    assert client.patch(f"{BASE}/{shared_id}", json={"label": "x"}).status_code == 404
    assert client.delete(f"{BASE}/{shared_id}").status_code == 404
    # Gemeinsame Konten bleiben fuer alle als Absender waehlbar.
    from cc_crm.api.v1.mail_send import _resolve_send_account

    with session_factory() as session:
        user = session.scalars(select(User)).first()
        assert _resolve_send_account(session, user, shared.id).address == "info@firma.example"


def test_microsoft_login_mailbox_is_personal_when_it_is_the_users_own_address(
    session_factory: sessionmaker[Session],
) -> None:
    from cc_crm.integrations.microsoft_graph.auth import GraphTokens
    from cc_crm.services.mail_oauth import store_connection

    tokens = GraphTokens(access_token="a", refresh_token="r", expires_in=3600, scope="x")
    with session_factory() as session:
        own = User(email="lukas@firma.example", hashed_password="x")
        admin = User(email="admin@firma.example", hashed_password="x", role="admin")
        session.add_all([own, admin])
        session.commit()
        mine = store_connection(session, own.id, tokens, {"mail": "lukas@firma.example"})
        shared = store_connection(session, admin.id, tokens, {"mail": "info@firma.example"})
        assert mine.owner_user_id == own.id and mine.sync_enabled is False
        assert shared.owner_user_id is None and shared.sync_enabled is True
        assert own.default_send_account_id == mine.id
        assert admin.default_send_account_id is None  # fremde Adresse -> kein Standard
