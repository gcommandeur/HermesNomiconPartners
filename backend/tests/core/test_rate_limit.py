from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from cc_crm.core.rate_limit import LoginRateLimiter, client_ip, email_rate_limit_key
from cc_crm.infrastructure.database import session as db_session_module
from cc_crm.models.rate_limit_attempt import RateLimitAttempt


@pytest.fixture(autouse=True)
def _use_isolated_db(
    monkeypatch: pytest.MonkeyPatch, session_factory: sessionmaker[Session]
) -> None:
    """Der Rate-Limiter ist DB-gestuetzt (siehe core/rate_limit.py) - ohne
    dies wuerden diese Tests Zeilen in die echte lokale Dev-/Produktions-DB
    schreiben statt in die isolierte Test-Engine (gleiches Muster wie
    tests/conftest.py::client fuer den kompletten API-Testlauf)."""
    monkeypatch.setattr(db_session_module, "SessionLocal", session_factory)


def test_client_ip_prefers_cf_connecting_ip_over_forwarded_for() -> None:
    """CF-Connecting-IP wird von Cloudflare selbst am Edge gesetzt und kann
    vom Client nicht gefaelscht werden - muss also Vorrang vor dem
    client-kontrollierbaren X-Forwarded-For haben."""
    assert (
        client_ip("203.0.113.9", "10.13.37.1, 198.51.100.1", "127.0.0.1")
        == "203.0.113.9"
    )


def test_client_ip_falls_back_to_forwarded_for_without_cloudflare() -> None:
    assert client_ip(None, "198.51.100.1, 10.0.0.1", "127.0.0.1") == "198.51.100.1"


def test_client_ip_falls_back_to_direct_host_without_any_proxy_headers() -> None:
    assert client_ip(None, None, "127.0.0.1") == "127.0.0.1"


def test_client_ip_falls_back_to_unknown_without_any_source() -> None:
    assert client_ip(None, None, None) == "unknown"


def test_spoofed_forwarded_for_cannot_bypass_rate_limit_behind_cloudflare() -> None:
    """Regressionsschutz fuer die auf Produktion bestaetigte Luecke: ein
    Angreifer, der bei jedem Request einen neu erfundenen X-Forwarded-For-Wert
    mitschickt, darf das Rate-Limit nicht mehr umgehen koennen, solange
    CF-Connecting-IP vorhanden ist (Produktionsfall hinter Cloudflare)."""
    limiter = LoginRateLimiter("test_ip", max_attempts=3)
    real_ip = "203.0.113.9"

    for i in range(5):
        spoofed_xff = f"10.13.37.{i}"
        ip = client_ip(real_ip, spoofed_xff, "127.0.0.1")
        assert ip == real_ip
        limiter.record_failure(ip)

    assert limiter.is_blocked(real_ip)


def test_record_failure_returns_true_only_on_the_blocking_attempt() -> None:
    """Nur der Versuch, der die Sperre neu ausloest, soll True liefern -
    steuert, dass genau eine Sicherheitswarnung pro Ausbruch verschickt wird
    (siehe api/v1/auth.py)."""
    limiter = LoginRateLimiter("test_blocking_attempt", max_attempts=3)

    assert limiter.record_failure("1.2.3.4") is False
    assert limiter.record_failure("1.2.3.4") is False
    assert limiter.record_failure("1.2.3.4") is True  # 3. Versuch loest die Sperre aus
    assert limiter.record_failure("1.2.3.4") is False  # bereits blockiert, keine erneute Warnung


def test_record_success_resets_failure_count() -> None:
    limiter = LoginRateLimiter("test_success_reset", max_attempts=3)
    limiter.record_failure("1.2.3.4")
    limiter.record_failure("1.2.3.4")
    limiter.record_success("1.2.3.4")

    assert limiter.record_failure("1.2.3.4") is False
    assert not limiter.is_blocked("1.2.3.4")


