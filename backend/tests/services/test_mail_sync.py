"""Tests fuer den IMAP-Sync (services/mail_sync.py).

Der IMAP-Zugriff ist ueber den `fetcher`-Parameter injiziert - alle Tests
laufen daher ohne echten Mailserver gegen genau die Logik, in der die
Fehler stecken: Dedup, Selbst-Erkennung, Zuordnung und Fehlerbehandlung.
"""

from datetime import UTC, datetime

import pytest
from cryptography.fernet import Fernet
from sqlalchemy.orm import Session, sessionmaker

from cc_crm.models.activity import Activity
from cc_crm.models.candidate import Candidate
from cc_crm.models.client_company import ClientCompany
from cc_crm.models.contact_person import ContactPerson
from cc_crm.models.enums import MailDirection, MailMatchStatus
from cc_crm.models.mail import MailAccount, MailMessage
from cc_crm.services.mail_sync import (
    ACTIVITY_TYPE_EMAIL,
    ACTIVITY_TYPE_LINKEDIN,
    FetchedMail,
    MailSyncService,
    _max_uid,
)

_KEY = Fernet.generate_key().decode()


@pytest.fixture(autouse=True)
def _encryption_key(monkeypatch: pytest.MonkeyPatch) -> None:
    """mail_sync entschluesselt das Passwort nur in _safe_error - ohne
    gesetzten Schluessel wuerde das dort scheitern."""
    from cc_crm.core.config import get_settings

    get_settings.cache_clear()
    monkeypatch.setenv("CC_CRM_MAIL_CREDENTIALS_ENCRYPTION_KEY", _KEY)
    yield
    get_settings.cache_clear()


def _make_account(session: Session, **overrides: object) -> MailAccount:
    defaults: dict[str, object] = {
        "address": "info@commandeurconsulting.de",
        "label": "info-linkedin",
        "imap_host": "imap.example.com",
        "smtp_host": "smtp.example.com",
        "username": "info@commandeurconsulting.de",
        "encrypted_password": Fernet(_KEY.encode()).encrypt(b"geheim").decode(),
    }
    defaults.update(overrides)
    account = MailAccount(**defaults)
    session.add(account)
    session.commit()
    session.refresh(account)
    return account


def _mail(**overrides: object) -> FetchedMail:
    defaults: dict[str, object] = {
        "message_id": "msg-1@example.com",
        "uid": "1",
        "from_name": "Anna Müller",
        "from_address": "anna.mueller@example.com",
        "subject": "Rückfrage",
        "body_text": "Hallo, hätten Sie Zeit für ein Gespräch?",
        "received_at": datetime(2026, 8, 1, 10, 0, tzinfo=UTC),
    }
    defaults.update(overrides)
    return FetchedMail(**defaults)  # type: ignore[arg-type]


def _sync(session: Session, account: MailAccount, mails: list[FetchedMail]):
    service = MailSyncService(session, fetcher=lambda _account, _uid: mails)
    return service.sync_account(account)


class TestLinkedInMatching:
    def test_matched_candidate_gets_linkedin_activity(
        self, session_factory: sessionmaker[Session]
    ) -> None:
        with session_factory() as session:
            account = _make_account(session)
            candidate = Candidate(first_name="John Paul", last_name="Fürus")
            session.add(candidate)
            session.commit()
            candidate_id = candidate.id

            result = _sync(
                session,
                account,
                [
                    _mail(
                        from_name="John Paul Fürus",
                        from_address="hit-reply@linkedin.com",
                        subject="Message replied: Steuerberater (m/w/d) gesucht",
                        body_text="Gerne telefonieren.\n\nThis email was intended for Gege.\n",
                    )
                ],
            )

            assert result.ok is True
            assert result.created_activities == 1

            activity = session.query(Activity).one()
            assert activity.activity_type == ACTIVITY_TYPE_LINKEDIN
            assert activity.candidate_id == candidate_id
            # Rollentitel als Betreff, Boilerplate raus.
            assert activity.subject == "Steuerberater (m/w/d) gesucht"
            assert "intended for" not in (activity.details or "")

    def test_unknown_person_goes_to_review_without_creating_candidate(
        self, session_factory: sessionmaker[Session]
    ) -> None:
        """Kernregel: aus einer Mail entsteht NIE automatisch ein Kandidat -
        gleiche Governance wie beim Sourcing-Lead-Review."""
        with session_factory() as session:
            account = _make_account(session)

            result = _sync(
                session,
                account,
                [
                    _mail(
                        from_name="Wildfremde Person",
                        from_address="hit-reply@linkedin.com",
                        subject="Message replied: Rolle",
                    )
                ],
            )

            assert result.pending_review == 1
            assert result.created_activities == 0
            assert session.query(Candidate).count() == 0
            assert session.query(Activity).count() == 0
            assert session.query(MailMessage).one().match_status == MailMatchStatus.PENDING_REVIEW


