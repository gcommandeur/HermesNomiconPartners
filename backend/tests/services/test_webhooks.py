"""Outbox, Webhook-Verteilung und signierte Zustellung."""

import uuid
from collections.abc import Iterator

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from cc_crm.core.config import get_settings
from cc_crm.core.errors import BusinessRuleError
from cc_crm.infrastructure.database import session as db_session_module
from cc_crm.models.background_job import BackgroundJob
from cc_crm.models.event_outbox import EventOutbox
from cc_crm.models.recruiting import AuditLog
from cc_crm.models.webhook import WebhookDelivery
from cc_crm.services import webhooks
from cc_crm.services.job_queue import process_one
from cc_crm.services.webhooks import WebhookService, dispatch_outbox, matches, sign
from tests.jobs import drain_jobs

_KEY = "S3Jm1m3O4ZVQ0xk0y2oUq2k8x6mQ4oY7Qk0rj0s0yX8="


@pytest.fixture(autouse=True)
def _wire(
    monkeypatch: pytest.MonkeyPatch, session_factory: sessionmaker[Session]
) -> Iterator[None]:
    get_settings.cache_clear()
    monkeypatch.setenv("CC_CRM_MAIL_CREDENTIALS_ENCRYPTION_KEY", _KEY)
    monkeypatch.setattr(db_session_module, "SessionLocal", session_factory)
    monkeypatch.setattr(webhooks, "_resolve_host", lambda host: ["93.184.216.34"])
    yield
    get_settings.cache_clear()


def _endpoint(
    session: Session, patterns: list[str] | None = None, url: str = "https://hook.example/in"
) -> tuple[uuid.UUID, str]:
    endpoint, secret = WebhookService(session).create("Test", url, patterns or ["*"], None)
    return endpoint.id, secret


def _audit(session: Session, entity_type: str = "candidate", action: str = "created") -> None:
    session.add(AuditLog(entity_type=entity_type, entity_id=uuid.uuid4(), action=action))
    session.commit()


def test_signature_matches_the_standard_webhooks_reference_vector() -> None:
    signature = sign(
        "whsec_MfKQ9r8GKYqrTwjUPD8ILPZIo2LaLaSw",
        "msg_p5jXN8AQM9LWM0D4loKWxJek",
        1614265330,
        '{"test": 2432232314}',
    )
    assert signature == "v1,g0hM9SsE+OTPJTGt/tmIKtSyZlE3uFJELVlNIOLJ1OE="


def test_event_pattern_matching() -> None:
    assert matches(["*"], "candidate.created")
    assert matches(["candidate.*"], "candidate.created")
    assert matches(["candidate.created"], "candidate.created")
    assert not matches(["candidate.*"], "candidate_submission.created")
    assert not matches(["fee.paid"], "fee.created")


@pytest.mark.parametrize(
    "url", ["http://hook.example/in", "ftp://x.example", "https://user:pw@hook.example/in", "nope"]
)
def test_only_plain_https_urls_are_accepted(
    session_factory: sessionmaker[Session], url: str
) -> None:
    with session_factory() as session, pytest.raises(BusinessRuleError):
        _endpoint(session, url=url)


@pytest.mark.parametrize(
    "address", ["127.0.0.1", "10.0.0.5", "192.168.1.1", "169.254.169.254", "::1"]
)
def test_internal_addresses_are_rejected(
    session_factory: sessionmaker[Session], monkeypatch: pytest.MonkeyPatch, address: str
) -> None:
    monkeypatch.setattr(webhooks, "_resolve_host", lambda host: [address])
    with session_factory() as session, pytest.raises(BusinessRuleError):
        _endpoint(session)


def test_every_audit_entry_creates_exactly_one_outbox_row(
    session_factory: sessionmaker[Session],
) -> None:
    with session_factory() as session:
        _audit(session, "candidate_submission", "status_changed")
        rows = session.scalars(select(EventOutbox)).all()
    assert [row.event_type for row in rows] == ["candidate_submission.status_changed"]
    assert rows[0].dispatched_at is None


