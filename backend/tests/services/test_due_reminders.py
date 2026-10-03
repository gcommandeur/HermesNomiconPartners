"""Tests fuer die taegliche Faelligkeits-Mail (services/due_reminders.py).

Feste Zeitpunkte statt datetime.now() (keine Zeitbomben): `NOW` ist
05.10.2026 07:00 Berlin (CEST). "Heute faellig" heisst deshalb bis einschliesslich
05.10.2026 23:59 Berlin = 21:59 UTC. Der Mailversand ist ueber `sender`
injiziert; ein Test nutzt zusaetzlich das echte send_mail() mit Fake-SMTP."""

from datetime import UTC, datetime, timedelta

from sqlalchemy.orm import Session, sessionmaker

from cc_crm.core.security import hash_password
from cc_crm.models.candidate import Candidate
from cc_crm.models.client_company import ClientCompany
from cc_crm.models.enums import SubmissionStatus, TaskStatus
from cc_crm.models.mail import MailAccount, MailMessage
from cc_crm.models.submission import CandidateSubmission
from cc_crm.models.task import Task
from cc_crm.models.user import User
from cc_crm.services.due_reminders import (
    build_digest,
    collect_due_items,
    end_of_today_utc,
    send_due_reminders,
)
from cc_crm.services.mail_send import MailSendError, send_mail
from tests.services.test_mail_send import (  # noqa: F401
    _encryption_key,
    _FakeTransport,
    _make_account,
)

NOW = datetime(2026, 10, 5, 5, 0, tzinfo=UTC)  # 07:00 Europe/Berlin
TODAY_MORNING = datetime(2026, 10, 5, 6, 0, tzinfo=UTC)
YESTERDAY = datetime(2026, 10, 4, 10, 0, tzinfo=UTC)
TOMORROW = datetime(2026, 10, 6, 10, 0, tzinfo=UTC)


def _user(session: Session, email: str, *, active: bool = True) -> User:
    user = User(
        email=email, hashed_password=hash_password("x"), is_active=active, display_name=email[:1]
    )
    session.add(user)
    session.commit()
    return user


def _task(session: Session, owner: User, title: str, **overrides: object) -> Task:
    values: dict[str, object] = {
        "title": title,
        "owner_user_id": owner.id,
        "due_at": TODAY_MORNING,
        "status": TaskStatus.OPEN,
    }
    values.update(overrides)
    task = Task(**values)
    session.add(task)
    session.commit()
    return task


def _candidate(session: Session, name: str = "Anna") -> Candidate:
    candidate = Candidate(first_name=name, last_name="Muster")
    session.add(candidate)
    session.commit()
    return candidate


def _submission(
    session: Session, owner: User, candidate: Candidate, **overrides: object
) -> CandidateSubmission:
    values: dict[str, object] = {
        "candidate_id": candidate.id,
        "owner_user_id": owner.id,
        "status": SubmissionStatus.CV_OUT,
        "follow_up_at": TODAY_MORNING,
    }
    values.update(overrides)
    submission = CandidateSubmission(**values)
    session.add(submission)
    session.commit()
    return submission


class _Recorder:
    def __init__(self, fail_for: str | None = None) -> None:
        self.calls: list[dict[str, object]] = []
        self._fail_for = fail_for

    def __call__(self, session: Session, **kwargs: object) -> None:
        if kwargs["to_address"] == self._fail_for:
            raise MailSendError("Transportfehler")
        self.calls.append(kwargs)


