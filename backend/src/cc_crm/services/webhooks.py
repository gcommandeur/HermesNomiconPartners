"""Ausgehende Webhooks: Ziele verwalten, Ereignisse aus der Outbox verteilen,
signiert zustellen (Standard-Webhooks-Format).

Ablauf: Audit-Eintrag -> Zeile in `event_outbox` (gleiche Transaktion, siehe
models/event_outbox.py) -> `dispatch_outbox` legt je passendem Ziel eine
`WebhookDelivery` + einen Job `webhook.deliver` an -> der Handler sendet, bei
Fehler wiederholt die Job-Warteschlange mit wachsendem Abstand, nach dem letzten
Versuch gilt die Zustellung als "dead" (Admin kann neu anstossen).

Datenschutz: die Nutzlast enthaelt nur Ereignisart und IDs, keine
Personendaten; der Empfaenger holt Details per API-Key.

Sicherheit: nur https, keine Adressen im privaten/internen Netz (SSRF), keine
Weiterleitungen, kurzes Zeitlimit, Geheimnis verschluesselt gespeichert.
"""

from __future__ import annotations

import base64
import fnmatch
import hashlib
import hmac
import ipaddress
import json
import logging
import secrets
import socket
import time
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any
from urllib.parse import urlsplit

import httpx
from sqlalchemy import delete, select
from sqlalchemy.orm import Session, sessionmaker

from cc_crm.core.errors import BusinessRuleError, EntityNotFoundError
from cc_crm.models.background_job import BackgroundJob
from cc_crm.models.event_outbox import EventOutbox
from cc_crm.models.webhook import WebhookDelivery, WebhookEndpoint
from cc_crm.services.job_queue import enqueue
from cc_crm.services.mail_credentials import decrypt_password, encrypt_password

logger = logging.getLogger("cc_crm.webhooks")

SECRET_PREFIX = "whsec_"
DELIVERY_JOB = "webhook.deliver"
MAX_DELIVERY_ATTEMPTS = 6
REQUEST_TIMEOUT_SECONDS = 10.0
OUTBOX_BATCH = 100
OUTBOX_RETENTION = timedelta(days=14)
_PURGE_INTERVAL_SECONDS = 3600.0
_last_purge = 0.0


class WebhookDeliveryError(Exception):
    """Zustellung fehlgeschlagen - loest die Wiederholung der Warteschlange aus."""


def _now() -> datetime:
    return datetime.now(UTC)


# --- URL-Pruefung (SSRF) -------------------------------------------------


def _resolve_host(host: str) -> list[str]:
    try:
        infos = socket.getaddrinfo(host, None, proto=socket.IPPROTO_TCP)
    except socket.gaierror as exc:
        raise BusinessRuleError(f"Adresse '{host}' laesst sich nicht aufloesen.") from exc
    return sorted({str(info[4][0]) for info in infos})


def validate_webhook_url(url: str) -> None:
    parts = urlsplit(url.strip())
    if parts.scheme != "https":
        raise BusinessRuleError("Webhook-Adressen muessen mit https:// beginnen.")
    if not parts.hostname or parts.username or parts.password:
        raise BusinessRuleError("Ungueltige Webhook-Adresse.")
    for address in _resolve_host(parts.hostname):
        ip = ipaddress.ip_address(address.split("%")[0])
        if (
            ip.is_private
            or ip.is_loopback
            or ip.is_link_local
            or ip.is_reserved
            or ip.is_multicast
            or ip.is_unspecified
        ):
            raise BusinessRuleError(
                "Webhook-Adressen im privaten oder internen Netz sind nicht erlaubt."
            )


# --- Geheimnis und Signatur ---------------------------------------------


def generate_secret() -> str:
    return SECRET_PREFIX + base64.b64encode(secrets.token_bytes(24)).decode("ascii")


def sign(secret: str, message_id: str, timestamp: int, body: str) -> str:
    """Standard-Webhooks: HMAC-SHA256 ueber "{id}.{timestamp}.{body}", Schluessel
    ist der base64-dekodierte Teil nach "whsec_"; Ergebnis "v1,<base64>"."""
    key = base64.b64decode(secret.removeprefix(SECRET_PREFIX))
    digest = hmac.new(key, f"{message_id}.{timestamp}.{body}".encode(), hashlib.sha256).digest()
    return "v1," + base64.b64encode(digest).decode("ascii")


def matches(patterns: list[str], event_type: str) -> bool:
    return any(pattern == "*" or fnmatch.fnmatchcase(event_type, pattern) for pattern in patterns)


