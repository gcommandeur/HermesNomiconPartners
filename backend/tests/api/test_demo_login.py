# NOMICON: Demo-Login ohne Passwort/2FA - nur lokal. Die Schutzmassnahmen sind der Kern der Tests.
from __future__ import annotations

import sys
from collections.abc import Generator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from cc_crm.core.config import Settings, get_settings
from cc_crm.core.rate_limit import login_rate_limiter
from cc_crm.main import create_app, lifespan
from cc_crm.models.client_company import ClientCompany
from cc_crm.models.user import User
from cc_crm.services.demo_login import (
    DEMO_PERSONAS,
    assert_demo_login_safe,
    database_is_local,
    demo_login_active,
    ensure_demo_users,
)
from cc_crm.services.engagement_status import summarize

API = "/api/v1"
SQLITE = "sqlite:////tmp/x.db"
LOCAL_PG = "postgresql+psycopg://u:p@localhost:5432/db"
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))


def _settings(**overrides: object) -> Settings:
    base = {"demo_login": True, "environment": "local", "database_url": SQLITE}
    return Settings(**{**base, **overrides})  # type: ignore[arg-type]


@pytest.fixture
def demo_on(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "cc_crm.api.v1.demo_login.get_settings",
        lambda: get_settings().model_copy(update={"demo_login": True, "environment": "local"}),
    )


@pytest.fixture
def seeded(session_factory: sessionmaker[Session]) -> None:
    with session_factory() as session:
        ensure_demo_users(session)


@pytest.fixture(autouse=True)
def _reset_limiter(client: TestClient) -> Generator[None, None, None]:
    login_rate_limiter.reset()
    yield
    login_rate_limiter.reset()


def _login(client: TestClient, persona: str) -> TestClient | dict:
    response = client.post(f"{API}/auth/demo-login", json={"persona": persona})
    assert response.status_code == 200, response.text
    return response.json()


# --- aus: nichts davon existiert ------------------------------------------------------------


def test_without_the_switch_the_endpoint_does_not_exist(client: TestClient, seeded: None) -> None:
    assert client.post(f"{API}/auth/demo-login", json={"persona": "admin"}).status_code == 404
    status = client.get(f"{API}/auth/demo-login/status")
    assert status.status_code == 200 and status.json() == {"enabled": False}


def test_switch_on_in_a_non_local_environment_is_inactive(
    client: TestClient, seeded: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        "cc_crm.api.v1.demo_login.get_settings",
        lambda: get_settings().model_copy(update={"demo_login": True, "environment": "production"}),
    )
    assert client.post(f"{API}/auth/demo-login", json={"persona": "admin"}).status_code == 404
    assert client.get(f"{API}/auth/demo-login/status").json() == {"enabled": False}


# --- Start in unsicherer Umgebung ----------------------------------------------------------


@pytest.mark.parametrize("environment", ["production", "staging", "development", "prod", ""])
def test_app_refuses_to_start_in_unsafe_environments(environment: str) -> None:
    with pytest.raises(RuntimeError, match="Demo-Login|DEMO_LOGIN"):
        assert_demo_login_safe(_settings(environment=environment))


@pytest.mark.parametrize(
    "url",
    [
        "postgresql+psycopg://u:p@db.internal.example:5432/x",
        "postgresql+psycopg://u:p@10.0.0.5:5432/x",
        "postgresql+psycopg://u:p@db-123.ondigitalocean.com:25060/x",
    ],
)
def test_app_refuses_to_start_with_a_foreign_database(url: str) -> None:
    with pytest.raises(RuntimeError, match="DEMO_LOGIN"):
        assert_demo_login_safe(_settings(database_url=url))


def test_safe_combinations_and_default_off() -> None:
    for environment in ("local", "test", "demo"):
        assert_demo_login_safe(_settings(environment=environment))
        assert demo_login_active(_settings(environment=environment))
    assert_demo_login_safe(_settings(database_url=LOCAL_PG))
    assert database_is_local("sqlite:///:memory:") and database_is_local(LOCAL_PG)
    # aus (Standard): nie aktiv, auch nicht in "unsicherer" Umgebung - dort passiert nichts
    off = _settings(demo_login=False, environment="production")
    assert_demo_login_safe(off)
    assert not demo_login_active(off)
    assert Settings().demo_login is False


