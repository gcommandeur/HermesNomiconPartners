"""Job-Warteschlange: Abholen, Wiederholung, Zeitlimit, Fehlerstatus."""

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.orm import Session, sessionmaker

from cc_crm.core.errors import BusinessRuleError
from cc_crm.models.background_job import BackgroundJob
from cc_crm.services import job_queue
from cc_crm.services.job_queue import enqueue, process_one, register_handler, retry_job

calls: list[str] = []


@register_handler("test.ok")
def _ok(job: BackgroundJob) -> None:
    calls.append(job.payload["name"])


@register_handler("test.boom")
def _boom(job: BackgroundJob) -> None:
    raise RuntimeError("kaputt")


@pytest.fixture(autouse=True)
def _reset_calls() -> None:
    calls.clear()


def _reload(factory: sessionmaker[Session], job_id: object) -> BackgroundJob:
    with factory() as session:
        job = session.get(BackgroundJob, job_id)
        assert job is not None
        return job


def test_job_runs_once_and_is_done(session_factory: sessionmaker[Session]) -> None:
    with session_factory() as session:
        job = enqueue(session, "test.ok", {"name": "a"}, blob=b"daten")
        job_id = job.id
    assert process_one(session_factory) is True
    assert process_one(session_factory) is False
    assert calls == ["a"]
    done = _reload(session_factory, job_id)
    assert done.status == "done"
    assert done.attempts == 1
    assert done.payload_blob is None  # Bytes werden nach Abschluss geleert


def test_failing_job_is_retried_with_backoff_then_failed(
    session_factory: sessionmaker[Session],
) -> None:
    with session_factory() as session:
        job_id = enqueue(session, "test.boom", max_attempts=2).id
    assert process_one(session_factory) is True
    first = _reload(session_factory, job_id)
    assert first.status == "queued"
    assert first.attempts == 1
    assert "kaputt" in (first.last_error or "")
    # Wiederholung liegt in der Zukunft -> noch nichts abzuholen.
    assert process_one(session_factory) is False

    with session_factory() as session:
        session.get(BackgroundJob, job_id).run_after = datetime.now(UTC) - timedelta(seconds=1)  # type: ignore[union-attr]
        session.commit()
    assert process_one(session_factory) is True
    last = _reload(session_factory, job_id)
    assert last.status == "failed"
    assert last.attempts == 2
    assert last.finished_at is not None


def test_job_with_future_run_after_waits(session_factory: sessionmaker[Session]) -> None:
    with session_factory() as session:
        enqueue(session, "test.ok", {"name": "later"}, delay=timedelta(hours=1))
    assert process_one(session_factory) is False
    assert calls == []


def test_unknown_kind_ends_failed(session_factory: sessionmaker[Session]) -> None:
    with session_factory() as session:
        job_id = enqueue(session, "gibt.es.nicht", max_attempts=1).id
    assert process_one(session_factory) is True
    job = _reload(session_factory, job_id)
    assert job.status == "failed"
    assert "Unbekannte" in (job.last_error or "")


def test_crashed_worker_job_is_picked_up_again(session_factory: sessionmaker[Session]) -> None:
    with session_factory() as session:
        job_id = enqueue(session, "test.ok", {"name": "x"}, max_attempts=3).id
        job = session.get(BackgroundJob, job_id)
        assert job is not None
        job.status = "running"
        job.attempts = 1
        job.locked_until = datetime.now(UTC) - timedelta(minutes=1)  # Sperre abgelaufen
        session.commit()
    assert process_one(session_factory) is True
    assert calls == ["x"]
    assert _reload(session_factory, job_id).status == "done"


def test_running_job_with_valid_lock_is_not_taken(session_factory: sessionmaker[Session]) -> None:
    with session_factory() as session:
        job_id = enqueue(session, "test.ok", {"name": "x"}).id
        job = session.get(BackgroundJob, job_id)
        assert job is not None
        job.status = "running"
        job.locked_until = datetime.now(UTC) + timedelta(minutes=5)
        session.commit()
    assert process_one(session_factory) is False


def test_crash_in_last_attempt_ends_failed_without_running(
    session_factory: sessionmaker[Session],
) -> None:
    with session_factory() as session:
        job_id = enqueue(session, "test.ok", {"name": "x"}, max_attempts=1).id
        job = session.get(BackgroundJob, job_id)
        assert job is not None
        job.status = "running"
        job.attempts = 1
        job.locked_until = datetime.now(UTC) - timedelta(minutes=1)
        session.commit()
    assert process_one(session_factory) is False
    assert calls == []
    assert _reload(session_factory, job_id).status == "failed"


def test_retry_only_for_failed_jobs(session_factory: sessionmaker[Session]) -> None:
    with session_factory() as session:
        job_id = enqueue(session, "test.boom", max_attempts=1).id
        with pytest.raises(BusinessRuleError):
            retry_job(session, job_id)
    process_one(session_factory)
    with session_factory() as session:
        job = retry_job(session, job_id)
        assert job.status == job_queue.QUEUED
        assert job.attempts == 0
        assert job.last_error is None