def test_email_rate_limit_key_normalizes_case_and_whitespace() -> None:
    """Punkt 4 des Auftrags "5 Hoch-Punkte umsetzen": ohne Normalisierung
    liesse sich der Pro-Account-Zaehler durch Gross-/Kleinschreibung der
    E-Mail-Adresse umgehen - "Foo@Bar.de" und "foo@bar.de" muessen denselben
    Zaehler treffen."""
    assert email_rate_limit_key("Foo@Bar.de") == email_rate_limit_key(" foo@bar.de ")


def test_email_limiter_blocks_the_same_account_independently_of_ip() -> None:
    """Der Pro-Account-Zaehler ist ein eigenstaendiger LoginRateLimiter mit
    eigenen Grenzwerten - er blockt allein aufgrund des E-Mail-Schluessels,
    unabhaengig davon, von welcher IP aus die Versuche kamen (das Zuordnen
    zur richtigen IP ist Aufgabe des separaten login_rate_limiter, nicht
    dieses Zaehlers)."""
    limiter = LoginRateLimiter("test_email_scope", max_attempts=5)
    key = email_rate_limit_key("opfer@example.com")

    for _ in range(4):
        assert limiter.record_failure(key) is False
    assert limiter.record_failure(key) is True
    assert limiter.is_blocked(key)


def test_different_scopes_do_not_interfere_with_each_other() -> None:
    """Punkt 2 des DB-Rate-Limiter-Auftrags: alle vier Zaehler teilen sich
    EINE Tabelle (rate_limit_attempts) - der scope muss Zeilen verschiedener
    Zaehler zuverlaessig auseinanderhalten, sonst wuerden z.B. IP- und
    E-Mail-Fehlversuche sich gegenseitig blockieren."""
    limiter_a = LoginRateLimiter("scope_a", max_attempts=2)
    limiter_b = LoginRateLimiter("scope_b", max_attempts=2)
    same_key = "shared-key"

    limiter_a.record_failure(same_key)
    limiter_a.record_failure(same_key)
    assert limiter_a.is_blocked(same_key)
    assert not limiter_b.is_blocked(same_key)


def test_rows_persist_across_limiter_instances_with_the_same_scope() -> None:
    """Kernanforderung des DB-Umbaus: der Zustand liegt in der DB, nicht im
    Prozessspeicher - eine ZWEITE LoginRateLimiter-Instanz mit demselben
    scope sieht dieselben bereits gezaehlten Fehlversuche (simuliert einen
    Neustart/eine zweite App-Instanz, ohne dass eine echte zweite
    Instanz noetig ist)."""
    first_instance = LoginRateLimiter("persisted_scope", max_attempts=3)
    first_instance.record_failure("9.9.9.9")
    first_instance.record_failure("9.9.9.9")

    second_instance = LoginRateLimiter("persisted_scope", max_attempts=3)
    assert second_instance.record_failure("9.9.9.9") is True


def test_record_failure_prunes_rows_older_than_one_day(
    session_factory: sessionmaker[Session],
) -> None:
    """Teil 2 des Auftrags: "bei jedem Insert beilaeufig Zeilen aelter als 1
    Tag loeschen" - kein separater Cron-Job noetig. Legt eine 2 Tage alte
    Zeile eines ANDEREN Scopes direkt an (record_failure() selbst kann kein
    altes Datum erzeugen), ruft record_failure() fuer irgendeinen Schluessel
    auf und prueft, dass die alte Zeile danach weg ist."""
    with session_factory() as session:
        session.add(
            RateLimitAttempt(
                scope="some_other_scope",
                key="irrelevant",
                created_at=datetime.now(UTC) - timedelta(days=2),
            )
        )
        session.commit()

    limiter = LoginRateLimiter("cleanup_trigger_scope", max_attempts=99)
    limiter.record_failure("1.1.1.1")

    with session_factory() as session:
        remaining = session.scalars(
            select(RateLimitAttempt).where(RateLimitAttempt.scope == "some_other_scope")
        ).all()
        assert remaining == []
