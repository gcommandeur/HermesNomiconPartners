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
