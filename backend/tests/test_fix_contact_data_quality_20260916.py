"""Tests fuer scripts/fix_contact_data_quality_20260916.py.

Zwei Schwerpunkte, analog zu tests/test_merge_kanzlei_duplikate.py:
1. Name-Split darf nur leere first_name-Felder anfassen (ein bereits
   bearbeiteter Kontakt wird uebersprungen, nicht ueberschrieben).
2. Vor dem Loeschen eines Dubletten-Kontakts werden ALLE Referenzen
   (CandidateSubmission.contact_person_id, MailMessage.
   matched_contact_person_id, MailingGroup.recipients) auf den Keeper
   umgehaengt - keine davon darf nach dem Loeschen ins Leere zeigen oder
   verwaisen."""

import uuid

import pytest
from sqlalchemy.orm import Session, sessionmaker

from cc_crm.models.candidate import Candidate
from cc_crm.models.client_company import ClientCompany
from cc_crm.models.contact_person import ContactPerson
from cc_crm.models.enums import MailDirection, MailMatchStatus
from cc_crm.models.mail import MailAccount, MailMessage
from cc_crm.models.mailing_group import MailingGroup
from cc_crm.models.submission import CandidateSubmission
from scripts.archive import fix_contact_data_quality_20260916 as script


@pytest.fixture(autouse=True)
def _isolate(monkeypatch: pytest.MonkeyPatch, session_factory: sessionmaker[Session]):
    monkeypatch.setattr(script, "SessionLocal", session_factory)
    # Die im Skript fest hinterlegten Produktivdaten sollen die Tests nicht
    # beeinflussen - jeder Test setzt sich seine eigenen Faelle auf.
    monkeypatch.setattr(script, "NAME_SPLITS", [])
    monkeypatch.setattr(script, "DUPLICATE_PAIRS", [])


def _client(session: Session, name: str = "Muster Kanzlei") -> ClientCompany:
    client = ClientCompany(name=name)
    session.add(client)
    session.commit()
    session.refresh(client)
    return client


def _candidate(session: Session) -> Candidate:
    candidate = Candidate(first_name="Anna", last_name="Muster")
    session.add(candidate)
    session.commit()
    session.refresh(candidate)
    return candidate


def _mail_account(session: Session) -> MailAccount:
    account = MailAccount(
        address=f"{uuid.uuid4().hex[:8]}@example.com",
        label="Test",
        imap_host="imap.example.com",
        smtp_host="smtp.example.com",
        username="test",
        encrypted_password="not-a-real-cipher",
    )
    session.add(account)
    session.commit()
    session.refresh(account)
    return account


def _contact(
    session: Session, client: ClientCompany, *, first_name: str, last_name: str, **kwargs
) -> ContactPerson:
    contact = ContactPerson(
        client_company_id=client.id, first_name=first_name, last_name=last_name, **kwargs
    )
    session.add(contact)
    session.commit()
    session.refresh(contact)
    return contact


class TestApplyNameSplits:
    def test_fills_empty_first_name(self, session_factory: sessionmaker[Session]) -> None:
        with session_factory() as session:
            client = _client(session)
            contact = _contact(session, client, first_name="", last_name="max.mustermann")
            contact_id = contact.id

            script.NAME_SPLITS.append((str(contact_id), "Max", "Mustermann"))
            fixed, skipped = script.apply_name_splits(session, apply=True)
            session.commit()

            assert fixed == 1
            assert skipped == 0
            refreshed = session.get(ContactPerson, contact_id)
            assert refreshed is not None
            assert refreshed.first_name == "Max"
            assert refreshed.last_name == "Mustermann"

    def test_dry_run_does_not_write(self, session_factory: sessionmaker[Session]) -> None:
        with session_factory() as session:
            client = _client(session)
            contact = _contact(session, client, first_name="", last_name="max.mustermann")
            contact_id = contact.id

            script.NAME_SPLITS.append((str(contact_id), "Max", "Mustermann"))
            fixed, skipped = script.apply_name_splits(session, apply=False)
            session.rollback()

            assert fixed == 1
            refreshed = session.get(ContactPerson, contact_id)
            assert refreshed is not None
            assert refreshed.last_name == "max.mustermann"

    def test_skips_contact_with_already_populated_first_name(
        self, session_factory: sessionmaker[Session]
    ) -> None:
        """Ein Kontakt, dessen first_name nicht mehr leer ist (z.B.
        zwischenzeitlich manuell bearbeitet), wird NICHT ueberschrieben."""
        with session_factory() as session:
            client = _client(session)
            contact = _contact(
                session, client, first_name="Schon Gesetzt", last_name="max.mustermann"
            )
            contact_id = contact.id

            script.NAME_SPLITS.append((str(contact_id), "Max", "Mustermann"))
            fixed, skipped = script.apply_name_splits(session, apply=True)
            session.commit()

            assert fixed == 0
            assert skipped == 1
            refreshed = session.get(ContactPerson, contact_id)
            assert refreshed is not None
            assert refreshed.first_name == "Schon Gesetzt"
            assert refreshed.last_name == "max.mustermann"

    def test_skips_missing_contact(self, session_factory: sessionmaker[Session]) -> None:
        with session_factory() as session:
            script.NAME_SPLITS.append((str(uuid.uuid4()), "Max", "Mustermann"))
            fixed, skipped = script.apply_name_splits(session, apply=True)
            assert fixed == 0
            assert skipped == 1


