import uuid
from decimal import Decimal

from sqlalchemy import JSON, Enum, ForeignKey, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from cc_crm.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from cc_crm.models.enums import JobStatus, TaskPriority


class JobMandate(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "job_mandates"

    client_company_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("client_companies.id", ondelete="RESTRICT"),
        index=True,
    )
    title: Mapped[str] = mapped_column(String(240), nullable=False, index=True)
    status: Mapped[JobStatus] = mapped_column(
        Enum(JobStatus, native_enum=False, length=32),
        default=JobStatus.DRAFT,
        nullable=False,
        index=True,
    )
    priority: Mapped[TaskPriority] = mapped_column(
        Enum(TaskPriority, native_enum=False, length=16),
        default=TaskPriority.NORMAL,
        nullable=False,
        index=True,
    )
    location: Mapped[str | None] = mapped_column(String(240))
    search_radius_km: Mapped[int] = mapped_column(default=30, nullable=False)
    work_model: Mapped[str | None] = mapped_column(String(120))
    qualifications: Mapped[str | None] = mapped_column(Text)
    experience: Mapped[str | None] = mapped_column(Text)
    description: Mapped[str | None] = mapped_column(Text)
    must_have: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    nice_to_have: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    salary_min: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    salary_max: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    fee_percentage: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))
