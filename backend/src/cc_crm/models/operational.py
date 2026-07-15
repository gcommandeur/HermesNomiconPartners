import uuid
from datetime import date, datetime

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from cc_crm.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class Document(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "documents"
    __table_args__ = (Index("ix_documents_owner", "owner_type", "owner_id"),)

    owner_type: Mapped[str] = mapped_column(String(40), nullable=False)
    owner_id: Mapped[uuid.UUID] = mapped_column(nullable=False)
    document_type: Mapped[str] = mapped_column(String(60), nullable=False)
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    storage_key: Mapped[str] = mapped_column(String(500), nullable=False)
    content_type: Mapped[str | None] = mapped_column(String(120))
    size_bytes: Mapped[int | None] = mapped_column(Integer)
    uploaded_by: Mapped[str | None] = mapped_column(String(160))
    sent_with_submission_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("candidate_submissions.id", ondelete="SET NULL"), index=True
    )
    # True, wenn filename einem generischen Muster entspricht (siehe
    # services/storage.py:has_generic_filename) - Hinweis fuer den Recruiter,
    # das Dokument ggf. sprechender umzubenennen.
    has_generic_filename: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)


class SourcingMetric(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "sourcing_metrics"

    period_start: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    period_end: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    source: Mapped[str] = mapped_column(String(80), default="LinkedIn", nullable=False)
    campaign: Mapped[str | None] = mapped_column(String(240))
    pitches: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    responses: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    positive_responses: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    qualification_calls: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    notes: Mapped[str | None] = mapped_column(Text)


class EmailDraftLog(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "email_draft_logs"

    template_key: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    candidate_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("candidates.id", ondelete="SET NULL"), index=True
    )
    client_company_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("client_companies.id", ondelete="SET NULL"), index=True
    )
    candidate_submission_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("candidate_submissions.id", ondelete="SET NULL"), index=True
    )
    recipient: Mapped[str | None] = mapped_column(String(320))
    subject: Mapped[str] = mapped_column(String(240), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    provider: Mapped[str] = mapped_column(String(40), default="outlook", nullable=False)
    external_draft_id: Mapped[str | None] = mapped_column(String(240))
    drafted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
