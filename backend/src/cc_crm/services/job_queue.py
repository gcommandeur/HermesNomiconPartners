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
# Nach so vielen Tagen werden Datei-Inhalte (Lebenslaeufe) endgueltig fehlgeschlagener oder
# verwaister Jobs vom Aufraeumschritt `purge_stale_job_blobs` geloescht.
STALE_BLOB_DAYS = 3
REMOVED = "[entfernt]"

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
        _drop_personal_data(job)
        session.commit()
        return claim_next(session)
    job.status = RUNNING
    job.attempts += 1
    job.locked_until = now + LOCK_BY_KIND.get(job.kind, DEFAULT_LOCK)
    session.commit()
    return job


def _drop_personal_data(job: BackgroundJob) -> None:
    """Loescht die mitgegebenen Bytes (z. B. den Lebenslauf) und einen darin steckenden
    Dateinamen, der den Namen der Person enthalten kann. Fuer Jobs, die nicht mehr laufen
    werden (fertig oder endgueltig fehlgeschlagen)."""
    job.payload_blob = None
    if "filename" in job.payload:
        job.payload = {**job.payload, "filename": REMOVED}


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
            # Endgueltig fehlgeschlagen: der Lebenslauf darf nicht liegen bleiben (DSGVO).
            _drop_personal_data(job)
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
    if job.kind == "cv.scan" and not job.payload_blob:
        raise BusinessRuleError(
            "Der Lebenslauf dieses Jobs wurde aus Datenschutzgruenden geloescht. "
            "Bitte den Lebenslauf erneut hochladen."
        )
    job.status = QUEUED
    job.attempts = 0
    job.run_after = _now()
    job.finished_at = None
    job.last_error = None
    session.commit()
    return job


def purge_stale_job_blobs(
    session: Session, *, older_than_days: int = STALE_BLOB_DAYS, dry_run: bool = False
) -> int:
    """Aufraeumschritt (DSGVO): loescht die Bytes (Lebenslaeufe) und Dateinamen von Jobs, die
    nicht mehr laufen werden und seit mehr als `older_than_days` Tagen liegen:

    - fehlgeschlagene Jobs (Altbestand von vor der Sofort-Loeschung),
    - verwaiste Jobs: "running" mit abgelaufener Sperre oder "queued" ohne dass je ein Worker
      sie abgeholt hat. Diese werden zusaetzlich auf "failed" gesetzt, damit sie nicht
      spaeter mit leeren Bytes laufen,
    - erledigte Jobs, in denen aus irgendeinem Grund noch Bytes stehen.

    Gibt die Zahl der bereinigten Jobs zurueck (bei `dry_run` nur gezaehlt,
    nichts geaendert). Wird NICHT automatisch gestartet; Aufruf ueber
    scripts/purge_job_blobs.py (standardmaessig Probelauf)."""
    now = _now()
    cutoff = now - timedelta(days=older_than_days)
    stale = or_(
        (BackgroundJob.status == FAILED) & (BackgroundJob.updated_at < cutoff),
        (BackgroundJob.status == DONE) & (BackgroundJob.updated_at < cutoff),
        (BackgroundJob.status == RUNNING) & (BackgroundJob.locked_until < cutoff),
        (BackgroundJob.status == QUEUED) & (BackgroundJob.run_after < cutoff),
    )
    jobs = session.scalars(
        select(BackgroundJob).where(BackgroundJob.payload_blob.is_not(None)).where(stale)
    ).all()
    if dry_run:
        return len(jobs)
    for job in jobs:
        if job.status in (RUNNING, QUEUED):
            job.status = FAILED
            job.last_error = "Job verwaist: Lebenslauf aus Datenschutzgruenden geloescht."
            job.finished_at = now
            job.locked_until = None
        _drop_personal_data(job)
    session.commit()
    return len(jobs)
