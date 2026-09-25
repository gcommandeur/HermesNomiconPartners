import re
import threading
import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session, sessionmaker

from cc_crm.core.rate_limit import (
    EMAIL_MAX_ATTEMPTS,
    MAX_ATTEMPTS,
    VERIFY_MAX_ATTEMPTS,
    email_login_rate_limiter,
    login_rate_limiter,
    verify_account_rate_limiter,
    verify_ip_rate_limiter,
)
from tests.conftest import TEST_USER_EMAIL, TEST_USER_PASSWORD

_CODE_RE = re.compile(r"Anmeldecode lautet: (\d{6})")


@pytest.fixture(autouse=True)
def _reset_rate_limiters() -> None:
    """Beide Login-Rate-Limiter sind prozessweite Singletons (siehe
    core/rate_limit.py) - ohne einen Reset vor JEDEM Test wuerden
    fehlgeschlagene Login-Versuche aus vorherigen Tests (die alle denselben
    TEST_USER_EMAIL verwenden) sich ueber die Testdatei hinweg aufsummieren
    und einzelne, fuer sich genommen korrekte Tests mit einem unerwarteten
    429 statt 401 scheitern lassen."""
    login_rate_limiter.reset()
    email_login_rate_limiter.reset()
    verify_ip_rate_limiter.reset()
    verify_account_rate_limiter.reset()
    yield
    login_rate_limiter.reset()
    email_login_rate_limiter.reset()
    verify_ip_rate_limiter.reset()
    verify_account_rate_limiter.reset()


@pytest.fixture(autouse=True)
def _capture_sent_codes(monkeypatch: pytest.MonkeyPatch) -> list[dict[str, str]]:
    """2FA-Codes gehen per Resend raus (integrations/email/resend_client.py) -
    in Tests ist kein API-Key konfiguriert, also wird IMMER gemockt, damit
    kein Test versehentlich einen echten HTTP-Call macht. Der Klartext-Code
    steht im Mailtext (siehe api/v1/auth.py::_send_login_code) und wird hier
    abgegriffen, um ihn in den Tests "einzutippen"."""
    calls: list[dict[str, str]] = []

    def fake_send_transactional_email(*, to_address: str, subject: str, body_text: str) -> None:
        calls.append({"to_address": to_address, "subject": subject, "body_text": body_text})

    monkeypatch.setattr(
        "cc_crm.api.v1.auth.send_transactional_email", fake_send_transactional_email
    )
    return calls


def _extract_code(calls: list[dict[str, str]]) -> str:
    match = _CODE_RE.search(calls[-1]["body_text"])
    assert match is not None, f"Kein Code in der zuletzt 'verschickten' Mail gefunden: {calls[-1]}"
    return match.group(1)


def _start_login(
    client: TestClient, email: str = TEST_USER_EMAIL, password: str = TEST_USER_PASSWORD
):
    return client.post("/api/v1/auth/login", json={"email": email, "password": password})


def test_protected_route_requires_bearer_token(client: TestClient) -> None:
    client.headers.pop("Authorization", None)

    response = client.get("/api/v1/candidates")

    assert response.status_code == 401


def test_login_sends_a_code_and_verify_returns_token_and_me_resolves_user(
    client: TestClient, _capture_sent_codes: list[dict[str, str]]
) -> None:
    client.headers.pop("Authorization", None)

    start = _start_login(client)
    assert start.status_code == 200
    body = start.json()
    assert body["status"] == "challenge_required"
    assert body["challenge_id"]
    assert body["token"] is None
    assert len(_capture_sent_codes) == 1
    assert _capture_sent_codes[0]["to_address"] == TEST_USER_EMAIL

    code = _extract_code(_capture_sent_codes)
    verify = client.post(
        "/api/v1/auth/login/verify",
        json={"challenge_id": body["challenge_id"], "code": code},
    )
    assert verify.status_code == 200
    verify_body = verify.json()
    token = verify_body["token"]
    assert verify_body["trusted_device_token"]

    me = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert me.status_code == 200
    assert me.json()["email"] == TEST_USER_EMAIL