# --- Verwaltung ----------------------------------------------------------


def _clean_patterns(patterns: list[str]) -> list[str]:
    cleaned = [pattern.strip() for pattern in patterns if pattern.strip()]
    if not cleaned:
        raise BusinessRuleError("Mindestens eine Ereignisart (oder *) angeben.")
    return cleaned


class WebhookService:
    def __init__(self, session: Session) -> None:
        self.session = session

    def list_all(self) -> list[WebhookEndpoint]:
        return list(
            self.session.scalars(select(WebhookEndpoint).order_by(WebhookEndpoint.created_at))
        )

    def get(self, endpoint_id: uuid.UUID) -> WebhookEndpoint:
        endpoint = self.session.get(WebhookEndpoint, endpoint_id)
        if endpoint is None:
            raise EntityNotFoundError("Webhook nicht gefunden")
        return endpoint

    def create(
        self, name: str, url: str, event_types: list[str], created_by: uuid.UUID | None
    ) -> tuple[WebhookEndpoint, str]:
        validate_webhook_url(url)
        secret = generate_secret()
        endpoint = WebhookEndpoint(
            name=name.strip(),
            url=url.strip(),
            secret_encrypted=encrypt_password(secret),
            event_types=_clean_patterns(event_types),
            created_by_user_id=created_by,
        )
        self.session.add(endpoint)
        self.session.commit()
        return endpoint, secret

    def update(
        self,
        endpoint_id: uuid.UUID,
        *,
        name: str | None,
        url: str | None,
        event_types: list[str] | None,
        is_active: bool | None,
    ) -> WebhookEndpoint:
        endpoint = self.get(endpoint_id)
        if url is not None:
            validate_webhook_url(url)
            endpoint.url = url.strip()
        if name is not None:
            endpoint.name = name.strip()
        if event_types is not None:
            endpoint.event_types = _clean_patterns(event_types)
        if is_active is not None:
            endpoint.is_active = is_active
        self.session.commit()
        return endpoint

    def rotate_secret(self, endpoint_id: uuid.UUID) -> tuple[WebhookEndpoint, str]:
        endpoint = self.get(endpoint_id)
        secret = generate_secret()
        endpoint.secret_encrypted = encrypt_password(secret)
        self.session.commit()
        return endpoint, secret

    def delete(self, endpoint_id: uuid.UUID) -> None:
        self.session.delete(self.get(endpoint_id))
        self.session.commit()

    def deliveries(self, endpoint_id: uuid.UUID, limit: int = 50) -> list[WebhookDelivery]:
        self.get(endpoint_id)
        return list(
            self.session.scalars(
                select(WebhookDelivery)
                .where(WebhookDelivery.endpoint_id == endpoint_id)
                .order_by(WebhookDelivery.created_at.desc())
                .limit(limit)
            )
        )

    def send_test(self, endpoint_id: uuid.UUID) -> WebhookDelivery:
        endpoint = self.get(endpoint_id)
        return _queue_delivery(self.session, endpoint, "ping", {}, None)

    def retry_delivery(self, delivery_id: uuid.UUID) -> WebhookDelivery:
        delivery = self.session.get(WebhookDelivery, delivery_id)
        if delivery is None:
            raise EntityNotFoundError("Zustellung nicht gefunden")
        if delivery.status != "dead":
            raise BusinessRuleError("Nur aufgegebene Zustellungen koennen neu gestartet werden.")
        delivery.status = "pending"
        delivery.attempts = 0
        delivery.last_error = None
        enqueue(
            self.session,
            DELIVERY_JOB,
            {"delivery_id": str(delivery.id)},
            max_attempts=MAX_DELIVERY_ATTEMPTS,
            commit=False,
        )
        self.session.commit()
        return delivery


# --- Verteilen -----------------------------------------------------------


def _queue_delivery(
    session: Session,
    endpoint: WebhookEndpoint,
    event_type: str,
    data: dict[str, Any],
    outbox_id: uuid.UUID | None,
) -> WebhookDelivery:
    delivery = WebhookDelivery(
        endpoint_id=endpoint.id,
        outbox_id=outbox_id,
        event_type=event_type,
        payload={"type": event_type, "timestamp": _now().isoformat(), "data": data},
    )
    session.add(delivery)
    session.flush()
    enqueue(
        session,
        DELIVERY_JOB,
        {"delivery_id": str(delivery.id)},
        max_attempts=MAX_DELIVERY_ATTEMPTS,
        commit=False,
    )
    session.commit()
    return delivery