class TestApplyDuplicateDeletions:
    def test_deletes_loser_and_repoints_submission_and_mail_and_mailing_group(
        self, session_factory: sessionmaker[Session]
    ) -> None:
        with session_factory() as session:
            client = _client(session)
            keeper = _contact(
                session,
                client,
                first_name="Waltraud",
                last_name="Nolte",
                role_title="Steuerberaterin",
            )
            loser = _contact(session, client, first_name="Waltraud", last_name="Nolte (Duplikat)")

            mail_account = _mail_account(session)
            candidate = _candidate(session)
            submission = CandidateSubmission(contact_person_id=loser.id, candidate_id=candidate.id)
            session.add(submission)
            message = MailMessage(
                mail_account_id=mail_account.id,
                message_id=f"<{uuid.uuid4()}@example.com>",
                direction=MailDirection.INBOUND,
                match_status=MailMatchStatus.MATCHED,
                matched_contact_person_id=loser.id,
            )
            session.add(message)
            group = MailingGroup(
                name="Testgruppe",
                recipients=[
                    {
                        "kind": "contact",
                        "id": str(loser.id),
                        "name": "Alt",
                        "email": "alt@example.com",
                    }
                ],
            )
            session.add(group)
            session.commit()

            keeper_id, loser_id, submission_id, message_id, group_id = (
                keeper.id,
                loser.id,
                submission.id,
                message.id,
                group.id,
            )

            script.DUPLICATE_PAIRS.append((str(keeper_id), str(loser_id), "Waltraud Nolte"))
            deleted, skipped = script.apply_duplicate_deletions(session, apply=True)
            session.commit()

            assert deleted == 1
            assert skipped == 0
            assert session.get(ContactPerson, loser_id) is None
            assert session.get(ContactPerson, keeper_id) is not None

            refreshed_submission = session.get(CandidateSubmission, submission_id)
            assert refreshed_submission is not None
            assert refreshed_submission.contact_person_id == keeper_id

            refreshed_message = session.get(MailMessage, message_id)
            assert refreshed_message is not None
            assert refreshed_message.matched_contact_person_id == keeper_id

            refreshed_group = session.get(MailingGroup, group_id)
            assert refreshed_group is not None
            assert refreshed_group.recipients[0]["id"] == str(keeper_id)
            assert refreshed_group.recipients[0]["name"] == "Waltraud Nolte"

    def test_dry_run_does_not_delete_or_repoint(
        self, session_factory: sessionmaker[Session]
    ) -> None:
        with session_factory() as session:
            client = _client(session)
            keeper = _contact(session, client, first_name="Waltraud", last_name="Nolte")
            loser = _contact(session, client, first_name="Waltraud", last_name="Nolte (Duplikat)")
            candidate = _candidate(session)
            submission = CandidateSubmission(contact_person_id=loser.id, candidate_id=candidate.id)
            session.add(submission)
            session.commit()
            keeper_id, loser_id, submission_id = keeper.id, loser.id, submission.id

            script.DUPLICATE_PAIRS.append((str(keeper_id), str(loser_id), "Waltraud Nolte"))
            deleted, skipped = script.apply_duplicate_deletions(session, apply=False)
            session.rollback()

            assert deleted == 1
            assert session.get(ContactPerson, loser_id) is not None
            assert session.get(CandidateSubmission, submission_id).contact_person_id == loser_id

    def test_skips_missing_pair(self, session_factory: sessionmaker[Session]) -> None:
        with session_factory() as session:
            client = _client(session)
            keeper = _contact(session, client, first_name="Waltraud", last_name="Nolte")
            script.DUPLICATE_PAIRS.append((str(keeper.id), str(uuid.uuid4()), "Fehlt"))
            deleted, skipped = script.apply_duplicate_deletions(session, apply=True)
            assert deleted == 0
            assert skipped == 1


class TestCountContactReferences:
    def test_counts_all_three_reference_kinds(self, session_factory: sessionmaker[Session]) -> None:
        with session_factory() as session:
            client = _client(session)
            contact = _contact(session, client, first_name="X", last_name="Y")
            mail_account = _mail_account(session)
            candidate = _candidate(session)
            session.add(
                CandidateSubmission(contact_person_id=contact.id, candidate_id=candidate.id)
            )
            session.add(
                MailMessage(
                    mail_account_id=mail_account.id,
                    message_id=f"<{uuid.uuid4()}@example.com>",
                    direction=MailDirection.INBOUND,
                    match_status=MailMatchStatus.MATCHED,
                    matched_contact_person_id=contact.id,
                )
            )
            session.add(
                MailingGroup(
                    name="Testgruppe",
                    recipients=[{"kind": "contact", "id": str(contact.id), "name": "X Y"}],
                )
            )
            session.commit()

            counts = script.count_contact_references(session, contact.id)

            assert counts == {
                "candidate_submissions": 1,
                "mail_messages": 1,
                "mailing_groups": 1,
            }