# --- DSGVO: Lebenslauf-Bytes nicht in fehlgeschlagenen/verwaisten Jobs liegen lassen ---------


def test_final_failure_drops_blob_and_filename(session_factory: sessionmaker[Session]) -> None:
    with session_factory() as session:
        job_id = enqueue(
            session,
            "test.boom",
            {"filename": "lebenslauf-erika-musterfrau.pdf", "job_id": "x"},
            blob=b"%PDF geheim",
            max_attempts=2,
        ).id
    process_one(session_factory)
    # Solange eine Wiederholung ansteht, bleibt der Lebenslauf fuer den naechsten Versuch.
    retrying = _reload(session_factory, job_id)
    assert retrying.status == "queued"
    assert retrying.payload_blob == b"%PDF geheim"
    with session_factory() as session:
        session.get(BackgroundJob, job_id).run_after = datetime.now(UTC) - timedelta(seconds=1)  # type: ignore[union-attr]
        session.commit()
    process_one(session_factory)
    failed = _reload(session_factory, job_id)
    assert failed.status == "failed"
    assert failed.payload_blob is None
    assert failed.payload["filename"] == "[entfernt]"
    assert failed.payload["job_id"] == "x"  # technische Parameter bleiben


def test_worker_crash_in_last_attempt_drops_blob(session_factory: sessionmaker[Session]) -> None:
    with session_factory() as session:
        job_id = enqueue(
            session, "test.ok", {"filename": "cv-max.pdf"}, blob=b"%PDF", max_attempts=1
        ).id
        job = session.get(BackgroundJob, job_id)
        assert job is not None
        job.status = "running"
        job.attempts = 1
        job.locked_until = datetime.now(UTC) - timedelta(minutes=1)
        session.commit()
    process_one(session_factory)
    job = _reload(session_factory, job_id)
    assert job.status == "failed"
    assert job.payload_blob is None
    assert job.payload["filename"] == "[entfernt]"


def _aged_job(
    factory: sessionmaker[Session], *, status: str, days: int, kind: str = "test.ok"
) -> object:
    with factory() as session:
        job = enqueue(session, kind, {"filename": "cv.pdf"}, blob=b"%PDF geheim")
        job.status = status
        old = datetime.now(UTC) - timedelta(days=days)
        job.run_after = old
        job.locked_until = old if status == "running" else None
        session.commit()
        job_id = job.id
        # updated_at laesst sich ueber ORM-onupdate nicht zurueckdatieren -> direkt setzen
        session.execute(
            BackgroundJob.__table__.update()
            .where(BackgroundJob.id == job_id)
            .values(updated_at=old)
            .execution_options(synchronize_session=False)
        )
        session.commit()
        return job_id


def test_purge_removes_blobs_of_old_failed_and_orphaned_jobs(
    session_factory: sessionmaker[Session],
) -> None:
    old_failed = _aged_job(session_factory, status="failed", days=10)
    old_running = _aged_job(session_factory, status="running", days=10)
    old_queued = _aged_job(session_factory, status="queued", days=10)
    fresh_failed = _aged_job(session_factory, status="failed", days=1)
    fresh_queued = _aged_job(session_factory, status="queued", days=0)

    with session_factory() as session:
        assert job_queue.purge_stale_job_blobs(session, older_than_days=3, dry_run=True) == 3
    assert _reload(session_factory, old_failed).payload_blob is not None  # Probelauf aendert nichts

    with session_factory() as session:
        assert job_queue.purge_stale_job_blobs(session, older_than_days=3) == 3

    for job_id in (old_failed, old_running, old_queued):
        job = _reload(session_factory, job_id)
        assert job.payload_blob is None
        assert job.payload["filename"] == "[entfernt]"
        assert job.status == "failed"
    assert "verwaist" in (_reload(session_factory, old_running).last_error or "")
    # Frisches bleibt unberuehrt (wird noch gebraucht bzw. ist gerade erst fehlgeschlagen).
    assert _reload(session_factory, fresh_failed).payload_blob is not None
    assert _reload(session_factory, fresh_queued).payload_blob is not None
    assert _reload(session_factory, fresh_queued).status == "queued"

    with session_factory() as session:
        assert job_queue.purge_stale_job_blobs(session, older_than_days=3) == 0  # idempotent


def test_retry_of_scan_job_without_cv_is_refused(session_factory: sessionmaker[Session]) -> None:
    with session_factory() as session:
        job = enqueue(session, "cv.scan", {"filename": "x.pdf"}, blob=None, max_attempts=1)
        job.status = job_queue.FAILED
        session.commit()
        with pytest.raises(BusinessRuleError, match="erneut hochladen"):
            retry_job(session, job.id)
