from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from cc_crm.models.candidate import Candidate
from cc_crm.models.client_company import ClientCompany
from cc_crm.models.enums import TaskStatus
from cc_crm.models.recruiting import AuditLog
from cc_crm.models.submission import CandidateSubmission
from cc_crm.models.task import Task
from cc_crm.services.submissions import AUTO_FOLLOW_UP_DESCRIPTION
from scripts import cleanup_stale_followup_tasks as cleanup_script


def _use_session_factory(
    monkeypatch: pytest.MonkeyPatch, session_factory: sessionmaker[Session]
) -> None:
    monkeypatch.setattr(cleanup_script, "SessionLocal", session_factory)


def _make_submission(session: Session) -> CandidateSubmission:
    candidate = Candidate(first_name="Erkut", last_name="Dayan")
    client = ClientCompany(name="ZAHLENWERK STEUERBERATUNGSGESELLSCHAFT mbH")
    session.add_all([candidate, client])
    session.flush()
    submission = CandidateSubmission(
        candidate_id=candidate.id, client_company_id=client.id, status="CV_OUT"
    )
    session.add(submission)
    session.commit()
    return submission


def _make_auto_task(
    session: Session,
    submission: CandidateSubmission,
    *,
    title: str,
    created_at: datetime,
    status: TaskStatus = TaskStatus.OPEN,
    description: str = AUTO_FOLLOW_UP_DESCRIPTION,
) -> Task:
    task = Task(
        candidate_id=submission.candidate_id,
        client_company_id=submission.client_company_id,
        candidate_submission_id=submission.id,
        title=title,
        description=description,
        due_at=created_at + timedelta(days=1),
        status=status,
    )
    session.add(task)
    session.commit()
    task.created_at = created_at
    session.commit()
    return task


def _status(session: Session, task_id: object) -> TaskStatus:
    task = session.get(Task, task_id)
    assert task is not None
    return task.status


def test_dry_run_reports_duplicates_without_writing(
    monkeypatch: pytest.MonkeyPatch, session_factory: sessionmaker[Session]
) -> None:
    _use_session_factory(monkeypatch, session_factory)
    now = datetime.now(UTC)
    with session_factory() as session:
        submission = _make_submission(session)
        older = _make_auto_task(
            session, submission, title="CV-Out nachfassen", created_at=now - timedelta(days=2)
        )
        newer = _make_auto_task(
            session,
            submission,
            title="Interviewfeedback nachfassen",
            created_at=now - timedelta(days=1),
        )

    stats = cleanup_script.cleanup(apply=False)

    assert stats == {"submissions_checked": 1, "submissions_affected": 1, "tasks_closed": 1}
    with session_factory() as session:
        assert _status(session, older.id) == TaskStatus.OPEN
        assert _status(session, newer.id) == TaskStatus.OPEN


def test_apply_closes_all_but_newest_and_writes_audit_log(
    monkeypatch: pytest.MonkeyPatch, session_factory: sessionmaker[Session]
) -> None:
    _use_session_factory(monkeypatch, session_factory)
    now = datetime.now(UTC)
    with session_factory() as session:
        submission = _make_submission(session)
        older = _make_auto_task(
            session, submission, title="CV-Out nachfassen", created_at=now - timedelta(days=2)
        )
        newer = _make_auto_task(
            session,
            submission,
            title="Interviewfeedback nachfassen",
            created_at=now - timedelta(days=1),
        )

    stats = cleanup_script.cleanup(apply=True)

    assert stats == {"submissions_checked": 1, "submissions_affected": 1, "tasks_closed": 1}
    with session_factory() as session:
        refreshed_older = session.get(Task, older.id)
        assert refreshed_older is not None
        assert refreshed_older.status == TaskStatus.DONE
        assert "Bereinigungs-Skript" in (refreshed_older.description or "")

        refreshed_newer = session.get(Task, newer.id)
        assert refreshed_newer is not None
        assert refreshed_newer.status == TaskStatus.OPEN

        logs = session.scalars(
            select(AuditLog).where(
                AuditLog.entity_type == "task",
                AuditLog.action == "stale_followup_cleanup_closed",
            )
        ).all()
        assert len(logs) == 1
        assert logs[0].entity_id == older.id


