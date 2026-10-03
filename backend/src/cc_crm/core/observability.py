"""Einfaches Betriebs-Monitoring ohne Pflicht-Dienst: JSON-Logzeilen, Request-ID,
Warnung bei langsamen Requests und langsamen SQL-Abfragen, optional Sentry.

Bewusst klein gehalten: DigitalOcean sammelt stdout ohnehin; eine Logzeile pro
Request mit Request-ID reicht, um "was ist um 14:03 passiert" zu beantworten. Sentry
wird nur aktiv, wenn CC_CRM_SENTRY_DSN gesetzt ist (siehe core/config.py)."""

from __future__ import annotations

import contextvars
import json
import logging
import re
import time
import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import Engine, event
from starlette.types import ASGIApp, Message, Receive, Scope, Send

logger = logging.getLogger("cc_crm.request")
sql_logger = logging.getLogger("cc_crm.sql")

REQUEST_ID_HEADER = "X-Request-ID"
# Nur kurze, harmlose Zeichen aus fremden Headern uebernehmen (Log-Injection).
_SAFE_REQUEST_ID = re.compile(r"^[A-Za-z0-9._-]{8,64}$")

SLOW_REQUEST_SECONDS = 1.0
SLOW_SQL_SECONDS = 0.3

request_id_var: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "request_id", default=None
)
# Veraenderlicher Behaelter statt einer einfachen Variable: synchrone FastAPI-
# Abhaengigkeiten laufen in einem Thread mit KOPIERTEM Kontext, ein dort gesetzter
# Wert ginge fuer die Middleware verloren - die Mutation des gemeinsamen
# Objekts dagegen nicht.
request_state_var: contextvars.ContextVar[dict[str, str | None] | None] = contextvars.ContextVar(
    "request_state", default=None
)


def set_request_user(user_id: str) -> None:
    state = request_state_var.get()
    if state is not None:
        state["user_id"] = user_id


class JsonFormatter(logging.Formatter):
    """Eine JSON-Zeile pro Logeintrag; Felder aus `extra={"fields": {...}}`
    werden eingemischt, Request-ID und Nutzer-ID kommen aus dem Kontext."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "ts": datetime.fromtimestamp(record.created, UTC).isoformat(timespec="milliseconds"),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }
        request_id = request_id_var.get()
        if request_id:
            payload["request_id"] = request_id
        extra = getattr(record, "fields", None)
        if isinstance(extra, dict):
            payload.update(extra)
        if record.exc_info:
            payload["exc"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False, default=str)


def configure_logging(level: str = "INFO", *, json_logs: bool = True) -> None:
    """Haengt den JSON-Formatter an den Root-Logger (einmalig, idempotent)."""
    root = logging.getLogger()
    root.setLevel(level.upper())
    if any(getattr(h, "_cc_crm_json", False) for h in root.handlers):
        return
    handler = logging.StreamHandler()
    handler.setFormatter(
        JsonFormatter()
        if json_logs
        else logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s")
    )
    handler._cc_crm_json = True  # type: ignore[attr-defined]
    root.addHandler(handler)


def _tail_for(real_path: str, template: str) -> str:
    """Der Teil des echten Pfads, der zur Routen-Vorlage gehoert (gleiche Zahl
    Pfadsegmente wie die Vorlage, von hinten)."""
    segments = [part for part in real_path.split("/") if part]
    count = len([part for part in template.split("/") if part])
    return "/" + "/".join(segments[len(segments) - count :]) if count else ""


class RequestLoggingMiddleware:
    """Reine ASGI-Middleware (kein BaseHTTPMiddleware): setzt/uebernimmt die
    Request-ID, schreibt eine Logzeile mit Methode, Pfad, Status, Dauer und
    Nutzer-ID und meldet langsame Requests als Warnung."""

    def __init__(self, app: ASGIApp, *, slow_seconds: float = SLOW_REQUEST_SECONDS) -> None:
        self.app = app
        self.slow_seconds = slow_seconds

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        incoming = ""
        for name, value in scope.get("headers", []):
            if name == b"x-request-id":
                incoming = value.decode("latin-1")
                break
        request_id = incoming if _SAFE_REQUEST_ID.match(incoming) else uuid.uuid4().hex
        request_token = request_id_var.set(request_id)
        state: dict[str, str | None] = {"user_id": None}
        state_token = request_state_var.set(state)
        started = time.perf_counter()
        status_code = 500

        async def send_with_id(message: Message) -> None:
            nonlocal status_code
            if message["type"] == "http.response.start":
                status_code = message["status"]
                headers = list(message.get("headers", []))
                headers.append((REQUEST_ID_HEADER.lower().encode(), request_id.encode()))
                message["headers"] = headers
            await send(message)

        try:
            await self.app(scope, receive, send_with_id)
        finally:
            duration = time.perf_counter() - started
            route = scope.get("route")
            template = getattr(route, "path", None)
            real_path = scope.get("path") or ""
            if template:
                # Die Route kennt den Prefix nicht (include_router(prefix=...)):
                # aus dem echten Pfad vorne wieder ergaenzen.
                prefix = real_path[: len(real_path) - len(_tail_for(real_path, template))]
                template = f"{prefix}{template}"
            fields = {
                "method": scope.get("method"),
                # Routen-Vorlage statt echtem Pfad (keine IDs/Tokens in den Logs).
                "path": template or real_path,
                "status": status_code,
                "duration_ms": round(duration * 1000, 1),
                "user_id": state["user_id"],
            }
            slow = duration >= self.slow_seconds
            logger.log(
                logging.WARNING if slow else logging.INFO,
                "slow_request" if slow else "request",
                extra={"fields": fields},
            )
            request_id_var.reset(request_token)
            request_state_var.reset(state_token)


def install_slow_sql_logging(
    engine: Engine, *, threshold_seconds: float = SLOW_SQL_SECONDS
) -> None:
    """Warnung mit gekuerztem Statement (OHNE Parameterwerte - die koennen
    Personendaten enthalten) bei Abfragen ueber `threshold_seconds`."""

    @event.listens_for(engine, "before_cursor_execute")
    def _before(conn, cursor, statement, parameters, context, executemany):  # type: ignore[no-untyped-def]
        conn.info["_query_start"] = time.perf_counter()

    @event.listens_for(engine, "after_cursor_execute")
    def _after(conn, cursor, statement, parameters, context, executemany):  # type: ignore[no-untyped-def]
        started = conn.info.pop("_query_start", None)
        if started is None:
            return
        elapsed = time.perf_counter() - started
        if elapsed >= threshold_seconds:
            sql_logger.warning(
                "slow_sql",
                extra={
                    "fields": {
                        "duration_ms": round(elapsed * 1000, 1),
                        "statement": " ".join(statement.split())[:300],
                    }
                },
            )


def init_sentry(dsn: str | None, *, environment: str, traces_sample_rate: float = 0.0) -> bool:
    """Aktiviert Sentry nur mit gesetzter DSN. Keine personenbezogenen Daten
    (send_default_pii=False); Request-Bodies werden nicht uebertragen."""
    if not dsn:
        return False
    import sentry_sdk

    sentry_sdk.init(
        dsn=dsn,
        environment=environment,
        send_default_pii=False,
        max_request_body_size="never",
        traces_sample_rate=traces_sample_rate,
    )
    return True
