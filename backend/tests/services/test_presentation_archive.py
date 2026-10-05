"""Vorstellungs-Archiv: Erfassung bei jedem Sendeweg, Pruefsumme, Fehlschlag, Loeschwege."""

from __future__ import annotations

import hashlib
from collections.abc import Iterator
from pathlib import Path

import pytest
from cryptography.fernet import Fernet
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from cc_crm.core.config import get_settings
from cc_crm.models.candidate import Candidate
from cc_crm.models.client_company import ClientCompany
from cc_crm.models.contact_person import ContactPerson
from cc_crm.models.mail import MailAccount
from cc_crm.models.presentation_record import PresentationRecord
from cc_crm.models.submission import CandidateSubmission
from cc_crm.services.mail_send import (
    BulkRecipient,
    MailAttachmentRef,
    MailSendError,
    send_bulk,
    send_mail,
)
from cc_crm.services.presentation_archive import (
    ARCHIVE_PREFIX,
    PresentationArchiveService,
    count_presented_without_record,
    sha256_hex,
)
from cc_crm.services.storage import read_document_bytes, save_document_bytes

_KEY = Fernet.generate_key().decode()
PROFILE_BYTES = b"PK\x03\x04 anonymes Profil Nr. 4711 \x00\xff binary"


@pytest.fixture(autouse=True)
def _env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Iterator[None]:
    monkeypatch.setenv("CC_CRM_MAIL_CREDENTIALS_ENCRYPTION_KEY", _KEY)
    monkeypatch.setenv("CC_CRM_DOCUMENTS_STORAGE_DIR", str(tmp_path / "docs"))
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


class Transport:
    def __init__(self, error: Exception | None = None) -> None:
        self.sent: list[str] = []
        self.error = error

    def smtp_sender(self, account: MailAccount, password: str, message, to_address: str) -> None:
        if self.error is not None:
            raise self.error
        self.sent.append(to_address)

    def imap_appender(self, account: MailAccount, password: str, message) -> bool:
        return True


class World:
    def __init__(self, session: Session) -> None:
        self.session = session
        self.account = MailAccount(
            address="berater@agentur.example",
            label="Berater",
            imap_host="imap.example",
            smtp_host="smtp.example",
            username="berater@agentur.example",
            encrypted_password=Fernet(_KEY.encode()).encrypt(b"geheim").decode(),
        )
        self.client = ClientCompany(name="Kanzlei Weiss & Partner")
        self.candidate = Candidate(
            first_name="Greta",
            last_name="Vorgestellt",
            consent_received=True,
            candidate_number="4711",
            short_profile="Steuerfachwirtin mit DATEV",
        )
        session.add_all([self.account, self.client, self.candidate])
        session.commit()
        self.contact = ContactPerson(
            client_company_id=self.client.id,
            first_name="Karl",
            last_name="Kontakt",
            email="karl@kanzlei.example",
        )
        session.add(self.contact)
        session.commit()
        self.profile_key = save_document_bytes(
            owner_type="candidate",
            owner_id=self.candidate.id,
            filename="Nr_4711.docx",
            content=PROFILE_BYTES,
        )

    def attachment(self) -> list[MailAttachmentRef]:
        return [MailAttachmentRef(storage_key=self.profile_key, filename="Nr_4711.docx")]


@pytest.fixture
def world(session_factory: sessionmaker[Session]) -> Iterator[World]:
    with session_factory() as session:
        yield World(session)


def _records(session: Session) -> list[PresentationRecord]:
    return list(session.scalars(select(PresentationRecord)).all())


def _archive_files(tmp_path: Path) -> list[Path]:
    root = tmp_path / "docs" / ARCHIVE_PREFIX
    return [p for p in root.rglob("*") if p.is_file()] if root.exists() else []