class TestCollectDueItems:
    def test_selects_due_and_overdue_tasks_and_submissions(
        self, session_factory: sessionmaker[Session]
    ) -> None:
        with session_factory() as session:
            user = _user(session, "a@example.com")
            other = _user(session, "b@example.com")
            company = ClientCompany(name="Kanzlei X")
            session.add(company)
            session.commit()
            _task(session, user, "heute")
            _task(session, user, "ueberfaellig", due_at=YESTERDAY)
            # Spaetabends (23:30 Berlin) zaehlt noch zu "heute"
            _task(session, user, "heute spaet", due_at=datetime(2026, 10, 5, 21, 30, tzinfo=UTC))
            # Snooze abgelaufen -> zaehlt
            _task(session, user, "snooze vorbei", snoozed_until=YESTERDAY)
            # NICHT: morgen, 00:30 Berlin morgen, gesnoozt, erledigt, ohne Frist, fremd
            _task(session, user, "morgen", due_at=TOMORROW)
            _task(
                session,
                user,
                "kurz nach Mitternacht",
                due_at=datetime(2026, 10, 5, 22, 30, tzinfo=UTC),
            )
            _task(session, user, "gesnoozt", snoozed_until=NOW + timedelta(days=3))
            _task(session, user, "erledigt", status=TaskStatus.DONE)
            _task(session, user, "storniert", status=TaskStatus.CANCELLED)
            _task(session, user, "ohne Frist", due_at=None)
            _task(session, other, "fremd")

            candidate = _candidate(session)
            session.refresh(company)
            _submission(session, user, candidate, client_company_id=company.id)
            _submission(session, user, _candidate(session, "Zukunft"), follow_up_at=TOMORROW)
            _submission(session, user, _candidate(session, "Ohne"), follow_up_at=None)
            _submission(
                session,
                user,
                _candidate(session, "Platziert"),
                status=SubmissionStatus.PLACEMENT,
                follow_up_at=YESTERDAY,
            )
            _submission(
                session,
                user,
                _candidate(session, "Storniert"),
                status=SubmissionStatus.CANCELLED,
                follow_up_at=YESTERDAY,
            )
            _submission(
                session,
                user,
                _candidate(session, "Archiviert"),
                follow_up_at=YESTERDAY,
                archived_at=YESTERDAY,
            )
            _submission(session, other, _candidate(session, "Fremd"))

            items = collect_due_items(session, user, now=NOW)

            assert sorted(t.title for t in items.tasks) == sorted(
                ["ueberfaellig", "snooze vorbei", "heute", "heute spaet"]
            )
            assert [s.label for s in items.submissions] == ["Anna Muster bei Kanzlei X"]

    def test_end_of_today_handles_winter_and_summer_time(self) -> None:
        summer = end_of_today_utc(datetime(2026, 7, 1, 6, 0, tzinfo=UTC))
        winter = end_of_today_utc(datetime(2026, 12, 1, 6, 0, tzinfo=UTC))
        assert summer == datetime(2026, 7, 1, 22, 0)  # 00:00 Berlin (UTC+2) am 02.07.
        assert winter == datetime(2026, 12, 1, 23, 0)  # 00:00 Berlin (UTC+1) am 02.12.

    def test_digest_text(self, session_factory: sessionmaker[Session]) -> None:
        with session_factory() as session:
            user = _user(session, "a@example.com")
            _task(session, user, "Anruf bei Kanzlei", due_at=YESTERDAY)
            _submission(session, user, _candidate(session))
            subject, body = build_digest(user, collect_due_items(session, user, now=NOW), now=NOW)
        assert subject == "Hermes: 2 Punkte heute faellig"
        assert "Anruf bei Kanzlei (ueberfaellig seit 04.10.2026)" in body
        assert "Anna Muster - Stufe cv_out (heute)" in body


