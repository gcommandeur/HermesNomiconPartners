"""Webhook-Zustellung gegen DNS-Rebinding (Review 2026-10-04, Punkt 8): die Verbindung geht an die
soeben geprueften IP, nicht an den Namen - httpx loest den Namen nicht ein zweites Mal auf."""

import uuid
from collections.abc import Iterator
from typing import Any

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from cc_crm.core.config import get_settings
from cc_crm.core.errors import BusinessRuleError
from cc_crm.infrastructure.database import session as db_session_module
from cc_crm.models.recruiting import AuditLog
from cc_crm.models.webhook import WebhookDelivery
from cc_crm.services import webhooks
from cc_crm.services.webhooks import WebhookService, dispatch_outbox
from tests.jobs import drain_jobs

_KEY = "S3Jm1m3O4ZVQ0xk0y2oUq2k8x6mQ4oY7Qk0rj0s0yX8="
PUBLIC = "93.184.216.34"


@pytest.fixture(autouse=True)
def _wire(
    monkeypatch: pytest.MonkeyPatch, session_factory: sessionmaker[Session]
) -> Iterator[None]:
    get_settings.cache_clear()
    monkeypatch.setenv("CC_CRM_MAIL_CREDENTIALS_ENCRYPTION_KEY", _KEY)
    monkeypatch.setattr(db_session_module, "SessionLocal", session_factory)
    yield
    get_settings.cache_clear()


class _FakeClient:
    """Ersetzt httpx.Client: merkt sich den Aufruf, sendet nichts."""

    calls: list[dict[str, Any]] = []
    init: list[dict[str, Any]] = []

    def __init__(self, **kwargs: Any) -> None:
        _FakeClient.init.append(kwargs)

    def __enter__(self) -> "_FakeClient":
        return self

    def __exit__(self, *exc: object) -> None:
        return None

    def post(self, url: str, **kwargs: Any) -> Any:
        _FakeClient.calls.append({"url": url, **kwargs})

        class _Response:
            status_code = 204

        return _Response()


@pytest.fixture
def fake_http(monkeypatch: pytest.MonkeyPatch) -> type[_FakeClient]:
    _FakeClient.calls = []
    _FakeClient.init = []
    monkeypatch.setattr(webhooks.httpx, "Client", _FakeClient)
    return _FakeClient


def test_the_connection_goes_to_the_validated_ip_with_the_original_name_in_host_and_sni(
    monkeypatch: pytest.MonkeyPatch, fake_http: type[_FakeClient]
) -> None:
    monkeypatch.setattr(webhooks, "_resolve_host", lambda host: [PUBLIC])
    status = webhooks._http_post("https://hook.example/pfad/x?a=1", {"X-Test": "1"}, "{}")
    assert status == 204
    call = fake_http.calls[0]
    assert call["url"] == f"https://{PUBLIC}:443/pfad/x?a=1"  # IP statt Name in der URL
    assert call["headers"]["Host"] == "hook.example"
    assert call["headers"]["X-Test"] == "1"
    assert call["extensions"] == {"sni_hostname": "hook.example"}  # Zertifikat fuer den Namen
    assert fake_http.init[0]["follow_redirects"] is False
    assert fake_http.init[0]["trust_env"] is False


def test_ipv6_literals_get_brackets_and_a_custom_port_stays_in_the_host_header(
    monkeypatch: pytest.MonkeyPatch, fake_http: type[_FakeClient]
) -> None:
    monkeypatch.setattr(
        webhooks, "_resolve_host", lambda host: ["2606:2800:220:1:248:1893:25c8:1946"]
    )
    webhooks._http_post("https://hook.example:8443/", {}, "{}")
    call = fake_http.calls[0]
    assert call["url"] == "https://[2606:2800:220:1:248:1893:25c8:1946]:8443/"
    assert call["headers"]["Host"] == "hook.example:8443"


def test_a_second_resolution_that_flips_to_a_private_ip_is_refused(
    monkeypatch: pytest.MonkeyPatch, fake_http: type[_FakeClient]
) -> None:
    """Pruefung sieht eine oeffentliche IP, der Versand loest erneut auf und bekommt eine interne:
    der Versand muss scheitern, ohne dass eine Verbindung aufgebaut wird."""
    answers = iter([[PUBLIC], ["10.0.0.5"], ["10.0.0.5"]])
    monkeypatch.setattr(webhooks, "_resolve_host", lambda host: next(answers))
    webhooks.validate_webhook_url("https://hook.example/in")  # 1. Aufloesung: oeffentlich
    with pytest.raises(BusinessRuleError, match="privaten"):
        webhooks._http_post("https://hook.example/in", {}, "{}")  # 2. Aufloesung: intern
    assert fake_http.calls == []  # nie verbunden


def test_all_resolved_addresses_must_be_public(
    monkeypatch: pytest.MonkeyPatch, fake_http: type[_FakeClient]
) -> None:
    monkeypatch.setattr(webhooks, "_resolve_host", lambda host: [PUBLIC, "169.254.169.254"])
    with pytest.raises(BusinessRuleError):
        webhooks._http_post("https://hook.example/in", {}, "{}")
    assert fake_http.calls == []


def test_a_delivery_fails_when_the_name_flips_to_a_private_ip_after_validation(
    session_factory: sessionmaker[Session],
    monkeypatch: pytest.MonkeyPatch,
    fake_http: type[_FakeClient],
) -> None:
    # Anlegen und erste Pruefung (Aufloesung 1) oeffentlich, danach nur noch intern.
    monkeypatch.setattr(webhooks, "_resolve_host", lambda host: [PUBLIC])
    with session_factory() as session:
        WebhookService(session).create("Test", "https://hook.example/in", ["*"], None)
        session.add(AuditLog(entity_type="candidate", entity_id=uuid.uuid4(), action="created"))
        session.commit()
    answers = iter([[PUBLIC]])  # nur die Pruefung in deliver() sieht oeffentlich
    monkeypatch.setattr(webhooks, "_resolve_host", lambda host: next(answers, ["10.0.0.5"]))
    dispatch_outbox(session_factory)
    drain_jobs(session_factory)
    with session_factory() as session:
        delivery = session.scalars(select(WebhookDelivery)).one()
        assert delivery.status != "delivered"
        assert "privaten" in (delivery.last_error or "")
    assert fake_http.calls == []  # keine Verbindung zur internen Adresse


def test_real_httpx_receives_ip_url_host_header_and_sni(monkeypatch: pytest.MonkeyPatch) -> None:
    """Gegenprobe mit dem ECHTEN httpx (Transport ersetzt, es wird nichts gesendet): die
    Anfrage traegt die IP in der URL, den Namen im Host-Header und `sni_hostname`."""
    import httpx

    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(204)

    real_client = httpx.Client
    monkeypatch.setattr(webhooks, "_resolve_host", lambda host: [PUBLIC])
    monkeypatch.setattr(
        webhooks.httpx,
        "Client",
        lambda **kwargs: real_client(transport=httpx.MockTransport(handler), **kwargs),
    )
    assert webhooks._http_post("https://hook.example/in?x=1", {"X-Test": "1"}, '{"a":1}') == 204
    request = seen[0]
    assert request.url.host == PUBLIC and request.url.port in (None, 443)  # 443 ist Standard
    assert request.url.path == "/in" and request.url.query == b"x=1"
    assert request.headers["host"] == "hook.example"
    assert request.extensions["sni_hostname"] == "hook.example"
    assert request.content == b'{"a":1}'
