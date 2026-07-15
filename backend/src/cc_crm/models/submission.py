import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from cc_crm.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from cc_crm.models.enums import ClosingStatus, SubmissionCancellationReason, SubmissionStatus


class CandidateSubmission(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "candidate_submissions"
    __table_args__ = (
        Index(
            "ix_candidate_submissions_candidate_client_status",
            "candidate_id",
            "client_company_id",
            "status",
        ),
    )

    candidate_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("candidates.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    client_company_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("client_companies.id", ondelete="RESTRICT"),
        index=True,
    )
    job_mandate_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("job_mandates.id", ondelete="SET NULL"),
        index=True,
    )
    contact_person_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("contact_persons.id", ondelete="SET NULL"),
        index=True,
    )
    status: Mapped[SubmissionStatus] = mapped_column(
        Enum(SubmissionStatus, native_enum=False, length=40),
        default=SubmissionStatus.QUALIFICATION_CALL,
        nullable=False,
        index=True,
    )
    cancellation_reason: Mapped[SubmissionCancellationReason | None] = mapped_column(
        Enum(SubmissionCancellationReason, native_enum=False, length=40),
    )
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_activity_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    summary: Mapped[str | None] = mapped_column(Text)
    sent_profile_text: Mapped[str | None] = mapped_column(Text)
    salary_at_submission: Mapped[str | None] = mapped_column(String(120))
    fee_percentage: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))
    expected_fee: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    refund_terms: Mapped[str | None] = mapped_column(Text)
    feedback_summary: Mapped[str | None] = mapped_column(Text)
    next_step: Mapped[str | None] = mapped_column(String(240))
    follow_up_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    owner: Mapped[str | None] = mapped_column(String(160))
    outlook_draft_created: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    email_sent: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    # --- Closing-Probability-Modell (Quali-Call-Scoring, 2026-07) ---
    pain_staerke: Mapped[int | None] = mapped_column(Integer)
    entscheidungsklarheit: Mapped[int | None] = mapped_column(Integer)
    markt_fit: Mapped[int | None] = mapped_column(Integer)
    momentum: Mapped[int | None] = mapped_column(Integer)
    closing_probability: Mapped[float | None] = mapped_column(Float, index=True)
    closing_status: Mapped[ClosingStatus | None] = mapped_column(
        Enum(ClosingStatus, native_enum=False, length=16)
    )
