"""Tests fuer den SMTP-Versand (services/mail_send.py).

Der SMTP-/IMAP-Zugriff ist ueber `smtp_sender`/`imap_appender` injiziert
(gleiches Muster wie der `fetcher`-Parameter in mail_sync.py) - kein Test
hier oeffnet eine echte Netzwerkverbindung. Das ist zugleich der geforderte
Testpfad, der nicht wirklich versendet."""

from datetime import UTC, datetime, timedelta

import pytest
from cryptography.fernet import Fernet
from sqlalchemy.orm import Session, sessionmaker

from cc_crm.core.errors import ConsentNotGrantedError
from cc_crm.models.candidate import Candidate
from cc_crm.models.enums import MailDirection, MailMatchStatus
from cc_crm.models.mail import MailAccount, MailMessage
from cc_crm.models.recruiting import AuditLog
from cc_crm.models.user import User
from cc_crm.services.mail_send import (
    ACTIVITY_TYPE_EMAIL_SENT,
    AUDIT_ACTION_CANDIDATE_PROFILE_SENT,
    AUDIT_ACTION_MAIL_SENT,
    BulkRecipient,
    DailyLimitReachedError,
    MailSendError,
    send_bulk,
    send_mail,
    sent_today_count,
)

_KEY = Fernet.generate_key().decode()


@pytest.fixture(autouse=True)
def _encryption_key(monkeypatch: pytest.MonkeyPatch) -> None:
    from cc_crm.core.config import get_settings

    get_settings.cache_clear()
    monkeypatch.setenv("CC_CRM_MAIL_CREDENTIALS_ENCRYPTION_KEY", _KEY)
    yield
    get_settings.cache_clear()


def _make_account(session: Session, **overrides: object) -> MailAccount:
    defaults: dict[str, object] = {
        "address": "lukas.bergmann@commandeurconsulting.de",
        "label": "Lukas Bergmann",
        "imap_host": "imap.example.com",
        "smtp_host": "smtp.example.com",
        "username": "lukas.bergmann@commandeurconsulting.de",
        "encrypted_password": Fernet(_KEY.encode()).encrypt(b"geheim").decode(),
    }
    defaults.update(overrides)
    account = MailAccount(**defaults)
    session.add(account)
    session.commit()
    session.refresh(account)
    return account


class _FakeTransport:
    """Zeichnet SMTP-/IMAP-Aufrufe auf, statt wirklich zu versenden."""

    def __init__(self, *, append_ok: bool = True, smtp_error: Exception | None = None) -> None:
        self.smtp_calls: list[tuple[str, str]] = []  # (from_address, to_address)
        self.append_calls = 0
        self._append_ok = append_ok
        self._smtp_error = smtp_error

    def smtp_sender(self, account: MailAccount, password: str, message, to_address: str) -> None:
        if self._smtp_error is not None:
            raise self._smtp_error
        assert password == "geheim"
        self.smtp_calls.append((account.address, to_address))

    def imap_appender(self, account: MailAccount, password: str, message) -> bool:
        self.append_calls += 1
        return self._append_ok