def test_lifespan_refuses_to_run_in_production(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "cc_crm.core.config.get_settings",
        lambda: _settings(environment="production"),
        raising=True,
    )
    monkeypatch.setattr(
        "cc_crm.main.get_settings", lambda: _settings(environment="production"), raising=True
    )

    async def run() -> None:
        async with lifespan(create_app()):
            pass

    import asyncio

    with pytest.raises(RuntimeError, match="DEMO_LOGIN"):
        asyncio.run(run())


# --- an: genau zwei feste Konten ------------------------------------------------------------


def test_admin_persona_gets_a_session_without_password_or_code(
    client: TestClient, seeded: None, demo_on: None
) -> None:
    assert client.get(f"{API}/auth/demo-login/status").json() == {"enabled": True}
    body = _login(client, "admin")
    assert body["user"]["email"] == "demo-admin@nomicon.local"  # type: ignore[index]
    assert body["user"]["is_admin"] is True  # type: ignore[index]
    headers = {"Authorization": f"Bearer {body['token']}"}  # type: ignore[index]
    views = client.get(f"{API}/me/views", headers=headers).json()
    assert views == {
        "views": ["direct", "staffing", "management"],
        "default_view": "management",
    }


def test_broker_persona_is_a_member_with_direct_and_staffing(
    client: TestClient, seeded: None, demo_on: None
) -> None:
    body = _login(client, "vermittler")
    headers = {"Authorization": f"Bearer {body['token']}"}  # type: ignore[index]
    assert body["user"]["role"] == "member"  # type: ignore[index]
    assert client.get(f"{API}/me/views", headers=headers).json()["views"] == ["direct", "staffing"]
    assert client.get(f"{API}/staffing/overview", headers=headers).status_code == 200
    assert client.get(f"{API}/commission/report", headers=headers).status_code == 403
    # Der Demo-Admin kann die Ueberlassung live entziehen und wieder freischalten
    admin = {"Authorization": f"Bearer {_login(client, 'admin')['token']}"}  # type: ignore[index]
    broker_id = body["user"]["id"]  # type: ignore[index]
    revoked = client.put(
        f"{API}/admin/users/{broker_id}/views", json={"views": ["direct"]}, headers=admin
    )
    assert revoked.status_code == 200
    assert client.get(f"{API}/staffing/overview", headers=headers).status_code == 403
    client.put(
        f"{API}/admin/users/{broker_id}/views",
        json={"views": ["direct", "staffing"]},
        headers=admin,
    )
    assert client.get(f"{API}/staffing/overview", headers=headers).status_code == 200
    client.put(f"{API}/admin/users/{broker_id}/views", json={"views": ["direct"]}, headers=admin)
    assert client.get(f"{API}/staffing/overview", headers=headers).status_code == 403


@pytest.mark.parametrize("persona", ["root", "demo-admin@nomicon.local", "user", "", None, 1])
def test_every_other_persona_is_rejected(
    client: TestClient, seeded: None, demo_on: None, persona: object
) -> None:
    response = client.post(f"{API}/auth/demo-login", json={"persona": persona})
    assert response.status_code == 422


def test_extra_fields_cannot_pick_another_account(
    client: TestClient, seeded: None, demo_on: None, session_factory: sessionmaker[Session]
) -> None:
    response = client.post(
        f"{API}/auth/demo-login",
        json={"persona": "vermittler", "email": "test@commandeur.example", "user_id": "x"},
    )
    assert response.status_code == 200
    assert response.json()["user"]["email"] == "demo-vermittler@nomicon.local"


def test_missing_demo_accounts_give_a_clear_message_and_count_toward_the_limit(
    client: TestClient, demo_on: None
) -> None:
    first = client.post(f"{API}/auth/demo-login", json={"persona": "admin"})
    assert first.status_code == 401
    assert "seed_data.py seed --demo" in first.json()["detail"]
    codes = [
        client.post(f"{API}/auth/demo-login", json={"persona": "admin"}).status_code
        for _ in range(12)
    ]
    assert 429 in codes  # Ratenbegrenzung wie beim normalen Login