def test_dispatch_only_creates_deliveries_for_matching_active_endpoints(
    session_factory: sessionmaker[Session],
) -> None:
    with session_factory() as session:
        matching, _ = _endpoint(session, ["candidate.*"])
        _endpoint(session, ["fee.*"])
        inactive, _ = _endpoint(session, ["*"])
        WebhookService(session).update(
            inactive, name=None, url=None, event_types=None, is_active=False
        )
        _audit(session, "candidate", "created")

    assert dispatch_outbox(session_factory) == 1
    assert dispatch_outbox(session_factory) == 0  # nichts doppelt

    with session_factory() as session:
        deliveries = session.scalars(select(WebhookDelivery)).all()
        jobs = session.scalars(select(BackgroundJob).where(BackgroundJob.kind == "webhook.deliver"))
        assert [d.endpoint_id for d in deliveries] == [matching]
        assert len(list(jobs)) == 1
        assert session.scalars(select(EventOutbox)).one().dispatched_at is not None
        # Nur IDs und Ereignisart, keine Personendaten.
        assert set(deliveries[0].payload["data"]) == {"entity_type", "entity_id", "audit_log_id"}


def test_delivery_is_signed_and_marked_delivered(
    session_factory: sessionmaker[Session], monkeypatch: pytest.MonkeyPatch
) -> None:
    sent: list[tuple[str, dict[str, str], str]] = []
    monkeypatch.setattr(
        webhooks, "_http_post", lambda url, headers, body: sent.append((url, headers, body)) or 204
    )
    with session_factory() as session:
        _, secret = _endpoint(session)
        _audit(session)
    dispatch_outbox(session_factory)
    drain_jobs(session_factory)

    assert len(sent) == 1
    url, headers, body = sent[0]
    assert url == "https://hook.example/in"
    assert headers["webhook-signature"] == sign(
        secret, headers["webhook-id"], int(headers["webhook-timestamp"]), body
    )
    with session_factory() as session:
        delivery = session.scalars(select(WebhookDelivery)).one()
        assert delivery.status == "delivered"
        assert delivery.response_status == 204
        assert delivery.attempts == 1


def test_failed_delivery_retries_and_finally_goes_dead_then_can_be_retried(
    session_factory: sessionmaker[Session], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(webhooks, "_http_post", lambda url, headers, body: 500)
    with session_factory() as session:
        _endpoint(session)
        _audit(session)
    dispatch_outbox(session_factory)

    assert process_one(session_factory) is True
    with session_factory() as session:
        delivery = session.scalars(select(WebhookDelivery)).one()
        assert delivery.status == "retrying"
        assert "500" in (delivery.last_error or "")
        job = session.scalars(
            select(BackgroundJob).where(BackgroundJob.kind == "webhook.deliver")
        ).one()
        job.attempts = job.max_attempts - 1  # naechster Versuch ist der letzte
        job.run_after = job.run_after.replace(year=2000)
        session.commit()
    assert process_one(session_factory) is True
    with session_factory() as session:
        delivery = session.scalars(select(WebhookDelivery)).one()
        assert delivery.status == "dead"
        delivery_id = delivery.id
        WebhookService(session).retry_delivery(delivery_id)

    monkeypatch.setattr(webhooks, "_http_post", lambda url, headers, body: 200)
    drain_jobs(session_factory)
    with session_factory() as session:
        assert session.get(WebhookDelivery, delivery_id).status == "delivered"  # type: ignore[union-attr]


def test_deactivated_endpoint_does_not_receive_pending_delivery(
    session_factory: sessionmaker[Session], monkeypatch: pytest.MonkeyPatch
) -> None:
    sent: list[str] = []
    monkeypatch.setattr(webhooks, "_http_post", lambda url, headers, body: sent.append(url) or 200)
    with session_factory() as session:
        endpoint_id, _ = _endpoint(session)
        _audit(session)
    dispatch_outbox(session_factory)
    with session_factory() as session:
        WebhookService(session).update(
            endpoint_id, name=None, url=None, event_types=None, is_active=False
        )
    drain_jobs(session_factory)
    assert sent == []
    with session_factory() as session:
        assert session.scalars(select(WebhookDelivery)).one().status == "dead"
