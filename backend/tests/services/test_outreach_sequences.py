"""Tageslauf der Outreach-Sequenzen (services/outreach_sequences.py).

Feste Zeitpunkte (keine Zeitbomben): `DAY0` ist Montag 05.10.2026 07:00 Berlin.
Der Tageslauf wird fuer verschiedene simulierte Tage mit `now=DAY0 + n Tage`
aufgerufen. Mailversand ist ueber `sender` injiziert (kein echter SMTP)."""

from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from cc_crm.core.security import hash_password
from cc_crm.models.activity import Activity
from cc_crm.models.candidate import Candidate
from cc_crm.models.mail import MailAccount, MailMessage
from cc_crm.models.outreach import OutreachSequence, OutreachSequenceStep, SequenceEnrollment
from cc_crm.models.task import Task
from cc_crm.models.user import User
from cc_crm.services.mail_send import DailyLimitReachedError, send_mail
from cc_crm.services.outreach_sequences import render_template, run_due_steps
from tests.services.test_mail_send import (  # noqa: F401
    _encryption_key,
    _FakeTransport,
    _make_account,
)

DAY0 = datetime(2026, 10, 5, 5, 0, tzinfo=UTC)  # 07:00 Europe/Berlin (MESZ)


def day(offset: int) -> datetime:
    return DAY0 + timedelta(days=offset)


def _user(session: Session, email: str = "owner@example.com") -> User:
    user = User(email=email, hashed_password=hash_password("x"), display_name="Olga Owner")
    session.add(user)
    session.commit()
    return user


def _candidate(session: Session, **overrides: object) -> Candidate:
    values: dict[str, object] = {
        "first_name": "Anna",
        "last_name": "Muster",
        "email": "anna@example.com",
        "consent_received": True,
    }
    values.update(overrides)
    candidate = Candidate(**values)
    session.add(candidate)
    session.commit()
    return candidate


def _sequence(session: Session, steps: list[tuple[int, str, str, str | None]], **kw: object):
    sequence = OutreachSequence(name="Test-Sequenz", **kw)
    session.add(sequence)
    session.flush()
    for index, (offset, channel, subject, body) in enumerate(steps):
        session.add(
            OutreachSequenceStep(
                sequence_id=sequence.id,
                step_index=index,
                day_offset=offset,
                channel=channel,
                subject=subject,
                body_template=body,
            )
        )
    session.commit()
    return sequence


DEFAULT_STEPS = [
    (0, "email", "Hallo {first_name}", "Guten Tag {full_name}, viele Gruesse {sender_name}"),
    (3, "linkedin", "LinkedIn an {first_name} senden", "Textvorschlag fuer {last_name}"),
    (7, "email", "Nachfassen {first_name}", "Kurze Erinnerung"),
]


def _enroll(
    session: Session,
    sequence: OutreachSequence,
    candidate: Candidate,
    owner: User,
    started_at: datetime = DAY0,
) -> SequenceEnrollment:
    enrollment = SequenceEnrollment(
        sequence_id=sequence.id,
        candidate_id=candidate.id,
        owner_user_id=owner.id,
        started_at=started_at,
        status="active",
    )
    session.add(enrollment)
    session.commit()
    return enrollment


class _Sender:
    def __init__(self, fail_for: str | None = None, error: Exception | None = None) -> None:
        self.calls: list[dict[str, object]] = []
        self._fail_for = fail_for
        self._error = error or RuntimeError("Transportfehler")

    def __call__(self, session: Session, **kwargs: object) -> None:
        if kwargs["to_address"] == self._fail_for:
            raise self._error
        self.calls.append(kwargs)


def _account(session: Session) -> MailAccount:
    return _make_account(session, default_for_cv_out=True)


def _run(session: Session, sender: _Sender, offset: int):
    return run_due_steps(
        session,
        now=day(offset),
        sender=sender,
        resolve_account=lambda _u: object(),  # type: ignore[arg-type,return-value]
    )