def test_demo_accounts_cannot_log_in_with_a_password_and_normal_login_is_unchanged(
    client: TestClient, seeded: None, demo_on: None
) -> None:
    for email in (p.email for p in DEMO_PERSONAS.values()):
        for guess in ("", "demo", "password", "test1234", email):
            response = client.post(
                f"{API}/auth/login", json={"email": email, "password": guess or "x"}
            )
            # 401 (falsches Passwort) oder 422 (.local ist keine gueltige Adresse fuer das
            # Login-Formular) - in beiden Faellen gibt es keinen Passwort-Weg
            assert response.status_code in (401, 422)
    # normaler Login eines echten Nutzers verlangt weiter den E-Mail-Code (kein vertrautes Geraet)
    # - hier genuegt: falsches Passwort bleibt 401, der Demo-Schalter aendert daran nichts.
    wrong = client.post(
        f"{API}/auth/login", json={"email": "test@commandeur.example", "password": "falsch"}
    )
    assert wrong.status_code == 401


def test_seed_is_idempotent_and_covers_every_status(
    session_factory: sessionmaker[Session],
) -> None:
    from seed_demo import seed_demo  # type: ignore[import-not-found]

    with session_factory() as session:
        for index in range(4):
            session.add(ClientCompany(name=f"Demo-Kanzlei {index}"))
        session.commit()
        first = seed_demo(session)
        again = seed_demo(session)
        assert first.candidates == 11 and first.users == 3
        assert (again.candidates, again.processes, again.assignments) == (0, 0, 0)
        users = {u.email: u for u in session.scalars(select(User)).all()}
        broker = users["demo-vermittler@nomicon.local"]
        from cc_crm.models.candidate import Candidate

        demo_ids = [c.id for c in session.scalars(select(Candidate)).all()]
        summary = summarize(session, broker, demo_ids)
        statuses = {row.status for row in summary.values()}
        assert statuses == {"frei", "im_direct", "im_einsatz", "beides", "vermittelt"}
        # fremder Prozess (Kollegin): Details/IDs verborgen, Kundenname sichtbar
        foreign = [
            item
            for row in summary.values()
            for item in row.items
            if item.owner_name == "Demo Kollegin"
        ]
        assert foreign and all(
            not item.details_visible and item.entity_id is None for item in foreign
        )
        # ...eigener Prozess: mit Kanzlei
        own = [
            item
            for row in summary.values()
            for item in row.items
            if item.owner_name == "Demo Vermittler" and item.channel == "direct"
        ]
        assert own and all(item.details_visible for item in own)


def test_seed_completes_owner_fee_and_probability_even_on_old_demo_data(
    session_factory: sessionmaker[Session],
) -> None:
    """Pipeline-Wert und gewichtete Fees sind > 0, kein Prozess ohne Verantwortlichen - auch wenn
    die Prozesse aus einer älteren Demo-Datenbank ohne diese Felder stammen."""
    from seed_demo import seed_demo  # type: ignore[import-not-found]

    from cc_crm.models.submission import CandidateSubmission

    with session_factory() as session:
        for index in range(4):
            session.add(ClientCompany(name=f"Demo-Kunde {index}"))
        session.commit()
        seed_demo(session)
        # alter Stand: alles ohne Verantwortlichen, Fee und Wahrscheinlichkeit
        for row in session.scalars(select(CandidateSubmission)).all():
            row.owner_user_id = None
            row.expected_fee = None
            row.closing_probability = None
        session.commit()
        seed_demo(session)
        everything = session.scalars(select(CandidateSubmission)).all()
        rows = [r for r in everything if r.status.value != "cancelled"]
        assert rows and all(r.owner_user_id is not None for r in rows)
        assert sum(float(r.expected_fee or 0) for r in rows) > 0
        weighted = sum(float(r.expected_fee or 0) * (r.closing_probability or 0) for r in rows)
        assert weighted > 0
        open_fees = [r for r in rows if r.status.value == "interview" and r.expected_fee is None]
        assert len(open_fees) == 2  # bewusst "Fee offen"