class TestSendDueReminders:
    def test_user_with_nothing_due_gets_no_mail(
        self, session_factory: sessionmaker[Session]
    ) -> None:
        with session_factory() as session:
            _user(session, "leer@example.com")
            recorder = _Recorder()
            results = send_due_reminders(
                session, now=NOW, sender=recorder, resolve_account=lambda _u: object()  # type: ignore[arg-type,return-value]
            )
        assert recorder.calls == []
        assert [r.outcome for r in results] == ["nothing_due"]

    def test_each_user_gets_only_own_items_and_inactive_users_are_skipped(
        self, session_factory: sessionmaker[Session]
    ) -> None:
        with session_factory() as session:
            a = _user(session, "a@example.com")
            b = _user(session, "b@example.com")
            inactive = _user(session, "c@example.com", active=False)
            _task(session, a, "Aufgabe von A")
            _task(session, b, "Aufgabe von B")
            _task(session, inactive, "Aufgabe von C")
            recorder = _Recorder()
            send_due_reminders(
                session, now=NOW, sender=recorder, resolve_account=lambda _u: object()  # type: ignore[arg-type,return-value]
            )
        by_recipient = {str(c["to_address"]): str(c["body_text"]) for c in recorder.calls}
        assert set(by_recipient) == {"a@example.com", "b@example.com"}
        assert "Aufgabe von A" in by_recipient["a@example.com"]
        assert "Aufgabe von B" not in by_recipient["a@example.com"]
        assert "Aufgabe von B" in by_recipient["b@example.com"]
        assert "Aufgabe von A" not in by_recipient["b@example.com"]

    def test_failure_for_one_user_does_not_stop_the_others(
        self, session_factory: sessionmaker[Session]
    ) -> None:
        with session_factory() as session:
            a = _user(session, "a@example.com")
            b = _user(session, "b@example.com")
            c = _user(session, "c@example.com")
            for user in (a, b, c):
                _task(session, user, f"Task {user.email}")
            recorder = _Recorder(fail_for="a@example.com")
            results = send_due_reminders(
                session, now=NOW, sender=recorder, resolve_account=lambda _u: object()  # type: ignore[arg-type,return-value]
            )
        outcomes = {r.email: r.outcome for r in results}
        assert outcomes == {
            "a@example.com": "error",
            "b@example.com": "sent",
            "c@example.com": "sent",
        }
        assert {str(c["to_address"]) for c in recorder.calls} == {"b@example.com", "c@example.com"}

    def test_user_without_send_account_is_skipped_and_logged(
        self, session_factory: sessionmaker[Session]
    ) -> None:
        with session_factory() as session:
            a = _user(session, "a@example.com")
            b = _user(session, "b@example.com")
            _task(session, a, "A")
            _task(session, b, "B")
            account = _make_account(session)
            recorder = _Recorder()
            results = send_due_reminders(
                session,
                now=NOW,
                sender=recorder,
                resolve_account=lambda user: account if user.email == "b@example.com" else None,
            )
        outcomes = {r.email: r.outcome for r in results}
        assert outcomes == {"a@example.com": "no_account", "b@example.com": "sent"}

    def test_sender_account_prefers_personal_over_global_default(
        self, session_factory: sessionmaker[Session]
    ) -> None:
        with session_factory() as session:
            global_account = _make_account(
                session, address="global@example.com", default_for_cv_out=True
            )
            personal = _make_account(session, address="privat@example.com", username="privat")
            a = _user(session, "a@example.com")
            b = _user(session, "b@example.com")
            a.default_send_account_id = personal.id
            session.commit()
            _task(session, a, "A")
            _task(session, b, "B")
            recorder = _Recorder()
            send_due_reminders(session, now=NOW, sender=recorder)
        used = {str(c["to_address"]): c["account"].address for c in recorder.calls}  # type: ignore[attr-defined]
        assert used == {"a@example.com": personal.address, "b@example.com": global_account.address}

    def test_real_send_mail_with_fake_smtp(
        self, session_factory: sessionmaker[Session], _encryption_key: None  # noqa: F811
    ) -> None:
        with session_factory() as session:
            _make_account(session, default_for_cv_out=True)
            user = _user(session, "a@example.com")
            _task(session, user, "Echter Versand")
            transport = _FakeTransport()

            def sender(session: Session, **kwargs: object) -> MailMessage:
                return send_mail(
                    session,
                    smtp_sender=transport.smtp_sender,
                    imap_appender=transport.imap_appender,
                    **kwargs,  # type: ignore[arg-type]
                )

            results = send_due_reminders(session, now=NOW, sender=sender)
            account = session.query(MailAccount).one()
        assert [r.outcome for r in results] == ["sent"]
        assert transport.smtp_calls == [(account.address, "a@example.com")]
