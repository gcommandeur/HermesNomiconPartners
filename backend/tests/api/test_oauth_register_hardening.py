# ruff: noqa: F811
"""OAuth-Registrierung (POST /oauth/register) abgesichert (Review 2026-10-04, Punkt 3):
Rate-Limit pro IP, druckbarer/begrenzter Name, harte Obergrenze, Aufraeumen nicht
benutzter Clients. Vorhanden war schon: MAX_CLIENTS=500, MAX_REDIRECT_URIS=5."""

from __future__ import annotations

import uuid
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

from cc_crm.core.rate_limit import oauth_register_rate_limiter
from cc_crm.models.oauth import OAuthClient, OAuthToken
from cc_crm.models.user import User
from cc_crm.services import oauth_provider
from cc_crm.services.oauth_provider import STALE_CLIENT_DAYS
from tests.api.test_oauth_provider import BASE, CALLBACK, ai_on  # noqa: F401  (Fixture)


@pytest.fixture(autouse=True)
def _clean_limiter() -> Iterator[None]:
    oauth_register_rate_limiter.reset()
    yield
    oauth_register_rate_limiter.reset()


def _post(client: TestClient, name: str | None = "Claude", ip: str = "198.51.100.7", **extra):
    body: dict = {"redirect_uris": [CALLBACK], **extra}
    if name is not None:
        body["client_name"] = name
    return client.post(f"{BASE}/oauth/register", json=body, headers={"cf-connecting-ip": ip})


def _count(session_factory: sessionmaker[Session]) -> int:
    with session_factory() as session:
        return session.scalar(select(func.count()).select_from(OAuthClient)) or 0


def test_eleventh_registration_within_an_hour_is_refused(client: TestClient, ai_on: None) -> None:
    for number in range(10):
        assert _post(client).status_code == 201, number
    blocked = _post(client)
    assert blocked.status_code == 429
    assert blocked.json()["error"] == "too_many_requests"
    # Eine andere Client-IP ist davon nicht betroffen (Zaehler pro IP).
    assert _post(client, ip="203.0.113.9").status_code == 201


def test_blocked_requests_do_not_create_clients(
    client: TestClient, session_factory: sessionmaker[Session], ai_on: None
) -> None:
    for _ in range(10):
        _post(client)
    before = _count(session_factory)
    assert before == 10  # Vorbedingung: die ersten zehn wurden wirklich angelegt
    assert _post(client).status_code == 429
    assert _count(session_factory) == before


@pytest.mark.parametrize("name", ["x" * 121, "Cla\x00ude", "Zeile\neins", "‮Evil", 123, ["Claude"]])
def test_overlong_or_unprintable_names_are_refused(
    client: TestClient, ai_on: None, name: object
) -> None:
    response = client.post(
        f"{BASE}/oauth/register", json={"client_name": name, "redirect_uris": [CALLBACK]}
    )
    assert response.status_code == 400, response.text
    assert response.json()["error"] == "invalid_client_metadata"


def test_normal_and_missing_names_still_work(client: TestClient, ai_on: None) -> None:
    ok = _post(client, name="Claude für Hermes (Büro)")
    assert ok.status_code == 201 and ok.json()["client_name"] == "Claude für Hermes (Büro)"
    default = _post(client, name=None)
    assert default.status_code == 201 and default.json()["client_name"] == "Claude"


def test_more_than_five_redirect_uris_are_refused(client: TestClient, ai_on: None) -> None:
    response = client.post(
        f"{BASE}/oauth/register", json={"client_name": "Claude", "redirect_uris": [CALLBACK] * 6}
    )
    assert response.status_code == 400
    assert response.json()["error"] == "invalid_redirect_uri"


def test_hard_cap_refuses_when_all_clients_are_in_use(
    client: TestClient, ai_on: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(oauth_provider, "MAX_CLIENTS", 2)
    assert _post(client, ip="198.51.100.1").status_code == 201
    assert _post(client, ip="198.51.100.2").status_code == 201
    # Alle Clients "in Benutzung": das Aufraeumen findet nichts -> harte Grenze.
    monkeypatch.setattr(
        oauth_provider.OAuthProvider, "_purge_unused_clients", lambda self, **kwargs: None
    )
    refused = _post(client, ip="198.51.100.3")
    assert refused.status_code == 503
    assert refused.json()["error"] == "temporarily_unavailable"


def test_cap_evicts_the_oldest_unused_clients_but_never_one_with_a_token(
    client: TestClient,
    session_factory: sessionmaker[Session],
    ai_on: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(oauth_provider, "MAX_CLIENTS", 4)
    with session_factory() as session:
        user = User(email="owner@example.com", hashed_password="x")
        session.add(user)
        session.flush()
        now = datetime.now(UTC)
        ids = []
        for number in range(4):
            cid = f"hmc_cap{number}"
            ids.append(cid)
            session.add(
                OAuthClient(
                    client_id=cid,
                    client_name=f"c{number}",
                    redirect_uris=[CALLBACK],
                    created_at=now - timedelta(minutes=10 - number),
                )
            )
        # Der AELTESTE Client hat ein Token - er darf nicht verdraengt werden.
        session.add(
            OAuthToken(
                user_id=user.id,
                client_id=ids[0],
                access_hash=uuid.uuid4().hex + uuid.uuid4().hex,
                refresh_hash=uuid.uuid4().hex + uuid.uuid4().hex,
                access_expires_at=now + timedelta(hours=1),
                refresh_expires_at=now + timedelta(days=30),
            )
        )
        session.commit()
    assert _count(session_factory) == 4
    assert _post(client).status_code == 201
    with session_factory() as session:
        remaining = set(session.scalars(select(OAuthClient.client_id)).all())
    assert "hmc_cap0" in remaining  # mit Token: bleibt
    assert len(remaining) <= 4  # Obergrenze gehalten


def test_clients_without_token_older_than_30_days_are_purged_on_register(
    client: TestClient,
    session_factory: sessionmaker[Session],
    ai_on: None,
) -> None:
    old = datetime.now(UTC) - timedelta(days=STALE_CLIENT_DAYS + 1)
    recent = datetime.now(UTC) - timedelta(days=STALE_CLIENT_DAYS - 1)
    with session_factory() as session:
        user = User(email="owner2@example.com", hashed_password="x")
        session.add(user)
        session.flush()
        for cid, created in (
            ("hmc_old_unused", old),
            ("hmc_old_used", old),
            ("hmc_new_unused", recent),
        ):
            session.add(
                OAuthClient(
                    client_id=cid, client_name=cid, redirect_uris=[CALLBACK], created_at=created
                )
            )
        session.add(
            OAuthToken(
                user_id=user.id,
                client_id="hmc_old_used",
                access_hash=uuid.uuid4().hex + uuid.uuid4().hex,
                refresh_hash=uuid.uuid4().hex + uuid.uuid4().hex,
                access_expires_at=old + timedelta(hours=1),
                refresh_expires_at=old + timedelta(days=30),
            )
        )
        session.commit()
    assert _post(client).status_code == 201
    with session_factory() as session:
        remaining = set(session.scalars(select(OAuthClient.client_id)).all())
    assert "hmc_old_unused" not in remaining  # alt und ohne Token: weg
    assert "hmc_old_used" in remaining  # alt, aber mit Token: bleibt
    assert "hmc_new_unused" in remaining  # ohne Token, aber juenger als 30 Tage: bleibt