def dispatch_outbox(session_factory: sessionmaker[Session]) -> int:
    """Verteilt neue Outbox-Ereignisse an passende aktive Ziele. Gibt die Zahl
    verarbeiteter Ereignisse zurueck. Mehrere Worker: SKIP LOCKED."""
    global _last_purge
    with session_factory() as session:
        rows = list(
            session.scalars(
                select(EventOutbox)
                .where(EventOutbox.dispatched_at.is_(None))
                .order_by(EventOutbox.created_at)
                .limit(OUTBOX_BATCH)
                .with_for_update(skip_locked=True)
            )
        )
        if rows:
            endpoints = list(
                session.scalars(select(WebhookEndpoint).where(WebhookEndpoint.is_active.is_(True)))
            )
            for row in rows:
                data = {
                    "entity_type": row.entity_type,
                    "entity_id": str(row.entity_id),
                    "audit_log_id": str(row.audit_log_id) if row.audit_log_id else None,
                }
                for endpoint in endpoints:
                    if matches(endpoint.event_types, row.event_type):
                        delivery = WebhookDelivery(
                            endpoint_id=endpoint.id,
                            outbox_id=row.id,
                            event_type=row.event_type,
                            payload={
                                "type": row.event_type,
                                "timestamp": row.created_at.isoformat(),
                                "data": data,
                            },
                        )
                        session.add(delivery)
                        session.flush()
                        enqueue(
                            session,
                            DELIVERY_JOB,
                            {"delivery_id": str(delivery.id)},
                            max_attempts=MAX_DELIVERY_ATTEMPTS,
                            commit=False,
                        )
                row.dispatched_at = _now()
        session.commit()
        monotonic = time.monotonic()
        if monotonic - _last_purge > _PURGE_INTERVAL_SECONDS:
            _last_purge = monotonic
            session.execute(
                delete(EventOutbox).where(
                    EventOutbox.dispatched_at < _now() - OUTBOX_RETENTION,
                )
            )
            session.commit()
        return len(rows)


# --- Zustellen -----------------------------------------------------------


def _http_post(url: str, headers: dict[str, str], body: str) -> int:
    response = httpx.post(
        url,
        content=body.encode(),
        headers=headers,
        timeout=REQUEST_TIMEOUT_SECONDS,
        follow_redirects=False,
    )
    return response.status_code


def deliver(job: BackgroundJob) -> None:
    """Handler des Jobs `webhook.deliver` (siehe services/job_handlers.py)."""
    from cc_crm.infrastructure.database.session import SessionLocal

    delivery_id = uuid.UUID(job.payload["delivery_id"])
    with SessionLocal() as session:
        delivery = session.get(WebhookDelivery, delivery_id)
        if delivery is None:
            return
        endpoint = session.get(WebhookEndpoint, delivery.endpoint_id)
        if endpoint is None or not endpoint.is_active:
            delivery.status = "dead"
            delivery.last_error = "Ziel geloescht oder deaktiviert."
            session.commit()
            return
        delivery.attempts = job.attempts
        error: str | None = None
        try:
            validate_webhook_url(endpoint.url)  # Adresse kann sich seit Anlage geaendert haben
            body = json.dumps(delivery.payload, separators=(",", ":"), sort_keys=True)
            timestamp = int(time.time())
            message_id = f"msg_{delivery.id.hex}"
            status_code = _http_post(
                endpoint.url,
                {
                    "Content-Type": "application/json",
                    "webhook-id": message_id,
                    "webhook-timestamp": str(timestamp),
                    "webhook-signature": sign(
                        decrypt_password(endpoint.secret_encrypted), message_id, timestamp, body
                    ),
                    "User-Agent": "HermesCRM-Webhooks/1",
                },
                body,
            )
            delivery.response_status = status_code
            if not 200 <= status_code < 300:
                error = f"Empfaenger antwortete mit HTTP {status_code}"
        except BusinessRuleError as exc:
            error = str(exc)
        except httpx.HTTPError as exc:
            error = f"{type(exc).__name__}: {exc}"[:500]
        if error is None:
            delivery.status = "delivered"
            delivery.delivered_at = _now()
            delivery.last_error = None
            session.commit()
            return
        delivery.last_error = error[:1000]
        delivery.status = "dead" if job.attempts >= job.max_attempts else "retrying"
        session.commit()
        raise WebhookDeliveryError(error)
