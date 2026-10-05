"""Vorstellungs-Archiv: Nachweis fuer Honorar-Streitfaelle (Regel des Nutzers 2026-10-05).

Bei jeder Vorstellung, die TATSAECHLICH an eine Kanzlei versendet wird, wird festgehalten, was
hinausgegangen ist: Empfaenger, Betreff, Mailtext, die EXAKTEN Bytes der versendeten Anhaenge
(mit SHA-256) und der Profiltext zum Versandzeitpunkt. Nur Admins sehen das Archiv
(api/v1/presentation_archive.py).

Wann ist ein Versand eine Vorstellung? Wenn `send_mail` einen Kandidaten UND eine Kanzlei als
Ziel kennt: `candidate_id` zusammen mit `client_company_id` oder `contact_person_id` (der Kontakt
wird zur Kanzlei aufgeloest). Das deckt Einzelversand (/mail/send) und den Massenversand der
CV-Out-Kampagne (/mail/send-bulk, Kandidat aus `MailingGroup.context_candidate_id`) ab. Der
blosse Stufenwechsel nach cv_out (Transition, Sammel-Einreichung, Quick-Log) versendet nichts und
schreibt deshalb nichts ins Archiv.

Ablauf in `send_mail`: VOR dem Versand werden die Dateien unter `presentation-archive/` abgelegt
(`prepare`) - schlaegt das fehl, geht keine Mail raus ("kein Versand ohne Beleg"). Scheitert der
Versand, werden die gerade abgelegten Dateien wieder entfernt (`discard`) und es entsteht kein
Eintrag. Nach erfolgreichem Versand wird die Zeile im selben Commit wie die Mail geschrieben.

Entfernen: nur ueber Antrag eines Admins mit Begruendung und Freigabe durch einen ZWEITEN Admin,
und nur wenn `retention_until` gesetzt und abgelaufen ist; es entsteht ein Audit-Eintrag ohne
Personendaten. Weder Teil-Loeschung noch Anonymisierung noch scripts/purge_job_blobs.py beruehren
das Archiv - es hat weder eine documents-Zeile noch Fremdschluessel."""

from __future__ import annotations

import hashlib
import logging
import uuid
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from typing import Any, Protocol

from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from cc_crm.core.errors import BusinessRuleError, EntityNotFoundError
from cc_crm.models.candidate import Candidate
from cc_crm.models.client_company import ClientCompany
from cc_crm.models.contact_person import ContactPerson
from cc_crm.models.enums import SubmissionStatus
from cc_crm.models.presentation_record import PresentationRecord, PresentationRemovalRequest
from cc_crm.models.recruiting import AuditLog
from cc_crm.models.submission import CandidateSubmission
from cc_crm.models.user import User
from cc_crm.services.storage import (
    _safe_filename,
    delete_document_bytes,
    read_document_bytes,
    save_document_bytes,
)

logger = logging.getLogger("cc_crm.presentation_archive")

ARCHIVE_PREFIX = "presentation-archive"
PENDING = "pending"
APPROVED = "approved"
REJECTED = "rejected"
MIN_REASON_LENGTH = 10
# Stufen, ab denen ein Prozess als "vorgestellt" gilt (fuer die Zaehlung ohne Archiv-Eintrag).
PRESENTED_STATUSES = (
    SubmissionStatus.CV_OUT,
    SubmissionStatus.INTERVIEW,
    SubmissionStatus.OFFER,
    SubmissionStatus.PLACEMENT,
)


class _AttachmentLike(Protocol):
    @property
    def filename(self) -> str: ...

    @property
    def content(self) -> bytes: ...

    @property
    def content_type(self) -> str: ...


@dataclass
class PendingArchive:
    """Vorbereiteter Eintrag: Dateien sind abgelegt, die Zeile folgt nach dem Versand."""

    record_id: uuid.UUID
    candidate_id: uuid.UUID
    client_id: uuid.UUID
    client_name: str | None
    candidate_number: str | None
    submission_id: uuid.UUID | None
    profile_text: str | None
    files: list[dict[str, Any]] = field(default_factory=list)