def test_single_send_to_client_archives_exact_bytes(world: World, tmp_path: Path) -> None:
    transport = Transport()
    mail = send_mail(
        world.session,
        account=world.account,
        to_address="karl@kanzlei.example",
        subject="Kandidat-Nr. 4711 - Steuerfachwirtin",
        body_text="Sehr geehrter Herr Kontakt, anbei das Kurzprofil.",
        attachments=world.attachment(),
        candidate_id=world.candidate.id,
        client_company_id=world.client.id,
        smtp_sender=transport.smtp_sender,
        imap_appender=transport.imap_appender,
    )
    records = _records(world.session)
    assert len(records) == 1
    record = records[0]
    assert record.candidate_number == "4711"
    assert record.client_name == "Kanzlei Weiss & Partner"
    assert record.client_id == world.client.id
    assert record.recipient_emails == ["karl@kanzlei.example"]
    assert record.mail_subject == "Kandidat-Nr. 4711 - Steuerfachwirtin"
    assert record.mail_body_text.startswith("Sehr geehrter Herr Kontakt")
    assert record.mail_record_id == mail.id
    assert record.profile_text_snapshot == "Steuerfachwirtin mit DATEV"
    (meta,) = record.files
    assert meta["sha256"] == hashlib.sha256(PROFILE_BYTES).hexdigest()
    assert meta["filename"] == "Nr_4711.docx"
    assert meta["storage_key"].startswith(f"{ARCHIVE_PREFIX}/")
    # Kopie der tatsaechlich versendeten Bytes, unter eigenem Praefix und eigener Datei.
    assert read_document_bytes(meta["storage_key"]) == PROFILE_BYTES
    assert meta["storage_key"] != world.profile_key
    assert len(_archive_files(tmp_path)) == 1


def test_contact_person_path_resolves_the_client_and_links_the_submission(
    world: World,
) -> None:
    submission = CandidateSubmission(
        candidate_id=world.candidate.id,
        client_company_id=world.client.id,
        sent_profile_text="Der genau versendete Profiltext",
    )
    world.session.add(submission)
    world.session.commit()
    transport = Transport()
    send_mail(
        world.session,
        account=world.account,
        to_address="karl@kanzlei.example",
        subject="Profil",
        body_text="Text",
        candidate_id=world.candidate.id,
        contact_person_id=world.contact.id,
        smtp_sender=transport.smtp_sender,
        imap_appender=transport.imap_appender,
    )
    (record,) = _records(world.session)
    assert record.client_id == world.client.id
    assert record.submission_id == submission.id
    assert record.profile_text_snapshot == "Der genau versendete Profiltext"
    assert record.files == []  # ohne Anhang: nur Text archiviert


def test_bulk_send_archives_one_record_per_recipient(world: World, tmp_path: Path) -> None:
    other = ContactPerson(
        client_company_id=world.client.id,
        first_name="Lena",
        last_name="Zweite",
        email="lena@kanzlei.example",
    )
    world.session.add(other)
    world.session.commit()
    transport = Transport()
    result = send_bulk(
        world.session,
        account=world.account,
        recipients=[
            BulkRecipient(
                to_address=c.email or "",
                candidate_id=world.candidate.id,
                contact_person_id=c.id,
            )
            for c in (world.contact, other)
        ],
        subject="CV-Out",
        body_text="Kurzprofil",
        attachments=world.attachment(),
        sleep=lambda _s: None,
        smtp_sender=transport.smtp_sender,
        imap_appender=transport.imap_appender,
    )
    assert len(result.sent) == 2
    records = _records(world.session)
    assert len(records) == 2
    assert {r.recipient_emails[0] for r in records} == {
        "karl@kanzlei.example",
        "lena@kanzlei.example",
    }
    assert all(r.files[0]["sha256"] == sha256_hex(PROFILE_BYTES) for r in records)
    assert len(_archive_files(tmp_path)) == 2  # je Eintrag eine eigene Datei


@pytest.mark.parametrize("variant", ["candidate_only", "client_only"])
def test_sends_that_are_not_presentations_leave_no_record(world: World, variant: str) -> None:
    transport = Transport()
    send_mail(
        world.session,
        account=world.account,
        to_address="x@example.com",
        subject="Kein Vorstellungsversand",
        body_text="Text",
        candidate_id=world.candidate.id if variant == "candidate_only" else None,
        client_company_id=world.client.id if variant == "client_only" else None,
        smtp_sender=transport.smtp_sender,
        imap_appender=transport.imap_appender,
    )
    assert transport.sent == ["x@example.com"]
    assert _records(world.session) == []


def test_failed_send_creates_no_record_and_no_files(world: World, tmp_path: Path) -> None:
    transport = Transport(error=ConnectionError("SMTP down"))
    with pytest.raises(MailSendError):
        send_mail(
            world.session,
            account=world.account,
            to_address="karl@kanzlei.example",
            subject="Profil",
            body_text="Text",
            attachments=world.attachment(),
            candidate_id=world.candidate.id,
            client_company_id=world.client.id,
            smtp_sender=transport.smtp_sender,
            imap_appender=transport.imap_appender,
        )
    assert _records(world.session) == []
    assert _archive_files(tmp_path) == []  # nichts liegt als Beleg fuer etwas, das nie ging