class TestAddressMatching:
    def test_known_candidate_address_creates_email_activity(
        self, session_factory: sessionmaker[Session]
    ) -> None:
        with session_factory() as session:
            account = _make_account(session)
            session.add(
                Candidate(first_name="Anna", last_name="Müller", email="anna.mueller@example.com")
            )
            session.commit()

            result = _sync(session, account, [_mail()])

            assert result.created_activities == 1
            activity = session.query(Activity).one()
            assert activity.activity_type == ACTIVITY_TYPE_EMAIL
            assert activity.subject == "Rückfrage"

    def test_address_match_is_case_insensitive(
        self, session_factory: sessionmaker[Session]
    ) -> None:
        with session_factory() as session:
            account = _make_account(session)
            session.add(
                Candidate(first_name="Anna", last_name="Müller", email="Anna.Mueller@Example.com")
            )
            session.commit()

            result = _sync(session, account, [_mail(from_address="anna.mueller@example.com")])

            assert result.created_activities == 1

    def test_contact_person_activity_is_attached_to_their_company(
        self, session_factory: sessionmaker[Session]
    ) -> None:
        with session_factory() as session:
            account = _make_account(session)
            company = ClientCompany(name="Kanzlei Muster")
            session.add(company)
            session.flush()
            session.add(
                ContactPerson(
                    first_name="Bernd",
                    last_name="Schmidt",
                    email="b.schmidt@kanzlei-muster.de",
                    client_company_id=company.id,
                )
            )
            session.commit()
            company_id = company.id

            _sync(session, account, [_mail(from_address="b.schmidt@kanzlei-muster.de")])

            activity = session.query(Activity).one()
            assert activity.client_company_id == company_id

    def test_unknown_address_is_archived_without_review(
        self, session_factory: sessionmaker[Session]
    ) -> None:
        """Newsletter & Co. brauchen kein Review - nur ablegen."""
        with session_factory() as session:
            account = _make_account(session)

            result = _sync(session, account, [_mail(from_address="news@irgendwo.de")])

            assert result.created_activities == 0
            assert result.pending_review == 0
            assert session.query(MailMessage).one().match_status == MailMatchStatus.UNMATCHED


class TestSelfSentAndDedup:
    def test_own_sent_mail_is_stored_but_not_recorded_as_activity(
        self, session_factory: sessionmaker[Session]
    ) -> None:
        """Der Sync sieht auch den Sent-Ordner - die eigenen Mails duerfen
        nicht als eingehende Aktivitaet auftauchen."""
        with session_factory() as session:
            account = _make_account(session)
            session.add(
                Candidate(first_name="Anna", last_name="Müller", email="anna.mueller@example.com")
            )
            session.commit()

            result = _sync(
                session,
                account,
                [_mail(from_address="info@commandeurconsulting.de")],
            )

            assert result.created_activities == 0
            assert session.query(Activity).count() == 0
            assert session.query(MailMessage).one().direction == MailDirection.OUTBOUND

    def test_own_address_detection_is_case_insensitive(
        self, session_factory: sessionmaker[Session]
    ) -> None:
        with session_factory() as session:
            account = _make_account(session)

            _sync(session, account, [_mail(from_address="INFO@CommandeurConsulting.de")])

            assert session.query(MailMessage).one().direction == MailDirection.OUTBOUND

    def test_second_run_skips_already_stored_message(
        self, session_factory: sessionmaker[Session]
    ) -> None:
        """Idempotenz: derselbe Abruf zweimal darf keine doppelten
        Activities/Zeilen erzeugen."""
        with session_factory() as session:
            account = _make_account(session)
            session.add(
                Candidate(first_name="Anna", last_name="Müller", email="anna.mueller@example.com")
            )
            session.commit()
            mails = [_mail()]

            first = _sync(session, account, mails)
            second = _sync(session, account, mails)

            assert first.created_activities == 1
            assert second.created_activities == 0
            assert second.skipped_duplicates == 1
            assert session.query(Activity).count() == 1
            assert session.query(MailMessage).count() == 1


