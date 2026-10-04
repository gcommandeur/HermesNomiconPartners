"""Microsoft-Login gehaertet (Review 2026-10-04, Punkt 2): Gaeste abgelehnt, unveraenderliche
Kennung (`ms_oid`) per Trust-on-first-use gebunden, Multi-Tenant-Konfiguration deaktiviert den
Login, Admin kann die Bindung loesen. Microsoft ist in den Tests ersetzt (siehe
test_microsoft_login.py), es wird nichts nach aussen gesendet."""

# ruff: noqa: F811
from __future__ import annotations

from urllib.parse import unquote

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from cc_crm.core.config import get_settings
from cc_crm.integrations.microsoft_graph.auth import login_tenant_problem
from cc_crm.models.recruiting import AuditLog
from cc_crm.models.user import User
from cc_crm.services.auth import AuthService
from tests.api.test_microsoft_login import (  # noqa: F401  (Fixtures muessen importiert werden)
    CALLBACK,
    LOGIN,
    ORIGIN,
    _add_user,
    _anonymous,
    _settings,
    _start,
    microsoft,
)
from tests.api.test_team_lead import _make_user

NO_ACCOUNT = "Kein Konto für diese E-Mail-Adresse"


def _callback(client: TestClient) -> tuple[str, str]:
    _anonymous(client)
    state = _start(client)
    response = client.get(CALLBACK, params={"code": "abc", "state": state}, follow_redirects=False)
    return response.headers["location"], " ".join(response.headers.get_list("set-cookie"))


def _oid(session_factory: sessionmaker[Session], email: str = "sso@example.com") -> str | None:
    with session_factory() as session:
        return session.scalar(select(User.ms_oid).where(User.email == email))


def _audit_actions(session_factory: sessionmaker[Session]) -> list[str]:
    with session_factory() as session:
        return list(session.scalars(select(AuditLog.action)).all())


def test_guest_is_rejected_and_nothing_is_bound(
    client: TestClient, session_factory: sessionmaker[Session], microsoft: dict[str, dict[str, str]]
) -> None:
    _add_user(session_factory)
    microsoft["profile"] = {"id": "oid-gast", "mail": "sso@example.com", "userType": "Guest"}
    location, cookies = _callback(client)
    assert location.startswith(f"{ORIGIN}/login?error=")
    assert NO_ACCOUNT in unquote(location)
    assert "cc_crm_token" not in cookies
    assert _oid(session_factory) is None


def test_first_login_binds_the_oid_and_audits_it(
    client: TestClient, session_factory: sessionmaker[Session], microsoft: dict[str, dict[str, str]]
) -> None:
    _add_user(session_factory)
    assert _oid(session_factory) is None  # Vorbedingung: vorher nichts gebunden
    location, cookies = _callback(client)
    assert location == f"{ORIGIN}/sso-complete"
    assert "cc_crm_token=" in cookies
    assert _oid(session_factory) == "oid-sso-1"
    assert "microsoft_oid_bound" in _audit_actions(session_factory)


def test_login_with_the_bound_oid_keeps_working(
    client: TestClient, session_factory: sessionmaker[Session], microsoft: dict[str, dict[str, str]]
) -> None:
    _add_user(session_factory)
    assert _callback(client)[0] == f"{ORIGIN}/sso-complete"
    assert _callback(client)[0] == f"{ORIGIN}/sso-complete"
    assert _audit_actions(session_factory).count("microsoft_oid_bound") == 1


def test_a_different_oid_is_rejected_with_audit(
    client: TestClient, session_factory: sessionmaker[Session], microsoft: dict[str, dict[str, str]]
) -> None:
    _add_user(session_factory)
    assert _callback(client)[0] == f"{ORIGIN}/sso-complete"  # bindet oid-sso-1
    # Dieselbe Adresse, aber ein anderes Microsoft-Konto (z. B. neu vergebene Adresse).
    microsoft["profile"] = {"id": "oid-anderer-mensch", "mail": "sso@example.com"}
    location, cookies = _callback(client)
    assert location.startswith(f"{ORIGIN}/login?error=")
    assert NO_ACCOUNT in unquote(location)  # gleiche neutrale Meldung wie "kein Konto"
    assert "cc_crm_token" not in cookies
    assert _oid(session_factory) == "oid-sso-1"  # unveraendert
    assert "microsoft_login_oid_mismatch" in _audit_actions(session_factory)