def test_no_send_without_proof_when_archive_storage_fails(
    world: World, monkeypatch: pytest.MonkeyPatch
) -> None:
    def broken(**_kwargs: object) -> str:
        raise OSError("Speicher voll")

    monkeypatch.setattr("cc_crm.services.presentation_archive.save_document_bytes", broken)
    transport = Transport()
    with pytest.raises(MailSendError, match="NICHT gesendet"):
        send_mail(
            world.session,
            account=world.account,
            to_address="karl@kanzlei.example",
            subject="Profil",
            body_text="Text",
            attachments=world.attachment(),
            candidate_id=world.candidate.id,
            client_company_id=world.client.id,
            smtp_sender=transport.smtp_sender,
            imap_appender=transport.imap_appender,
        )
    assert transport.sent == []
    assert _records(world.session) == []


def _archived(world: World) -> PresentationRecord:
    transport = Transport()
    send_mail(
        world.session,
        account=world.account,
        to_address="karl@kanzlei.example",
        subject="Profil",
        body_text="Text",
        attachments=world.attachment(),
        candidate_id=world.candidate.id,
        client_company_id=world.client.id,
        smtp_sender=transport.smtp_sender,
        imap_appender=transport.imap_appender,
    )
    return _records(world.session)[0]


def test_archive_survives_anonymization_and_candidate_deletion(world: World) -> None:
    from cc_crm.models.user import User
    from cc_crm.services.candidates import CandidateService

    record = _archived(world)
    snapshot = (record.id, record.candidate_number, record.mail_body_text, list(record.files))
    key = record.files[0]["storage_key"]

    admin = User(email="admin@x.example", hashed_password="x", role="admin")
    world.session.add(admin)
    world.session.commit()
    CandidateService(world.session).anonymize(world.candidate.id, admin)

    world.session.expire_all()
    (again,) = _records(world.session)
    assert (again.id, again.candidate_number, again.mail_body_text, list(again.files)) == snapshot
    assert read_document_bytes(key) == PROFILE_BYTES
    # Kein documents-Eintrag: das Archiv taucht in keiner Dokumentenliste auf.
    from cc_crm.models.operational import Document

    assert world.session.scalars(
        select(Document).where(Document.storage_key == key)
    ).all() == []


def test_job_blob_purge_does_not_touch_the_archive(world: World) -> None:
    from cc_crm.services.job_queue import purge_stale_job_blobs

    record = _archived(world)
    key = record.files[0]["storage_key"]
    purge_stale_job_blobs(world.session, older_than_days=0)
    world.session.expire_all()
    assert len(_records(world.session)) == 1
    assert read_document_bytes(key) == PROFILE_BYTES


def test_verify_detects_a_modified_or_missing_file(world: World) -> None:
    record = _archived(world)
    service = PresentationArchiveService(world.session)
    assert all(item["ok"] for item in service.verify(record))

    key = record.files[0]["storage_key"]
    save_document_bytes(
        owner_type=ARCHIVE_PREFIX, owner_id=record.id, filename="x", content=b"manipuliert",
        storage_key=key,
    )
    (item,) = service.verify(record)
    assert item["ok"] is False and item["missing"] is False
    assert item["actual_sha256"] == sha256_hex(b"manipuliert")

    from cc_crm.services.storage import delete_document_bytes

    delete_document_bytes(key)
    (gone,) = service.verify(record)
    assert gone["missing"] is True and gone["ok"] is False


def test_count_of_presented_processes_without_archive_record(world: World) -> None:
    from cc_crm.models.enums import SubmissionStatus

    other = Candidate(first_name="Nora", last_name="Alt", candidate_number="4712")
    world.session.add(other)
    world.session.commit()
    for candidate, status in (
        (world.candidate, SubmissionStatus.CV_OUT),
        (other, SubmissionStatus.INTERVIEW),
        (other, SubmissionStatus.CV_IN),  # noch nicht vorgestellt
    ):
        world.session.add(
            CandidateSubmission(
                candidate_id=candidate.id, client_company_id=world.client.id, status=status
            )
        )
        world.session.commit()
    # Ein Fall ohne Eintrag, einer wird archiviert.
    assert count_presented_without_record(world.session) == (2, 2)
    _archived(world)
    assert count_presented_without_record(world.session) == (2, 1)
