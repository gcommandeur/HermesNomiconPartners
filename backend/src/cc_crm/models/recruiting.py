import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import JSON, Date, DateTime, Enum, ForeignKey, Numeric, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from cc_crm.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from cc_crm.models.enums import (
    FeedbackType,
    InterviewStatus,
    InvoiceStatus,
    OfferStatus,
    PlacementStatus,
    SubmissionStatus,
)


class SubmissionFeedback(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "submission_feedback"
    submission_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("candidate_submissions.id", ondelete="CASCADE"), index=True
    )
    feedback_type: Mapped[FeedbackType] = mapped_column(
        Enum(FeedbackType, native_enum=False, length=32), nullable=False
    )
    feedback_text: Mapped[str] = mapped_column(Text, nullable=False)
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    next_step: Mapped[str | None] = mapped_column(String(240))
    created_by: Mapped[str | None] = mapped_column(String(240))
    # Welche Prozess-Stufe dieser Feedback-Eintrag betrifft (Quali-Call/
    # Shortlist/CV-Sent - siehe stage-edit-modal.tsx auf dem Frontend).
    # Nullable, weil bestehende Feedback-Eintraege vor dieser Erweiterung
    # keine Stufe gespeichert haben - NULL bedeutet "Stufe unbekannt/
    # historisch", kein Backfill fuer Altdaten (siehe Migration).
    stage: Mapped[SubmissionStatus | None] = mapped_column(
        Enum(SubmissionStatus, native_enum=False, length=40)
    )


class Interview(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "interviews"
    submission_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("candidate_submissions.id", ondelete="CASCADE"), index=True
    )
    scheduled_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    interview_type: Mapped[str] = mapped_column(String(120), nullable=False)
    location_or_link: Mapped[str | None] = mapped_column(String(500))
    participants: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    status: Mapped[InterviewStatus] = mapped_column(
        Enum(InterviewStatus, native_enum=False, length=32),
        default=InterviewStatus.SCHEDULED,
        nullable=False,
    )
    notes: Mapped[str | None] = mapped_column(Text)


class Offer(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "offers"
    submission_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("candidate_submissions.id", ondelete="CASCADE"), index=True
    )
    offered_salary: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    variable_compensation: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    start_date: Mapped[date | None] = mapped_column(Date)
    offer_status: Mapped[OfferStatus] = mapped_column(
        Enum(OfferStatus, native_enum=False, length=32),
        default=OfferStatus.RECEIVED,
        nullable=False,
    )
    notes: Mapped[str | None] = mapped_column(Text)


class Placement(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "placements"
    submission_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("candidate_submissions.id", ondelete="RESTRICT"),
        unique=True,
        index=True,
    )
    start_date: Mapped[date] = mapped_column(Date, nullable=False)
    final_salary: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    fee_percentage: Mapped[Decimal] = mapped_column(Numeric(5, 2), nullable=False)
    calculated_fee: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    guarantee_period_months: Mapped[int] = mapped_column(default=0, nullable=False)
    status: Mapped[PlacementStatus] = mapped_column(
        Enum(PlacementStatus, native_enum=False, length=32),
        default=PlacementStatus.PLANNED,
        nullable=False,
    )


class Fee(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "fees"
    placement_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("placements.id", ondelete="CASCADE"), index=True
    )
    amount_net: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    vat_rate: Mapped[Decimal] = mapped_column(Numeric(5, 2), nullable=False)
    amount_gross: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    invoice_status: Mapped[InvoiceStatus] = mapped_column(
        Enum(InvoiceStatus, native_enum=False, length=32),
        default=InvoiceStatus.DRAFT,
        nullable=False,
    )
    invoice_date: Mapped[date | None] = mapped_column(Date)
    payment_due_date: Mapped[date | None] = mapped_column(Date)
    paid_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class AuditLog(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "audit_logs"
    entity_type: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    entity_id: Mapped[uuid.UUID] = mapped_column(index=True)
    action: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    changed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    changed_by: Mapped[str | None] = mapped_column(String(240))
    old_values: Mapped[dict[str, object] | None] = mapped_column(JSON)
    new_values: Mapped[dict[str, object] | None] = mapped_column(JSON)
