from cc_crm.core.rate_limit import LoginRateLimiter, client_ip


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
    limiter = LoginRateLimiter(max_attempts=3)
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
    limiter = LoginRateLimiter(max_attempts=3)

    assert limiter.record_failure("1.2.3.4") is False
    assert limiter.record_failure("1.2.3.4") is False
    assert limiter.record_failure("1.2.3.4") is True  # 3. Versuch loest die Sperre aus
    assert limiter.record_failure("1.2.3.4") is False  # bereits blockiert, keine erneute Warnung


def test_record_success_resets_failure_count() -> None:
    limiter = LoginRateLimiter(max_attempts=3)
    limiter.record_failure("1.2.3.4")
    limiter.record_failure("1.2.3.4")
    limiter.record_success("1.2.3.4")

    assert limiter.record_failure("1.2.3.4") is False
    assert not limiter.is_blocked("1.2.3.4")