def test_render_template_replaces_known_placeholders_only() -> None:
    candidate = Candidate(first_name="Anna", last_name="Muster")
    owner = User(email="o@example.com", hashed_password="x", display_name="Olga")
    text = render_template(
        "{first_name} {last_name} / {full_name} / {sender_name} / {foo}", candidate, owner
    )
    assert text == "Anna Muster / Anna Muster / Olga / {foo}"


class TestSchedule:
    def test_steps_run_exactly_when_due_and_never_twice(
        self, session_factory: sessionmaker[Session]
    ) -> None:
        with session_factory() as session:
            owner = _user(session)
            candidate = _candidate(session)
            enrollment = _enroll(session, _sequence(session, DEFAULT_STEPS), candidate, owner)
            sender = _Sender()

            outcomes = {}
            for offset in (0, 0, 1, 2, 3, 3, 4, 6, 7, 7, 8):
                result = _run(session, sender, offset)
                outcomes.setdefault(offset, []).append([r.outcome for r in result])

            assert outcomes[0] == [["executed_email"], ["not_due"]]  # 2. Lauf am selben Tag
            assert outcomes[1] == [["not_due"]]
            assert outcomes[2] == [["not_due"]]
            assert outcomes[3] == [["executed_task"], ["not_due"]]
            assert outcomes[4] == [["not_due"]]
            assert outcomes[6] == [["not_due"]]
            assert outcomes[7] == [["completed"], []]  # danach nicht mehr aktiv
            assert outcomes[8] == [[]]
            # genau zwei Mails (Tag 0 und Tag 7), ein Task (Tag 3)
            assert [c["subject"] for c in sender.calls] == ["Hallo Anna", "Nachfassen Anna"]
            tasks = session.scalars(select(Task)).all()
            assert [t.title for t in tasks] == ["LinkedIn an Anna senden"]
            session.refresh(enrollment)
            assert enrollment.status == "completed"
            assert enrollment.current_step_index == 3

    def test_catch_up_runs_at_most_one_step_per_day(
        self, session_factory: sessionmaker[Session]
    ) -> None:
        with session_factory() as session:
            owner = _user(session)
            candidate = _candidate(session)
            steps = [(0, "linkedin", "A", None), (1, "linkedin", "B", None)]
            enrollment = _enroll(
                session, _sequence(session, steps), candidate, owner, started_at=day(-10)
            )
            sender = _Sender()
            assert [r.outcome for r in _run(session, sender, 0)] == ["executed_task"]
            assert [r.outcome for r in _run(session, sender, 0)] == ["not_due"]
            assert [r.outcome for r in _run(session, sender, 1)] == ["completed"]
            session.refresh(enrollment)
            assert len(session.scalars(select(Task)).all()) == 2

    def test_email_step_is_merged_and_sent_as_owner(
        self, session_factory: sessionmaker[Session]
    ) -> None:
        with session_factory() as session:
            owner = _user(session)
            candidate = _candidate(session)
            _enroll(session, _sequence(session, DEFAULT_STEPS), candidate, owner)
            sender = _Sender()
            _run(session, sender, 0)
            call = sender.calls[0]
            assert call["to_address"] == "anna@example.com"
            assert call["subject"] == "Hallo Anna"
            assert call["body_text"] == "Guten Tag Anna Muster, viele Gruesse Olga Owner"
            assert call["candidate_id"] == candidate.id
            assert call["current_user"].id == owner.id  # type: ignore[attr-defined]

    def test_task_step_creates_task_for_owner_and_sends_nothing(
        self, session_factory: sessionmaker[Session]
    ) -> None:
        with session_factory() as session:
            owner = _user(session)
            candidate = _candidate(session)
            steps = [(0, "linkedin", "LinkedIn an {first_name}", "Text fuer {last_name}")]
            _enroll(session, _sequence(session, steps), candidate, owner)
            sender = _Sender()
            assert [r.outcome for r in _run(session, sender, 0)] == ["completed"]
            assert sender.calls == []
            task = session.scalars(select(Task)).one()
            assert task.owner_user_id == owner.id
            assert task.candidate_id == candidate.id
            assert task.title == "LinkedIn an Anna"
            assert task.description == "Text fuer Muster"

    def test_inactive_sequence_is_skipped(self, session_factory: sessionmaker[Session]) -> None:
        with session_factory() as session:
            owner = _user(session)
            candidate = _candidate(session)
            sequence = _sequence(session, DEFAULT_STEPS, is_active=False)
            _enroll(session, sequence, candidate, owner)
            sender = _Sender()
            assert [r.outcome for r in _run(session, sender, 0)] == ["skipped"]
            assert sender.calls == []