def test_wrong_code_is_rejected_and_locks_after_five_attempts(
    client: TestClient, _capture_sent_codes: list[dict[str, str]]
) -> None:
    client.headers.pop("Authorization", None)
    challenge_id = _start_login(client).json()["challenge_id"]

    for _ in range(5):
        wrong = client.post(
            "/api/v1/auth/login/verify",
            json={"challenge_id": challenge_id, "code": "000000"},
        )
        assert wrong.status_code == 401

    locked = client.post(
        "/api/v1/auth/login/verify",
        json={"challenge_id": challenge_id, "code": "000000"},
    )
    assert locked.status_code == 401
    assert "Fehlversuche" in locked.json()["detail"]

    # Selbst der RICHTIGE Code wird nach der Sperre nicht mehr angenommen.
    code = _extract_code(_capture_sent_codes)
    still_locked = client.post(
        "/api/v1/auth/login/verify", json={"challenge_id": challenge_id, "code": code}
    )
    assert still_locked.status_code == 401


def test_verify_rate_limit_blocks_after_many_attempts_across_different_challenges(
    client: TestClient,
    _capture_sent_codes: list[dict[str, str]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Punkt 2 des Auftrags "3 Mittel-Punkte umsetzen": der bestehende
    Pro-Challenge-Zaehler (MAX_CODE_ATTEMPTS=5) greift nicht, wenn ein
    Angreifer (der das Passwort schon kennt) einfach immer wieder eine neue
    Challenge erzeugt - jeder Verify-Versuch haette sonst einen teuren
    PBKDF2-Hash ausgeloest, egal wie viele verschiedene challenge_ids
    verwendet werden. Zaehlt hier ueber VERIFY_MAX_ATTEMPTS verschiedene,
    valide Challenges hinweg."""
    client.headers.pop("Authorization", None)

    from cc_crm.services import auth as auth_service_module

    # verify_password wird auch fuer den normalen Passwort-Check in
    # authenticate() verwendet (_start_login() ruft es also selbst schon
    # einmal pro Iteration auf) - hier zaehlt nur, wie oft es waehrend des
    # VERIFY-Schritts selbst aufgerufen wird, daher ein Delta je Iteration
    # statt eines globalen Gesamtzaehlers.
    call_count = {"n": 0}
    original_verify_password = auth_service_module.verify_password

    def counting_verify_password(code: str, hashed: str) -> bool:
        call_count["n"] += 1
        return original_verify_password(code, hashed)

    monkeypatch.setattr(auth_service_module, "verify_password", counting_verify_password)

    for _ in range(VERIFY_MAX_ATTEMPTS):
        challenge_id = _start_login(client).json()["challenge_id"]
        before_verify = call_count["n"]
        response = client.post(
            "/api/v1/auth/login/verify",
            json={"challenge_id": challenge_id, "code": "000000"},
        )
        assert response.status_code == 401
        assert call_count["n"] == before_verify + 1

    # Der naechste Versuch - mit einer wiederum frischen, gueltigen
    # Challenge - wird jetzt blockiert, OHNE dass ueberhaupt noch ein
    # PBKDF2-Hash fuer den Code berechnet wird (Kernanforderung: das Limit
    # muss VOR dem teuren Vergleich greifen).
    blocked_challenge_id = _start_login(client).json()["challenge_id"]
    before_blocked = call_count["n"]
    blocked = client.post(
        "/api/v1/auth/login/verify",
        json={"challenge_id": blocked_challenge_id, "code": "000000"},
    )
    assert blocked.status_code == 429
    assert call_count["n"] == before_blocked


def test_verify_rate_limit_does_not_block_normal_two_factor_login(
    client: TestClient, _capture_sent_codes: list[dict[str, str]]
) -> None:
    """Regressionsschutz: ein einzelner, korrekter Verify-Versuch bleibt
    weiterhin ganz normal moeglich - das neue Limit betrifft nur exzessive
    Versuchsserien."""
    client.headers.pop("Authorization", None)
    challenge_id = _start_login(client).json()["challenge_id"]
    code = _extract_code(_capture_sent_codes)

    verify = client.post(
        "/api/v1/auth/login/verify", json={"challenge_id": challenge_id, "code": code}
    )
    assert verify.status_code == 200


def test_expired_code_is_rejected_with_a_clear_message(
    client: TestClient, session_factory: sessionmaker[Session]
) -> None:
    from datetime import UTC, datetime, timedelta

    from cc_crm.models.login_challenge import LoginChallenge

    client.headers.pop("Authorization", None)
    challenge_id = _start_login(client).json()["challenge_id"]

    with session_factory() as session:
        challenge = session.get(LoginChallenge, uuid.UUID(challenge_id))
        assert challenge is not None
        challenge.expires_at = datetime.now(UTC) - timedelta(minutes=1)
        session.commit()

    response = client.post(
        "/api/v1/auth/login/verify",
        json={"challenge_id": challenge_id, "code": "123456"},
    )
    assert response.status_code == 401
    assert "abgelaufen" in response.json()["detail"]


def test_resend_issues_a_new_code_and_resets_the_attempt_counter(
    client: TestClient, _capture_sent_codes: list[dict[str, str]]
) -> None:
    client.headers.pop("Authorization", None)
    challenge_id = _start_login(client).json()["challenge_id"]

    for _ in range(4):
        client.post(
            "/api/v1/auth/login/verify",
            json={"challenge_id": challenge_id, "code": "000000"},
        )

    cooldown = client.post("/api/v1/auth/login/resend", json={"challenge_id": challenge_id})
    assert cooldown.status_code == 422
    assert "warten" in cooldown.json()["detail"]


def test_resend_after_cooldown_issues_a_working_new_code(
    client: TestClient, session_factory: sessionmaker[Session]
) -> None:
    from datetime import UTC, datetime, timedelta

    from cc_crm.models.login_challenge import LoginChallenge

    client.headers.pop("Authorization", None)
    challenge_id = _start_login(client).json()["challenge_id"]

    for _ in range(5):
        client.post(
            "/api/v1/auth/login/verify",
            json={"challenge_id": challenge_id, "code": "000000"},
        )

    # Cooldown manuell ablaufen lassen statt 60s im Test zu warten.
    with session_factory() as session:
        challenge = session.get(LoginChallenge, uuid.UUID(challenge_id))
        assert challenge is not None
        challenge.last_sent_at = datetime.now(UTC) - timedelta(seconds=61)
        session.commit()

    calls: list[dict[str, str]] = []

    def fake_send(*, to_address: str, subject: str, body_text: str) -> None:
        calls.append({"body_text": body_text})

    import cc_crm.api.v1.auth as auth_module

    old = auth_module.send_transactional_email
    auth_module.send_transactional_email = fake_send  # type: ignore[assignment]
    try:
        resend = client.post("/api/v1/auth/login/resend", json={"challenge_id": challenge_id})
        assert resend.status_code == 200
        new_code = _extract_code(calls)
    finally:
        auth_module.send_transactional_email = old  # type: ignore[assignment]

    # Der Zaehler wurde durch den Resend zurueckgesetzt - der neue Code wird
    # angenommen, obwohl vorher schon 5 Fehlversuche liefen.
    verify = client.post(
        "/api/v1/auth/login/verify", json={"challenge_id": challenge_id, "code": new_code}
    )
    assert verify.status_code == 200


def test_a_consumed_code_cannot_be_replayed(
    client: TestClient, _capture_sent_codes: list[dict[str, str]]
) -> None:
    client.headers.pop("Authorization", None)
    challenge_id = _start_login(client).json()["challenge_id"]
    code = _extract_code(_capture_sent_codes)

    first = client.post(
        "/api/v1/auth/login/verify", json={"challenge_id": challenge_id, "code": code}
    )
    assert first.status_code == 200

    replay = client.post(
        "/api/v1/auth/login/verify", json={"challenge_id": challenge_id, "code": code}
    )
    assert replay.status_code == 401


def test_trusted_device_token_skips_2fa_on_next_login(
    client: TestClient, _capture_sent_codes: list[dict[str, str]]
) -> None:
    client.headers.pop("Authorization", None)
    challenge_id = _start_login(client).json()["challenge_id"]
    code = _extract_code(_capture_sent_codes)

    verify = client.post(
        "/api/v1/auth/login/verify", json={"challenge_id": challenge_id, "code": code}
    )
    device_token = verify.json()["trusted_device_token"]
    assert device_token

    calls_before = len(_capture_sent_codes)
    second_login = client.post(
        "/api/v1/auth/login",
        json={
            "email": TEST_USER_EMAIL,
            "password": TEST_USER_PASSWORD,
            "trusted_device_token": device_token,
        },
    )
    assert second_login.status_code == 200
    body = second_login.json()
    assert body["status"] == "authenticated"
    assert body["token"]
    # Kein zweiter Code wurde verschickt - der 2FA-Schritt wurde uebersprungen.
    assert len(_capture_sent_codes) == calls_before

    me = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {body['token']}"})
    assert me.status_code == 200
    assert me.json()["email"] == TEST_USER_EMAIL


def test_trusted_device_token_is_bound_to_the_issuing_user(
    client: TestClient,
    session_factory: sessionmaker[Session],
    _capture_sent_codes: list[dict[str, str]],
) -> None:
    """Ein auf einem geteilten Browser hinterlegtes 'Geraet merken'-Cookie
    darf niemals den 2FA-Schritt fuer einen ANDEREN Account ueberspringen."""
    from cc_crm.core.security import hash_password
    from cc_crm.models.user import User

    client.headers.pop("Authorization", None)
    challenge_id = _start_login(client).json()["challenge_id"]
    code = _extract_code(_capture_sent_codes)
    verify = client.post(
        "/api/v1/auth/login/verify", json={"challenge_id": challenge_id, "code": code}
    )
    device_token = verify.json()["trusted_device_token"]

    with session_factory() as session:
        session.add(
            User(email="andere@commandeur.example", hashed_password=hash_password("pw123456"))
        )
        session.commit()

    calls_before = len(_capture_sent_codes)
    other_login = client.post(
        "/api/v1/auth/login",
        json={
            "email": "andere@commandeur.example",
            "password": "pw123456",
            "trusted_device_token": device_token,
        },
    )
    assert other_login.status_code == 200
    body = other_login.json()
    # Falscher Nutzer fuer dieses Geraet -> normaler 2FA-Flow, kein Skip.
    assert body["status"] == "challenge_required"
    assert len(_capture_sent_codes) == calls_before + 1


def test_login_with_wrong_password_is_rejected(client: TestClient) -> None:
    client.headers.pop("Authorization", None)

    response = _start_login(client, password="wrong-password")

    assert response.status_code == 401


def test_login_is_rate_limited_after_repeated_failures(client: TestClient) -> None:
    client.headers.pop("Authorization", None)
    login_rate_limiter.reset()

    for _ in range(MAX_ATTEMPTS):
        response = _start_login(client, password="wrong-password")
        assert response.status_code == 401

    blocked = _start_login(client, password="wrong-password")
    assert blocked.status_code == 429

    # Auch ein KORREKTES Passwort wird waehrend der Sperre abgelehnt - das
    # Rate-Limit greift vor jedem Passwort-Vergleich, nicht nur bei falschen
    # Versuchen.
    still_blocked = _start_login(client)
    assert still_blocked.status_code == 429

    login_rate_limiter.reset()


def test_login_ignores_spoofed_x_forwarded_for_when_cf_connecting_ip_present(
    client: TestClient,
) -> None:
    """Regressionsschutz fuer die auf Produktion bestaetigte Luecke: hinter
    Cloudflare (CF-Connecting-IP gesetzt) darf ein bei jedem Request neu
    erfundener X-Forwarded-For-Wert das Rate-Limit nicht mehr umgehen."""
    client.headers.pop("Authorization", None)
    login_rate_limiter.reset()

    for i in range(MAX_ATTEMPTS):
        response = client.post(
            "/api/v1/auth/login",
            json={"email": TEST_USER_EMAIL, "password": "wrong-password"},
            headers={
                "CF-Connecting-IP": "203.0.113.9",
                "X-Forwarded-For": f"10.13.37.{i}",  # anderer Fake-Wert pro Request
            },
        )
        assert response.status_code == 401

    blocked = client.post(
        "/api/v1/auth/login",
        json={"email": TEST_USER_EMAIL, "password": "wrong-password"},
        headers={
            "CF-Connecting-IP": "203.0.113.9",
            "X-Forwarded-For": "10.13.37.99",  # wieder ein neuer Fake-Wert
        },
    )
    assert blocked.status_code == 429

    login_rate_limiter.reset()


def test_login_rate_limit_triggers_exactly_one_security_alert(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Die Warnung wird in einem eigenen Thread verschickt (siehe
    api/v1/auth.py), daher hier per Event auf den Aufruf warten statt auf
    eine Race-Condition zu vertrauen."""
    client.headers.pop("Authorization", None)
    login_rate_limiter.reset()

    calls: list[dict[str, str]] = []
    fired = threading.Event()

    def fake_send_security_alert(subject: str, body: str, settings: object | None = None) -> None:
        calls.append({"subject": subject, "body": body})
        fired.set()

    monkeypatch.setattr(
        "cc_crm.api.v1.auth.send_security_alert",
        fake_send_security_alert,
    )

    for _ in range(MAX_ATTEMPTS):
        _start_login(client, password="wrong-password")
    assert fired.wait(timeout=2), "Sicherheitswarnung wurde nicht innerhalb von 2s ausgeloest"
    assert len(calls) == 1
    assert TEST_USER_EMAIL in calls[0]["body"]

    # Weitere Versuche waehrend der Sperre loesen KEINE erneute Warnung aus.
    _start_login(client, password="wrong-password")
    assert len(calls) == 1

    login_rate_limiter.reset()


def test_login_blocks_same_account_attacked_from_many_different_ips(
    client: TestClient,
) -> None:
    """Punkt 4 des Auftrags "5 Hoch-Punkte umsetzen": der bisherige
    IP-Zaehler allein sieht diesen Angriff NICHT, weil jede einzelne IP fuer
    sich nur einmal fehlschlaegt (bleibt unter MAX_ATTEMPTS=3 pro IP) - der
    neue Pro-Account-Zaehler muss trotzdem greifen, sobald EMAIL_MAX_ATTEMPTS
    fuer denselben Account erreicht ist, egal von wie vielen verschiedenen
    IPs aus."""
    client.headers.pop("Authorization", None)
    login_rate_limiter.reset()
    email_login_rate_limiter.reset()

    for i in range(EMAIL_MAX_ATTEMPTS):
        response = client.post(
            "/api/v1/auth/login",
            json={"email": TEST_USER_EMAIL, "password": "wrong-password"},
            headers={"CF-Connecting-IP": f"203.0.113.{i}"},
        )
        assert response.status_code == 401

    blocked = client.post(
        "/api/v1/auth/login",
        json={"email": TEST_USER_EMAIL, "password": "wrong-password"},
        headers={"CF-Connecting-IP": "203.0.113.250"},
    )
    assert blocked.status_code == 429

    login_rate_limiter.reset()
    email_login_rate_limiter.reset()


def test_login_still_blocks_different_accounts_from_the_same_ip_as_before(
    client: TestClient,
) -> None:
    """Regressionsschutz: der neue Pro-Account-Zaehler darf die bestehende
    Pro-IP-Sperre nicht ersetzen/abschwaechen - dieselbe IP, die
    MAX_ATTEMPTS-mal gegen (hier bewusst) verschiedene, nicht-existente
    Accounts fehlschlaegt, wird weiterhin ganz normal pro IP gesperrt."""
    client.headers.pop("Authorization", None)
    login_rate_limiter.reset()
    email_login_rate_limiter.reset()

    for i in range(MAX_ATTEMPTS):
        response = client.post(
            "/api/v1/auth/login",
            json={"email": f"nicht-existent-{i}@example.com", "password": "wrong-password"},
            headers={"CF-Connecting-IP": "198.51.100.42"},
        )
        assert response.status_code == 401

    blocked = client.post(
        "/api/v1/auth/login",
        json={"email": "noch-ein-anderer@example.com", "password": "wrong-password"},
        headers={"CF-Connecting-IP": "198.51.100.42"},
    )
    assert blocked.status_code == 429

    login_rate_limiter.reset()
    email_login_rate_limiter.reset()


def test_logout_invalidates_token(client: TestClient) -> None:
    token = client.headers["Authorization"].removeprefix("Bearer ")

    logout = client.post("/api/v1/auth/logout", headers={"Authorization": f"Bearer {token}"})
    assert logout.status_code == 204

    after_logout = client.get("/api/v1/candidates", headers={"Authorization": f"Bearer {token}"})
    assert after_logout.status_code == 401