class TestSyncBookkeeping:
    def test_successful_run_updates_uid_and_clears_previous_error(
        self, session_factory: sessionmaker[Session]
    ) -> None:
        with session_factory() as session:
            account = _make_account(session, sync_error="alter Fehler", last_seen_uid="5")

            _sync(
                session,
                account,
                [_mail(message_id="a@x", uid="7"), _mail(message_id="b@x", uid="12")],
            )

            session.refresh(account)
            assert account.sync_error is None
            assert account.last_seen_uid == "12"
            assert account.last_synced_at is not None

    def test_uid_comparison_is_numeric_not_lexicographic(self) -> None:
        """Regressionsschutz: "9" darf nicht als groesser als "10" gelten -
        sonst faellt der Abrufstand zurueck und Mails werden doppelt geholt."""
        assert _max_uid("9", "10") == "10"
        assert _max_uid("10", "9") == "10"
        assert _max_uid(None, "3") == "3"
        assert _max_uid("3", None) == "3"

    def test_connection_failure_is_reported_not_raised(
        self, session_factory: sessionmaker[Session]
    ) -> None:
        """Nutzer-Vorgabe: der Grund muss sichtbar sein (Zugangsdaten vs.
        Netzwerk), deshalb ok=False + Fehlertext statt einer Exception."""
        with session_factory() as session:
            account = _make_account(session)

            def failing_fetch(_account: MailAccount, _uid: str | None) -> list[FetchedMail]:
                raise ConnectionError("LOGIN failed: authentication failed")

            result = MailSyncService(session, fetcher=failing_fetch).sync_account(account)

            assert result.ok is False
            assert result.error is not None
            assert "authentication failed" in result.error
            session.refresh(account)
            assert account.sync_error == result.error

    def test_password_is_never_leaked_into_sync_error(
        self, session_factory: sessionmaker[Session]
    ) -> None:
        """Manche IMAP-Bibliotheken zitieren den fehlgeschlagenen
        LOGIN-Befehl inklusive Passwort - das darf weder in der DB noch im
        UI landen."""
        with session_factory() as session:
            account = _make_account(session)

            def leaking_fetch(_account: MailAccount, _uid: str | None) -> list[FetchedMail]:
                raise ConnectionError('command LOGIN "info" "geheim" failed')

            result = MailSyncService(session, fetcher=leaking_fetch).sync_account(account)

            assert result.error is not None
            assert "geheim" not in result.error
            assert "***" in result.error

    def test_broken_mail_does_not_discard_already_processed_mails(
        self, session_factory: sessionmaker[Session]
    ) -> None:
        """Regressionsschutz fuer einen im Test gefundenen Bug: bei einem
        Fehler wird zurueckgerollt - ohne Commit pro Mail hat dieses
        Rollback auch alle BEREITS verarbeiteten Mails desselben Laufs
        verworfen. Deshalb steht die kaputte Mail hier bewusst HINTEN.
        """
        with session_factory() as session:
            account = _make_account(session)
            session.add(
                Candidate(first_name="Anna", last_name="Müller", email="anna.mueller@example.com")
            )
            session.commit()

            good = _mail(message_id="good@x", uid="2")
            # message_id=None verletzt die NOT-NULL-Spalte - stellvertretend
            # fuer jede unerwartet kaputte Mail.
            broken = _mail(message_id=None, uid="3")

            result = _sync(session, account, [good, broken])

            assert result.ok is True
            assert result.failed_messages == 1
            assert result.created_activities == 1
            # Die gute Mail muss den Lauf ueberlebt haben.
            assert session.query(Activity).count() == 1
            assert (
                session.query(MailMessage).filter(MailMessage.message_id == "good@x").count() == 1
            )

    def test_broken_mail_first_still_lets_later_mails_through(
        self, session_factory: sessionmaker[Session]
    ) -> None:
        with session_factory() as session:
            account = _make_account(session)
            session.add(
                Candidate(first_name="Anna", last_name="Müller", email="anna.mueller@example.com")
            )
            session.commit()

            result = _sync(
                session,
                account,
                [_mail(message_id=None, uid="2"), _mail(message_id="good@x", uid="3")],
            )

            assert result.failed_messages == 1
            assert result.created_activities == 1