class TestReplyPause:
    def _setup(self, session: Session) -> tuple[Candidate, SequenceEnrollment]:
        owner = _user(session)
        candidate = _candidate(session)
        return candidate, _enroll(session, _sequence(session, DEFAULT_STEPS), candidate, owner)

    def test_incoming_reply_after_start_pauses_and_blocks_next_step(
        self, session_factory: sessionmaker[Session]
    ) -> None:
        with session_factory() as session:
            candidate, enrollment = self._setup(session)
            sender = _Sender()
            _run(session, sender, 0)  # Schritt 0 geht raus
            session.add(
                Activity(
                    candidate_id=candidate.id,
                    activity_type="email",
                    subject="Re: Hallo",
                    occurred_at=day(1),
                )
            )
            session.commit()
            assert [r.outcome for r in _run(session, sender, 3)] == ["paused_reply"]
            assert len(sender.calls) == 1
            assert session.scalars(select(Task)).all() == []
            session.refresh(enrollment)
            assert enrollment.status == "paused_reply"
            assert _run(session, sender, 4) == []  # pausiert = nicht mehr im Lauf

    def test_linkedin_reply_also_pauses(self, session_factory: sessionmaker[Session]) -> None:
        with session_factory() as session:
            candidate, _ = self._setup(session)
            session.add(
                Activity(
                    candidate_id=candidate.id,
                    activity_type="linkedin_message",
                    subject="Antwort",
                    occurred_at=day(0) + timedelta(hours=1),
                )
            )
            session.commit()
            sender = _Sender()
            assert [r.outcome for r in _run(session, sender, 0)] == ["paused_reply"]
            assert sender.calls == []

    def test_old_activity_outgoing_and_foreign_activity_do_not_pause(
        self, session_factory: sessionmaker[Session]
    ) -> None:
        with session_factory() as session:
            candidate, _ = self._setup(session)
            other = _candidate(session, first_name="Bea", email="bea@example.com")
            session.add_all(
                [
                    Activity(
                        candidate_id=candidate.id,
                        activity_type="email",
                        subject="alt",
                        occurred_at=day(-2),  # VOR dem Start
                    ),
                    Activity(
                        candidate_id=candidate.id,
                        activity_type="email_sent",  # ausgehend
                        subject="raus",
                        occurred_at=day(1),
                    ),
                    Activity(
                        candidate_id=candidate.id,
                        activity_type="note",
                        subject="Notiz",
                        occurred_at=day(1),
                    ),
                    Activity(
                        candidate_id=other.id,  # anderer Kandidat
                        activity_type="email",
                        subject="fremd",
                        occurred_at=day(1),
                    ),
                ]
            )
            session.commit()
            sender = _Sender()
            assert [r.outcome for r in _run(session, sender, 0)] == ["executed_email"]