def sha256_hex(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def resolve_client_id(
    session: Session,
    client_company_id: uuid.UUID | None,
    contact_person_id: uuid.UUID | None,
) -> uuid.UUID | None:
    if client_company_id is not None:
        return client_company_id
    if contact_person_id is not None:
        contact = session.get(ContactPerson, contact_person_id)
        if contact is not None:
            return contact.client_company_id
    return None


def prepare(
    session: Session,
    *,
    candidate_id: uuid.UUID | None,
    client_company_id: uuid.UUID | None,
    contact_person_id: uuid.UUID | None,
    attachments: Sequence[_AttachmentLike],
) -> PendingArchive | None:
    """Gibt None zurueck, wenn der Versand keine Vorstellung ist. Sonst legt es die Dateien
    ab und liefert den vorbereiteten Eintrag. Wirft bei Speicherfehlern (dann darf nicht
    gesendet werden)."""
    if candidate_id is None:
        return None
    client_id = resolve_client_id(session, client_company_id, contact_person_id)
    if client_id is None:
        return None
    candidate = session.get(Candidate, candidate_id)
    client = session.get(ClientCompany, client_id)
    submission = session.scalar(
        select(CandidateSubmission)
        .where(
            CandidateSubmission.candidate_id == candidate_id,
            CandidateSubmission.client_company_id == client_id,
        )
        .order_by(
            (CandidateSubmission.status == SubmissionStatus.CANCELLED),
            CandidateSubmission.created_at.desc(),
        )
        .limit(1)
    )
    profile = None
    if submission is not None and submission.sent_profile_text:
        profile = submission.sent_profile_text
    elif candidate is not None:
        profile = candidate.short_profile
    pending = PendingArchive(
        record_id=uuid.uuid4(),
        candidate_id=candidate_id,
        client_id=client_id,
        client_name=client.name if client else None,
        candidate_number=candidate.candidate_number if candidate else None,
        submission_id=submission.id if submission else None,
        profile_text=profile,
    )
    try:
        for index, attachment in enumerate(attachments, start=1):
            digest = sha256_hex(attachment.content)
            key = (
                f"{ARCHIVE_PREFIX}/{pending.record_id}/"
                f"{index:02d}_{digest[:12]}_{_safe_filename(attachment.filename)}"
            )
            save_document_bytes(
                owner_type=ARCHIVE_PREFIX,
                owner_id=pending.record_id,
                filename=attachment.filename,
                content=attachment.content,
                storage_key=key,
            )
            pending.files.append(
                {
                    "storage_key": key,
                    "filename": attachment.filename,
                    "sha256": digest,
                    "size": len(attachment.content),
                    "content_type": attachment.content_type,
                }
            )
    except Exception:
        discard(pending)
        raise
    return pending


def discard(pending: PendingArchive) -> None:
    """Entfernt die fuer einen gescheiterten Versand abgelegten Dateien wieder. Betrifft nur
    Schluessel, die `prepare` selbst gerade geschrieben hat und die noch in keiner Zeile stehen."""
    for file in pending.files:
        try:
            delete_document_bytes(file["storage_key"])
        except Exception:  # noqa: BLE001 - Aufraeumen ist best effort
            logger.warning("Archivdatei %s konnte nicht entfernt werden", file["storage_key"])
    pending.files.clear()


def add_record(
    session: Session,
    pending: PendingArchive,
    *,
    recipient_email: str,
    subject: str,
    body_text: str,
    message_id: str | None,
    mail_record_id: uuid.UUID | None,
    sent_at: datetime,
    user: User | None,
) -> PresentationRecord:
    record = PresentationRecord(
        id=pending.record_id,
        submission_id=pending.submission_id,
        candidate_id=pending.candidate_id,
        client_id=pending.client_id,
        candidate_number=pending.candidate_number,
        client_name=pending.client_name,
        sent_at=sent_at,
        sent_by_user_id=user.id if user else None,
        sent_by_email=user.email if user else None,
        recipient_emails=[recipient_email],
        mail_subject=subject,
        mail_body_text=body_text,
        mail_message_id=message_id,
        mail_record_id=mail_record_id,
        files=list(pending.files),
        profile_text_snapshot=pending.profile_text,
    )
    session.add(record)
    return record


def count_presented_without_record(session: Session) -> tuple[int, int]:
    """Nur Zaehlung (nichts wird geaendert): (Prozesse ab cv_out, davon ohne Archiv-Eintrag).
    Es gibt bewusst KEINEN Backfill - fuer bereits abgeschlossene Vorstellungen existiert kein
    Beleg. Ein Prozess zaehlt als archiviert, wenn ein Eintrag mit seiner submission_id oder mit
    derselben Kandidat/Kanzlei-Kombination existiert."""
    submissions = session.scalars(
        select(CandidateSubmission).where(CandidateSubmission.status.in_(PRESENTED_STATUSES))
    ).all()
    by_id = {
        row[0]
        for row in session.execute(select(PresentationRecord.submission_id)).all()
        if row[0] is not None
    }
    by_pair = {
        (row[0], row[1])
        for row in session.execute(
            select(PresentationRecord.candidate_id, PresentationRecord.client_id)
        ).all()
    }
    missing = sum(
        1
        for s in submissions
        if s.id not in by_id and (s.candidate_id, s.client_company_id) not in by_pair
    )
    return len(submissions), missing


class PresentationArchiveService:
    """Admin-Funktionen (Liste, Detail, Download, Pruefsumme, Aufbewahrung, Entfernen)."""

    def __init__(self, session: Session) -> None:
        self.session = session

    # --- Lesen -------------------------------------------------------------------------------

    def list_records(
        self,
        *,
        client_id: uuid.UUID | None = None,
        candidate_number: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[PresentationRecord], int]:
        statement = select(PresentationRecord)
        if client_id is not None:
            statement = statement.where(PresentationRecord.client_id == client_id)
        if candidate_number:
            statement = statement.where(
                PresentationRecord.candidate_number == candidate_number.strip()
            )
        total = int(
            self.session.scalar(select(func.count()).select_from(statement.subquery())) or 0
        )
        rows = self.session.scalars(
            statement.order_by(PresentationRecord.sent_at.desc()).limit(limit).offset(offset)
        ).all()
        return list(rows), total

    def get(self, record_id: uuid.UUID) -> PresentationRecord:
        record = self.session.get(PresentationRecord, record_id)
        if record is None:
            raise EntityNotFoundError("Nicht gefunden")
        return record

    def read_file(self, record: PresentationRecord, index: int) -> tuple[dict[str, Any], bytes]:
        if index < 0 or index >= len(record.files):
            raise EntityNotFoundError("Nicht gefunden")
        meta = record.files[index]
        try:
            return meta, read_document_bytes(meta["storage_key"])
        except FileNotFoundError as exc:
            raise EntityNotFoundError("Datei im Speicher nicht vorhanden") from exc

    def verify(self, record: PresentationRecord) -> list[dict[str, Any]]:
        """Liest jede Datei neu und vergleicht den SHA-256 mit dem beim Versand erfassten."""
        results: list[dict[str, Any]] = []
        for index, meta in enumerate(record.files):
            actual: str | None
            try:
                actual = sha256_hex(read_document_bytes(meta["storage_key"]))
            except FileNotFoundError:
                actual = None
            results.append(
                {
                    "index": index,
                    "filename": meta["filename"],
                    "expected_sha256": meta["sha256"],
                    "actual_sha256": actual,
                    "ok": actual == meta["sha256"],
                    "missing": actual is None,
                }
            )
        return results

    def pending_request(self, record_id: uuid.UUID) -> PresentationRemovalRequest | None:
        return self.session.scalar(
            select(PresentationRemovalRequest).where(
                PresentationRemovalRequest.record_id == record_id,
                PresentationRemovalRequest.status == PENDING,
            )
        )

    # --- Aufbewahrung ------------------------------------------------------------------------

    def set_retention(
        self, record_id: uuid.UUID, retention_until: date | None, admin: User
    ) -> PresentationRecord:
        record = self.get(record_id)
        record.retention_until = retention_until
        record.retention_set_by = admin.email
        record.retention_set_at = datetime.now(UTC)
        self._audit(
            record_id,
            "presentation_retention_set",
            admin,
            {"retention_until": retention_until.isoformat() if retention_until else None},
        )
        self.session.commit()
        self.session.refresh(record)
        return record

    # --- Entfernen (Antrag + Freigabe durch einen zweiten Admin) ------------------------------

    def request_removal(
        self, record_id: uuid.UUID, reason: str, admin: User
    ) -> PresentationRemovalRequest:
        record = self.get(record_id)
        reason = reason.strip()
        if len(reason) < MIN_REASON_LENGTH:
            raise BusinessRuleError(
                f"Bitte eine Begruendung angeben (mindestens {MIN_REASON_LENGTH} Zeichen)."
            )
        self._ensure_retention_expired(record)
        if self.pending_request(record_id) is not None:
            raise BusinessRuleError("Fuer diesen Eintrag liegt bereits ein offener Antrag vor.")
        request = PresentationRemovalRequest(
            id=uuid.uuid4(),
            record_id=record_id, reason=reason, status=PENDING, requested_by=admin.email
        )
        self.session.add(request)
        self._audit(
            record_id, "presentation_removal_requested", admin, {"request_id": str(request.id)}
        )
        self.session.commit()
        self.session.refresh(request)
        return request

    def list_requests(self, status: str | None = None) -> list[PresentationRemovalRequest]:
        statement = select(PresentationRemovalRequest).order_by(
            PresentationRemovalRequest.created_at.desc()
        )
        if status:
            statement = statement.where(PresentationRemovalRequest.status == status)
        return list(self.session.scalars(statement).all())

    def decide(
        self, request_id: uuid.UUID, admin: User, *, approve: bool, note: str | None = None
    ) -> PresentationRemovalRequest:
        request = self.session.get(PresentationRemovalRequest, request_id)
        if request is None:
            raise EntityNotFoundError("Nicht gefunden")
        if request.status != PENDING:
            raise BusinessRuleError("Der Antrag ist bereits entschieden.")
        if approve and request.requested_by == admin.email:
            raise BusinessRuleError(
                "Die Freigabe muss ein anderer Admin als der Antragsteller erteilen."
            )
        request.status = APPROVED if approve else REJECTED
        request.decided_by = admin.email
        request.decided_at = datetime.now(UTC)
        request.decision_note = note
        if approve:
            record = self.get(request.record_id)
            self._ensure_retention_expired(record)
            keys = [meta["storage_key"] for meta in record.files]
            if self.session.get_bind().dialect.name == "postgresql":
                self.session.execute(text("SET LOCAL cc_crm.presentation_removal = 'on'"))
            self.session.delete(record)
            self._audit(
                request.record_id,
                "presentation_removed",
                admin,
                {"request_id": str(request.id), "file_count": len(keys)},
            )
            self.session.commit()
            for key in keys:
                delete_document_bytes(key)
        else:
            self._audit(
                request.record_id,
                "presentation_removal_rejected",
                admin,
                {"request_id": str(request.id)},
            )
            self.session.commit()
        self.session.refresh(request)
        return request

    # --- intern ------------------------------------------------------------------------------

    @staticmethod
    def _ensure_retention_expired(record: PresentationRecord) -> None:
        if record.retention_until is None:
            raise BusinessRuleError(
                "Ohne gesetzte Aufbewahrungsfrist (retention_until) kann nichts entfernt werden."
            )
        if record.retention_until > datetime.now(UTC).date():
            raise BusinessRuleError(
                f"Die Aufbewahrungsfrist laeuft noch bis {record.retention_until.isoformat()}."
            )

    def _audit(
        self, record_id: uuid.UUID, action: str, admin: User, new_values: dict[str, Any]
    ) -> None:
        # Bewusst ohne Personendaten: nur Kennungen und Zaehlwerte (Begruendung: im Antrag).
        self.session.add(
            AuditLog(
                entity_type="presentation_record",
                entity_id=record_id,
                action=action,
                changed_by=admin.email,
                new_values=new_values,
            )
        )