def test_an_oid_that_belongs_to_another_user_is_rejected(
    client: TestClient, session_factory: sessionmaker[Session], microsoft: dict[str, dict[str, str]]
) -> None:
    _add_user(session_factory, "a@example.com")
    _add_user(session_factory, "b@example.com")
    microsoft["profile"] = {"id": "oid-gemeinsam", "mail": "a@example.com"}
    assert _callback(client)[0] == f"{ORIGIN}/sso-complete"
    # Nutzer B meldet sich mit der Kennung von A an.
    microsoft["profile"] = {"id": "oid-gemeinsam", "mail": "b@example.com"}
    location, cookies = _callback(client)
    assert location.startswith(f"{ORIGIN}/login?error=")
    assert "cc_crm_token" not in cookies
    assert _oid(session_factory, "b@example.com") is None
    assert "microsoft_login_oid_conflict" in _audit_actions(session_factory)


def test_missing_oid_is_rejected(
    client: TestClient, session_factory: sessionmaker[Session], microsoft: dict[str, dict[str, str]]
) -> None:
    _add_user(session_factory)
    microsoft["profile"] = {"mail": "sso@example.com"}
    location, cookies = _callback(client)
    assert location.startswith(f"{ORIGIN}/login?error=")
    assert "cc_crm_token" not in cookies


@pytest.mark.parametrize("tenant", ["common", "organizations", "consumers", "COMMON", ""])
def test_multi_tenant_configuration_keeps_the_login_disabled(
    client: TestClient, monkeypatch: pytest.MonkeyPatch, tenant: str
) -> None:
    monkeypatch.setenv("CC_CRM_MS_GRAPH_TENANT_ID", tenant)
    get_settings.cache_clear()
    assert login_tenant_problem() is not None
    _anonymous(client)
    response = client.get(LOGIN, follow_redirects=False)
    assert response.headers["location"].startswith(f"{ORIGIN}/login?error=")
    assert not client.cookies.get("cc_crm_ms_login")


def test_a_directory_guid_is_accepted() -> None:
    assert login_tenant_problem() is None  # Fixture-Wert "tenant-id" ist kein Multi-Tenant-Wert


def test_inactive_user_is_still_treated_like_a_missing_one(
    client: TestClient, session_factory: sessionmaker[Session], microsoft: dict[str, dict[str, str]]
) -> None:
    _add_user(session_factory, active=False)
    location, _ = _callback(client)
    assert NO_ACCOUNT in unquote(location)
    assert _oid(session_factory) is None  # nichts gebunden


def test_password_login_is_unchanged_for_a_bound_user(
    session_factory: sessionmaker[Session],
) -> None:
    from cc_crm.core.security import hash_password

    with session_factory() as session:
        session.add(
            User(email="pw@example.com", hashed_password=hash_password("geheim"), ms_oid="oid-pw")
        )
        session.commit()
        user, token = AuthService(session).login("pw@example.com", "geheim")
        assert user.email == "pw@example.com" and token


def test_admin_can_reset_the_binding_and_others_cannot(
    client: TestClient, session_factory: sessionmaker[Session]
) -> None:
    admin = _make_user(session_factory, "chef@example.com", "admin", "Chef")
    member = _make_user(session_factory, "m@example.com", "member", "Mitarbeiterin")
    with session_factory() as session:
        user = session.scalar(select(User).where(User.email == "m@example.com"))
        assert user is not None
        user.ms_oid = "oid-m"
        session.commit()

    listed = client.get("/api/v1/users", headers=admin.headers).json()
    assert next(u for u in listed if u["email"] == "m@example.com")["ms_bound"] is True
    assert "ms_oid" not in listed[0]  # die Kennung selbst wird nicht ausgeliefert

    forbidden = client.post(
        f"/api/v1/users/{member.id}/reset-microsoft-binding", headers=member.headers
    )
    assert forbidden.status_code == 403
    assert _oid(session_factory, "m@example.com") == "oid-m"  # unveraendert

    done = client.post(f"/api/v1/users/{member.id}/reset-microsoft-binding", headers=admin.headers)
    assert done.status_code == 200, done.text
    assert done.json()["ms_bound"] is False
    assert _oid(session_factory, "m@example.com") is None
    assert "microsoft_oid_reset" in _audit_actions(session_factory)