class TestBlockedAndTransient:
    def test_missing_email_and_missing_consent_stop_with_task(
        self, session_factory: sessionmaker[Session]
    ) -> None:
        with session_factory() as session:
            owner = _user(session)
            sequence = _sequence(session, DEFAULT_STEPS)
            no_mail = _candidate(session, first_name="Ohne", email=None)
            no_consent = _candidate(
                session, first_name="Keine", email="k@example.com", consent_received=False
            )
            e1 = _enroll(session, sequence, no_mail, owner)
            e2 = _enroll(session, sequence, no_consent, owner)
            sender = _Sender()
            assert sorted(r.outcome for r in _run(session, sender, 0)) == ["stopped", "stopped"]
            assert sender.calls == []
            session.refresh(e1)
            session.refresh(e2)
            assert (e1.status, e1.stopped_reason) == ("stopped", "Keine E-Mail-Adresse")
            assert (e2.status, e2.stopped_reason) == ("stopped", "Keine Einwilligung erfasst")
            tasks = session.scalars(select(Task)).all()
            assert len(tasks) == 2
            assert all(t.owner_user_id == owner.id for t in tasks)

    def test_no_send_account_keeps_enrollment_active_and_retries(
        self, session_factory: sessionmaker[Session]
    ) -> None:
        with session_factory() as session:
            owner = _user(session)
            sequence = _sequence(session, DEFAULT_STEPS)
            enrollment = _enroll(session, sequence, _candidate(session), owner)
            sender = _Sender()
            results = run_due_steps(
                session, now=day(0), sender=sender, resolve_account=lambda _u: None
            )
            assert [r.outcome for r in results] == ["skipped"]
            session.refresh(enrollment)
            assert (enrollment.status, enrollment.current_step_index) == ("active", 0)
            assert [r.outcome for r in _run(session, sender, 1)] == ["executed_email"]

    def test_daily_limit_keeps_enrollment_active(
        self, session_factory: sessionmaker[Session]
    ) -> None:
        with session_factory() as session:
            owner = _user(session)
            sequence = _sequence(session, DEFAULT_STEPS)
            enrollment = _enroll(session, sequence, _candidate(session), owner)
            sender = _Sender(
                fail_for="anna@example.com", error=DailyLimitReachedError("Limit")
            )
            assert [r.outcome for r in _run(session, sender, 0)] == ["skipped"]
            session.refresh(enrollment)
            assert (enrollment.status, enrollment.current_step_index) == ("active", 0)

    def test_error_for_one_enrollment_does_not_stop_the_others(
        self, session_factory: sessionmaker[Session]
    ) -> None:
        with session_factory() as session:
            owner = _user(session)
            sequence = _sequence(session, DEFAULT_STEPS)
            bad = _candidate(session, first_name="Bad", email="bad@example.com")
            good = _candidate(session, first_name="Good", email="good@example.com")
            e_bad = _enroll(session, sequence, bad, owner, started_at=day(0) - timedelta(hours=2))
            e_good = _enroll(session, sequence, good, owner)
            sender = _Sender(fail_for="bad@example.com")
            outcomes = {r.enrollment_id: r.outcome for r in _run(session, sender, 0)}
            assert outcomes == {e_bad.id: "error", e_good.id: "executed_email"}
            session.refresh(e_bad)
            session.refresh(e_good)
            assert (e_bad.status, e_bad.current_step_index) == ("active", 0)  # Retry morgen
            assert e_good.current_step_index == 1
            assert [c["to_address"] for c in sender.calls] == ["good@example.com"]


def test_real_send_mail_does_not_trigger_the_reply_pause(
    session_factory: sessionmaker[Session], _encryption_key: None  # noqa: F811
) -> None:
    """Die eigene ausgehende Mail legt eine "email_sent"-Aktivitaet am Kandidaten
    an - sie darf die Sequenz nicht als "Antwort" pausieren."""
    with session_factory() as session:
        _account(session)
        owner = _user(session)
        candidate = _candidate(session)
        enrollment = _enroll(session, _sequence(session, DEFAULT_STEPS), candidate, owner)
        transport = _FakeTransport()

        def sender(session: Session, **kwargs: object) -> MailMessage:
            return send_mail(
                session,
                smtp_sender=transport.smtp_sender,
                imap_appender=transport.imap_appender,
                **kwargs,  # type: ignore[arg-type]
            )

        first = run_due_steps(session, now=day(0), sender=sender)
        assert [r.outcome for r in first] == ["executed_email"]
        assert len(transport.smtp_calls) == 1
        sent_activity = session.scalars(
            select(Activity).where(Activity.candidate_id == candidate.id)
        ).one()
        assert sent_activity.activity_type == "email_sent"
        second = run_due_steps(session, now=day(3), sender=sender)
        assert [r.outcome for r in second] == ["executed_task"]
        session.refresh(enrollment)
        assert enrollment.status == "active"