class TestSendMail:
    def test_sends_and_records_mail_message_and_activity(
        self, session_factory: sessionmaker[Session]
    ) -> None:
        with session_factory() as session:
            account = _make_account(session)
            candidate = Candidate(
                first_name="Anna", last_name="Muster", consent_received=True
            )
            session.add(candidate)
            session.commit()
            candidate_id = candidate.id

            transport = _FakeTransport()
            record = send_mail(
                session,
                account=account,
                to_address="kanzlei@example.com",
                to_name="Muster Kanzlei",
                subject="Kandidatenprofil Nr. 4456",
                body_text="Anbei das anonyme Profil.",
                candidate_id=candidate_id,
                smtp_sender=transport.smtp_sender,
                imap_appender=transport.imap_appender,
            )

            assert transport.smtp_calls == [(account.address, "kanzlei@example.com")]
            assert transport.append_calls == 1
            assert record.direction == MailDirection.OUTBOUND
            assert record.match_status == MailMatchStatus.MATCHED
            assert record.matched_candidate_id == candidate_id
            assert record.created_activity_id is not None

            stored = session.get(MailMessage, record.id)
            assert stored is not None
            assert stored.subject == "Kandidatenprofil Nr. 4456"

    def test_failed_append_to_sent_folder_does_not_fail_the_send(
        self, session_factory: sessionmaker[Session]
    ) -> None:
        """Best-effort: die Mail ist beim Empfaenger bereits angekommen -
        ein fehlgeschlagenes Sent-Ordner-APPEND darf den Versand nicht als
        gescheitert melden."""
        with session_factory() as session:
            account = _make_account(session)
            transport = _FakeTransport(append_ok=False)

            record = send_mail(
                session,
                account=account,
                to_address="kanzlei@example.com",
                subject="Test",
                body_text="Text",
                smtp_sender=transport.smtp_sender,
                imap_appender=transport.imap_appender,
            )

            assert record.id is not None

    def test_append_exception_does_not_fail_the_send(
        self, session_factory: sessionmaker[Session]
    ) -> None:
        with session_factory() as session:
            account = _make_account(session)
            transport = _FakeTransport()

            def _raising_appender(account, password, message):
                raise ConnectionError("IMAP nicht erreichbar")

            record = send_mail(
                session,
                account=account,
                to_address="kanzlei@example.com",
                subject="Test",
                body_text="Text",
                smtp_sender=transport.smtp_sender,
                imap_appender=_raising_appender,
            )

            assert record.id is not None

    def test_smtp_failure_raises_mail_send_error_and_persists_nothing(
        self, session_factory: sessionmaker[Session]
    ) -> None:
        with session_factory() as session:
            account = _make_account(session)
            transport = _FakeTransport(smtp_error=ConnectionRefusedError("Verbindung abgelehnt"))

            with pytest.raises(MailSendError):
                send_mail(
                    session,
                    account=account,
                    to_address="kanzlei@example.com",
                    subject="Test",
                    body_text="Text",
                    smtp_sender=transport.smtp_sender,
                    imap_appender=transport.imap_appender,
                )

            assert session.query(MailMessage).count() == 0

    def test_inactive_account_is_rejected_without_attempting_smtp(
        self, session_factory: sessionmaker[Session]
    ) -> None:
        with session_factory() as session:
            account = _make_account(session, is_active=False)
            transport = _FakeTransport()

            with pytest.raises(MailSendError, match="deaktiviert"):
                send_mail(
                    session,
                    account=account,
                    to_address="kanzlei@example.com",
                    subject="Test",
                    body_text="Text",
                    smtp_sender=transport.smtp_sender,
                    imap_appender=transport.imap_appender,
                )

            assert transport.smtp_calls == []

    def test_attachment_is_loaded_from_storage_and_sent(
        self, session_factory: sessionmaker[Session], tmp_path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from cc_crm.services.mail_send import MailAttachmentRef

        with session_factory() as session:
            account = _make_account(session)
            transport = _FakeTransport()

            captured_messages = []

            def _capturing_smtp_sender(account, password, message, to_address):
                captured_messages.append(message)
                transport.smtp_sender(account, password, message, to_address)

            monkeypatch.setattr(
                "cc_crm.services.mail_send.read_document_bytes",
                lambda storage_key: b"%PDF-fake-bytes",
            )

            send_mail(
                session,
                account=account,
                to_address="kanzlei@example.com",
                subject="Test",
                body_text="Text",
                attachments=[
                    MailAttachmentRef(
                        storage_key="candidate/x/Nr. 4456.docx",
                        filename="Nr. 4456.docx",
                        content_type=(
                            "application/vnd.openxmlformats-officedocument."
                            "wordprocessingml.document"
                        ),
                    )
                ],
                smtp_sender=_capturing_smtp_sender,
                imap_appender=transport.imap_appender,
            )

            assert len(captured_messages) == 1
            payload_filenames = [
                part.get_filename()
                for part in captured_messages[0].walk()
                if part.get_filename()
            ]
            assert "Nr. 4456.docx" in payload_filenames


class TestDailyLimit:
    def test_sent_today_count_only_counts_outbound_since_midnight(
        self, session_factory: sessionmaker[Session]
    ) -> None:
        with session_factory() as session:
            account = _make_account(session)
            session.add(
                MailMessage(
                    mail_account_id=account.id,
                    message_id="today@example.com",
                    direction=MailDirection.OUTBOUND,
                    received_at=datetime.now(UTC),
                    match_status=MailMatchStatus.MATCHED,
                )
            )
            session.add(
                MailMessage(
                    mail_account_id=account.id,
                    message_id="yesterday@example.com",
                    direction=MailDirection.OUTBOUND,
                    received_at=datetime.now(UTC) - timedelta(days=1),
                    match_status=MailMatchStatus.MATCHED,
                )
            )
            session.add(
                MailMessage(
                    mail_account_id=account.id,
                    message_id="inbound-today@example.com",
                    direction=MailDirection.INBOUND,
                    received_at=datetime.now(UTC),
                    match_status=MailMatchStatus.UNMATCHED,
                )
            )
            session.commit()

            assert sent_today_count(session, account.id) == 1

    def test_send_mail_rejects_once_daily_limit_reached(
        self, session_factory: sessionmaker[Session]
    ) -> None:
        with session_factory() as session:
            account = _make_account(session, daily_send_limit=1)
            transport = _FakeTransport()

            send_mail(
                session,
                account=account,
                to_address="a@example.com",
                subject="1",
                body_text="1",
                smtp_sender=transport.smtp_sender,
                imap_appender=transport.imap_appender,
            )

            with pytest.raises(DailyLimitReachedError):
                send_mail(
                    session,
                    account=account,
                    to_address="b@example.com",
                    subject="2",
                    body_text="2",
                    smtp_sender=transport.smtp_sender,
                    imap_appender=transport.imap_appender,
                )

            # Der zweite Versand wurde gar nicht erst versucht.
            assert transport.smtp_calls == [(account.address, "a@example.com")]


class TestSendBulk:
    def test_sleeps_between_sends_but_not_before_the_first(
        self, session_factory: sessionmaker[Session]
    ) -> None:
        with session_factory() as session:
            account = _make_account(session, send_throttle_seconds=7)
            transport = _FakeTransport()
            sleeps: list[float] = []

            result = send_bulk(
                session,
                account=account,
                recipients=[
                    BulkRecipient(to_address="a@example.com"),
                    BulkRecipient(to_address="b@example.com"),
                    BulkRecipient(to_address="c@example.com"),
                ],
                subject="Test",
                body_text="Text",
                sleep=sleeps.append,
                smtp_sender=transport.smtp_sender,
                imap_appender=transport.imap_appender,
            )

            assert sleeps == [7, 7]
            assert len(result.sent) == 3
            assert result.failed == []

    def test_single_recipient_failure_does_not_abort_the_run(
        self, session_factory: sessionmaker[Session]
    ) -> None:
        with session_factory() as session:
            account = _make_account(session)
            calls = {"n": 0}

            def _flaky_smtp_sender(account, password, message, to_address):
                calls["n"] += 1
                if to_address == "broken@example.com":
                    raise RuntimeError("Adresse ungueltig")

            result = send_bulk(
                session,
                account=account,
                recipients=[
                    BulkRecipient(to_address="broken@example.com"),
                    BulkRecipient(to_address="good@example.com"),
                ],
                subject="Test",
                body_text="Text",
                sleep=lambda _seconds: None,
                smtp_sender=_flaky_smtp_sender,
                imap_appender=lambda *a: True,
            )

            assert len(result.sent) == 1
            assert len(result.failed) == 1
            assert result.failed[0][0].to_address == "broken@example.com"

    def test_daily_limit_mid_run_skips_remaining_recipients(
        self, session_factory: sessionmaker[Session]
    ) -> None:
        with session_factory() as session:
            account = _make_account(session, daily_send_limit=2)
            transport = _FakeTransport()

            result = send_bulk(
                session,
                account=account,
                recipients=[
                    BulkRecipient(to_address="a@example.com"),
                    BulkRecipient(to_address="b@example.com"),
                    BulkRecipient(to_address="c@example.com"),
                    BulkRecipient(to_address="d@example.com"),
                ],
                subject="Test",
                body_text="Text",
                sleep=lambda _seconds: None,
                smtp_sender=transport.smtp_sender,
                imap_appender=transport.imap_appender,
            )

            assert len(result.sent) == 2
            assert [r.to_address for r in result.skipped_due_to_daily_limit] == [
                "c@example.com",
                "d@example.com",
            ]


def test_activity_created_with_correct_type_and_subject(
    session_factory: sessionmaker[Session],
) -> None:
    from cc_crm.models.activity import Activity

    with session_factory() as session:
        account = _make_account(session)
        candidate = Candidate(first_name="Anna", last_name="Muster", consent_received=True)
        session.add(candidate)
        session.commit()
        candidate_id = candidate.id
        transport = _FakeTransport()

        record = send_mail(
            session,
            account=account,
            to_address="kanzlei@example.com",
            subject="Kandidatenprofil Nr. 4456",
            body_text="Anbei das anonyme Profil.",
            candidate_id=candidate_id,
            smtp_sender=transport.smtp_sender,
            imap_appender=transport.imap_appender,
        )

        activity = session.get(Activity, record.created_activity_id)
        assert activity is not None
        assert activity.activity_type == ACTIVITY_TYPE_EMAIL_SENT
        assert activity.candidate_id == candidate_id
        assert activity.subject == "Kandidatenprofil Nr. 4456"


class TestConsentEnforcement:
    """Punkt 1 des Auftrags "5 Hoch-Punkte umsetzen": harter serverseitiger
    Block vor jedem Mail-Versand mit Kandidatenbezug, wenn
    candidate.consent_received nicht True ist - vorher wurde das Feld
    nirgends geprueft."""

    def test_send_mail_rejects_when_candidate_has_no_consent(
        self, session_factory: sessionmaker[Session]
    ) -> None:
        with session_factory() as session:
            account = _make_account(session)
            candidate = Candidate(
                first_name="Ohne", last_name="Einwilligung", consent_received=False
            )
            session.add(candidate)
            session.commit()
            candidate_id = candidate.id
            transport = _FakeTransport()

            with pytest.raises(ConsentNotGrantedError, match="Kein Einverständnis"):
                send_mail(
                    session,
                    account=account,
                    to_address="kanzlei@example.com",
                    subject="Test",
                    body_text="Text",
                    candidate_id=candidate_id,
                    smtp_sender=transport.smtp_sender,
                    imap_appender=transport.imap_appender,
                )

            # Kein Versand-Versuch, keine MailMessage - der Block greift, BEVOR
            # ueberhaupt SMTP kontaktiert wird.
            assert transport.smtp_calls == []
            assert session.query(MailMessage).count() == 0

    def test_send_mail_allows_send_without_candidate_id(
        self, session_factory: sessionmaker[Session]
    ) -> None:
        """Mails ohne Kandidatenbezug (z.B. reine Kanzlei-/Kontakt-Mail) sind
        von der Consent-Pruefung nicht betroffen."""
        with session_factory() as session:
            account = _make_account(session)
            transport = _FakeTransport()

            record = send_mail(
                session,
                account=account,
                to_address="kanzlei@example.com",
                subject="Test",
                body_text="Text",
                smtp_sender=transport.smtp_sender,
                imap_appender=transport.imap_appender,
            )
            assert record.id is not None

    def test_send_bulk_blocks_only_the_recipient_without_consent(
        self, session_factory: sessionmaker[Session]
    ) -> None:
        """Kernanforderung: EIN fehlendes Einverstaendnis in der Gruppe darf
        weder alle blocken noch alle durchlassen - nur der betroffene
        Empfaenger landet in `failed`, alle anderen werden trotzdem
        versendet."""
        with session_factory() as session:
            account = _make_account(session)
            consenting = Candidate(
                first_name="Mit", last_name="Einwilligung", consent_received=True
            )
            refusing = Candidate(
                first_name="Ohne", last_name="Einwilligung", consent_received=False
            )
            session.add_all([consenting, refusing])
            session.commit()
            transport = _FakeTransport()

            result = send_bulk(
                session,
                account=account,
                recipients=[
                    BulkRecipient(to_address="ok@example.com", candidate_id=consenting.id),
                    BulkRecipient(to_address="blocked@example.com", candidate_id=refusing.id),
                ],
                subject="Test",
                body_text="Text",
                sleep=lambda _seconds: None,
                smtp_sender=transport.smtp_sender,
                imap_appender=transport.imap_appender,
            )

            assert [m.matched_candidate_id for m in result.sent] == [consenting.id]
            assert len(result.failed) == 1
            failed_recipient, failed_message = result.failed[0]
            assert failed_recipient.to_address == "blocked@example.com"
            assert "Kein Einverständnis" in failed_message


class TestSendAuditTrail:
    """Punkt 2 des Auftrags "5 Hoch-Punkte umsetzen": Activity.sent_by_user_id
    + ein AuditLog-Eintrag pro erfolgreichem Versand ("wer hat wann welches
    Profil an wen geschickt")."""

    def test_activity_records_the_sending_user(
        self, session_factory: sessionmaker[Session]
    ) -> None:
        from cc_crm.models.activity import Activity

        with session_factory() as session:
            account = _make_account(session)
            user = User(email="lukas@commandeurconsulting.de", hashed_password="x")
            session.add(user)
            session.commit()
            transport = _FakeTransport()

            record = send_mail(
                session,
                account=account,
                to_address="kanzlei@example.com",
                subject="Test",
                body_text="Text",
                current_user=user,
                smtp_sender=transport.smtp_sender,
                imap_appender=transport.imap_appender,
            )

            activity = session.get(Activity, record.created_activity_id)
            assert activity is not None
            assert activity.sent_by_user_id == user.id

    def test_audit_log_written_for_candidate_profile_send(
        self, session_factory: sessionmaker[Session]
    ) -> None:
        with session_factory() as session:
            account = _make_account(session)
            user = User(email="lukas@commandeurconsulting.de", hashed_password="x")
            candidate = Candidate(
                first_name="Anna", last_name="Muster", consent_received=True
            )
            session.add_all([user, candidate])
            session.commit()
            transport = _FakeTransport()

            send_mail(
                session,
                account=account,
                to_address="kanzlei@example.com",
                subject="Kandidatenprofil Nr. 4456",
                body_text="Text",
                candidate_id=candidate.id,
                current_user=user,
                smtp_sender=transport.smtp_sender,
                imap_appender=transport.imap_appender,
            )

            entry = (
                session.query(AuditLog)
                .filter_by(entity_type="candidate", entity_id=candidate.id)
                .filter_by(action=AUDIT_ACTION_CANDIDATE_PROFILE_SENT)
                .one()
            )
            assert entry.changed_by == user.email
            assert entry.new_values is not None
            assert entry.new_values["candidate_id"] == str(candidate.id)
            assert entry.new_values["to_address"] == "kanzlei@example.com"

    def test_audit_log_written_without_candidate_uses_mail_message_entity(
        self, session_factory: sessionmaker[Session]
    ) -> None:
        with session_factory() as session:
            account = _make_account(session)
            transport = _FakeTransport()

            record = send_mail(
                session,
                account=account,
                to_address="kontakt@example.com",
                subject="Test",
                body_text="Text",
                smtp_sender=transport.smtp_sender,
                imap_appender=transport.imap_appender,
            )

            entry = (
                session.query(AuditLog)
                .filter_by(entity_type="mail_message", entity_id=record.id)
                .filter_by(action=AUDIT_ACTION_MAIL_SENT)
                .one()
            )
            assert entry.changed_by is None
