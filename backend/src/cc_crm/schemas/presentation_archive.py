import uuid
from datetime import date, datetime

from pydantic import BaseModel, Field


class PresentationFileRead(BaseModel):
    index: int
    filename: str
    sha256: str
    size: int
    content_type: str


class PresentationRecordListItem(BaseModel):
    id: uuid.UUID
    sent_at: datetime
    client_id: uuid.UUID | None = None
    client_name: str | None = None
    candidate_id: uuid.UUID | None = None
    candidate_number: str | None = None
    candidate_name: str | None = None
    submission_id: uuid.UUID | None = None
    sent_by_email: str | None = None
    recipient_emails: list[str]
    mail_subject: str
    file_count: int
    retention_until: date | None = None
    removal_requested: bool = False


class PresentationRecordDetail(PresentationRecordListItem):
    mail_body_text: str
    mail_message_id: str | None = None
    profile_text_snapshot: str | None = None
    files: list[PresentationFileRead]
    retention_set_by: str | None = None
    retention_set_at: datetime | None = None


class PresentationRecordPage(BaseModel):
    total: int
    items: list[PresentationRecordListItem]


class PresentationVerifyItem(BaseModel):
    index: int
    filename: str
    expected_sha256: str
    actual_sha256: str | None = None
    ok: bool
    missing: bool


class PresentationVerifyResult(BaseModel):
    all_ok: bool
    files: list[PresentationVerifyItem]


class RetentionUpdate(BaseModel):
    retention_until: date | None = None


class RemovalRequestCreate(BaseModel):
    reason: str = Field(min_length=1, max_length=2000)


class RemovalDecision(BaseModel):
    note: str | None = Field(default=None, max_length=2000)


class RemovalRequestRead(BaseModel):
    id: uuid.UUID
    record_id: uuid.UUID
    reason: str
    status: str
    requested_by: str
    created_at: datetime
    decided_by: str | None = None
    decided_at: datetime | None = None
    decision_note: str | None = None
    # Zur Anzeige (Momentaufnahme des Eintrags, solange er noch existiert).
    client_name: str | None = None
    candidate_number: str | None = None


class PresentationCountResult(BaseModel):
    presented_submissions: int
    without_archive_record: int
