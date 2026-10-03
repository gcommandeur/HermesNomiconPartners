"""Job-Warteschlange in der Datenbank (Tabelle background_jobs).

Ein Job wird mit `enqueue` angelegt und von einem Worker abgearbeitet
(`process_one` / `run_worker_loop`). Abholen per `FOR UPDATE SKIP LOCKED`
(unter SQLite ohne Wirkung - dort laeuft nur ein Prozess), Wiederholung mit
wachsendem Abstand, nach `max_attempts` Versuchen Status "failed". Ein
abgestuerzter Worker gibt den Job frei, sobald `locked_until` abgelaufen ist.

Die Handler stehen in services/job_handlers.py und werden per Art
(`kind`) aufgeloest. Ein Handler bekommt den Job und oeffnet bei Bedarf
selbst eine Session.
"""

from __future__ import annotations

import logging
import threading
import uuid
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import or_, select
from sqlalchemy.orm import Session, sessionmaker

from cc_crm.core.errors import BusinessRuleError, EntityNotFoundError
from cc_crm.models.background_job import BackgroundJob

logger = logging.getLogger("cc_crm.job_queue")

QUEUED = "queued"
RUNNING = "running"
DONE = "done"
FAILED = "failed"

DEFAULT_LOCK = timedelta(minutes=10)
# Lange Jobs duerfen laenger "gesperrt" bleiben (ganze Sourcing-Laeufe).
LOCK_BY_KIND: dict[str, timedelta] = {
    "sourcing.team_pages": timedelta(hours=6),
    "sourcing.areas": timedelta(hours=6),
}
BACKOFF_BASE = timedelta(seconds=30)
MAX_ERROR_LENGTH = 2000

JobHandler = Callable[[BackgroundJob], None]
_HANDLERS: dict[str, JobHandler] = {}


def register_handler(kind: str) -> Callable[[JobHandler], JobHandler]:
    def decorator(handler: JobHandler) -> JobHandler:
        _HANDLERS[kind] = handler
        return handler

    return decorator


def _now() -> datetime:
    return datetime.now(UTC)


def enqueue(
    session: Session,
    kind: str,
    payload: dict[str, Any] | None = None,
    *,
    blob: bytes | None = None,
    max_attempts: int = 3,
    delay: timedelta | None = None,
    commit: bool = True,
) -> BackgroundJob:
    job = BackgroundJob(
        kind=kind,
        payload=payload or {},
        payload_blob=blob,
        status=QUEUED,
        attempts=0,
        max_attempts=max_attempts,
        run_after=_now() + (delay or timedelta(0)),
    )
    session.add(job)
    if commit:
        session.commit()
        session.refresh(job)
    else:
        session.flush()
    return job


def claim_next(session: Session) -> BackgroundJob | None:
    """Holt den naechsten faelligen Job und markiert ihn als laufend."""
    now = _now()
    statement = (
        select(BackgroundJob)
        .where(
            or_(
                (BackgroundJob.status == QUEUED) & (BackgroundJob.run_after <= now),
                (BackgroundJob.status == RUNNING) & (BackgroundJob.locked_until < now),
            )
        )
        .order_by(BackgroundJob.run_after)
        .limit(1)
        .with_for_update(skip_locked=True)
    )
    job = session.scalar(statement)
    if job is None:
        session.rollback()
        return None
    if job.status == RUNNING and job.attempts >= job.max_attempts:
        # Worker ist waehrend des letzten erlaubten Versuchs abgestuerzt.
        job.status = FAILED
        job.last_error = "Worker abgestuerzt oder Zeitlimit ueberschritten."
        job.finished_at = now
        job.locked_until = None
        session.commit()
        return claim_next(session)
    job.status = RUNNING
    job.attempts += 1
    job.locked_until = now + LOCK_BY_KIND.get(job.kind, DEFAULT_LOCK)
    session.commit()
    return job


def _finish(session: Session, job_id: uuid.UUID, error: str | None) -> None:
    job = session.get(BackgroundJob, job_id)
    if job is None:
        return
    job.locked_until = None
    if error is None:
        job.status = DONE
        job.last_error = None
        job.finished_at = _now()
        job.payload_blob = None
    else:
        job.last_error = error[:MAX_ERROR_LENGTH]
        if job.attempts >= job.max_attempts:
            job.status = FAILED
            job.finished_at = _now()
        else:
            job.status = QUEUED
            job.run_after = _now() + BACKOFF_BASE * (4 ** (job.attempts - 1))
    session.commit()


def process_one(session_factory: sessionmaker[Session]) -> bool:
    """Arbeitet hoechstens einen Job ab. True, wenn einer gelaufen ist."""
    from cc_crm.services import job_handlers  # noqa: F401  (registriert die Handler)

    with session_factory() as session:
        job = claim_next(session)
        if job is None:
            return False
        job_id, kind = job.id, job.kind
        handler = _HANDLERS.get(kind)
        error: str | None = None
        if handler is None:
            error = f"Unbekannte Job-Art: {kind}"
        else:
            try:
                handler(job)
            except Exception as exc:  # noqa: BLE001 - jeder Fehler wird am Job vermerkt
                logger.exception("Job %s (%s) fehlgeschlagen", job_id, kind)
                error = f"{type(exc).__name__}: {exc}"
        session.rollback()
        _finish(session, job_id, error)
        return True


def run_worker_loop(
    session_factory: sessionmaker[Session],
    stop: threading.Event,
    *,
    poll_seconds: float = 2.0,
) -> None:
    while not stop.is_set():
        try:
            worked = process_one(session_factory)
            if not worked:
                # Neue Ereignisse (Outbox) an Webhooks verteilen, solange nichts anderes ansteht.
                from cc_crm.services.webhooks import dispatch_outbox

                worked = dispatch_outbox(session_factory) > 0
        except Exception:  # noqa: BLE001 - die Schleife darf nie sterben
            logger.exception("Worker-Durchlauf fehlgeschlagen")
            worked = False
        if not worked:
            stop.wait(poll_seconds)


def list_jobs(
    session: Session, *, status: str | None = None, limit: int = 100
) -> list[BackgroundJob]:
    statement = select(BackgroundJob).order_by(BackgroundJob.created_at.desc()).limit(limit)
    if status:
        statement = statement.where(BackgroundJob.status == status)
    return list(session.scalars(statement).all())


def retry_job(session: Session, job_id: uuid.UUID) -> BackgroundJob:
    job = session.get(BackgroundJob, job_id)
    if job is None:
        raise EntityNotFoundError("Job nicht gefunden")
    if job.status != FAILED:
        raise BusinessRuleError("Nur fehlgeschlagene Jobs koennen neu gestartet werden.")
    job.status = QUEUED
    job.attempts = 0
    job.run_after = _now()
    job.finished_at = None
    job.last_error = None
    session.commit()
    return job