def test_manually_created_task_with_different_description_is_left_alone(
    monkeypatch: pytest.MonkeyPatch, session_factory: sessionmaker[Session]
) -> None:
    _use_session_factory(monkeypatch, session_factory)
    now = datetime.now(UTC)
    with session_factory() as session:
        submission = _make_submission(session)
        _make_auto_task(
            session, submission, title="CV-Out nachfassen", created_at=now - timedelta(days=2)
        )
        manual = _make_auto_task(
            session,
            submission,
            title="CV-Out nachfassen",
            created_at=now - timedelta(days=1),
            description="Von Hand angelegt: bitte nochmal anrufen",
        )

    stats = cleanup_script.cleanup(apply=True)

    # Nur 1 Submission hat >1 offenen AUTOMATISCHEN Follow-up (der manuelle
    # zaehlt fuer die Duplikat-Erkennung nicht mit) - hier gibt es nur einen
    # einzigen automatischen Task, also kein Duplikat und nichts zu schliessen.
    assert stats == {"submissions_checked": 1, "submissions_affected": 0, "tasks_closed": 0}
    with session_factory() as session:
        assert _status(session, manual.id) == TaskStatus.OPEN


def test_no_duplicates_when_only_one_open_auto_follow_up(
    monkeypatch: pytest.MonkeyPatch, session_factory: sessionmaker[Session]
) -> None:
    _use_session_factory(monkeypatch, session_factory)
    now = datetime.now(UTC)
    with session_factory() as session:
        submission = _make_submission(session)
        _make_auto_task(session, submission, title="CV-Out nachfassen", created_at=now)

    stats = cleanup_script.cleanup(apply=True)

    assert stats == {"submissions_checked": 1, "submissions_affected": 0, "tasks_closed": 0}


def test_done_or_cancelled_auto_tasks_are_not_counted_as_open_duplicates(
    monkeypatch: pytest.MonkeyPatch, session_factory: sessionmaker[Session]
) -> None:
    _use_session_factory(monkeypatch, session_factory)
    now = datetime.now(UTC)
    with session_factory() as session:
        submission = _make_submission(session)
        _make_auto_task(
            session,
            submission,
            title="CV-Out nachfassen",
            created_at=now - timedelta(days=2),
            status=TaskStatus.DONE,
        )
        still_open = _make_auto_task(
            session,
            submission,
            title="Interviewfeedback nachfassen",
            created_at=now - timedelta(days=1),
        )

    stats = cleanup_script.cleanup(apply=True)

    assert stats == {"submissions_checked": 1, "submissions_affected": 0, "tasks_closed": 0}
    with session_factory() as session:
        assert _status(session, still_open.id) == TaskStatus.OPEN


def test_multiple_stale_duplicates_all_closed_except_newest(
    monkeypatch: pytest.MonkeyPatch, session_factory: sessionmaker[Session]
) -> None:
    _use_session_factory(monkeypatch, session_factory)
    now = datetime.now(UTC)
    with session_factory() as session:
        submission = _make_submission(session)
        first = _make_auto_task(
            session, submission, title="CV-Out nachfassen", created_at=now - timedelta(days=3)
        )
        second = _make_auto_task(
            session,
            submission,
            title="Interviewfeedback nachfassen",
            created_at=now - timedelta(days=2),
        )
        third = _make_auto_task(
            session, submission, title="Offer nachfassen", created_at=now - timedelta(days=1)
        )
        fourth = _make_auto_task(
            session,
            submission,
            title="Placement und Rechnung nachverfolgen",
            created_at=now,
        )

    stats = cleanup_script.cleanup(apply=True)

    assert stats == {"submissions_checked": 1, "submissions_affected": 1, "tasks_closed": 3}
    with session_factory() as session:
        for task_id in (first.id, second.id, third.id):
            assert _status(session, task_id) == TaskStatus.DONE
        assert _status(session, fourth.id) == TaskStatus.OPEN
