import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import JSON, DateTime, Enum, ForeignKey, Text
from sqlalchemy.orm import Mapped, mapped_column

from cc_crm.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from cc_crm.models.enums import CvExtractionJobStatus


class CvExtractionJob(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Hintergrundjob fuer die CV-Auswertung gescannter PDFs
    (services/cv_extraction_jobs.py). Die mehrseitige Vision-Auswertung dauert
    laenger als das Gateway-Timeout von /candidates/cv-preview erlaubt - die
    Vorschau legt deshalb einen Job an und antwortet sofort mit "processing",
    der Client holt das Ergebnis per GET /candidates/cv-preview/{job_id} ab.
    DB-gestuetzt statt In-Memory (gleiche Begruendung wie SourcingRun): Start
    und Abruf laufen in verschiedenen Requests, und ein Deploy-Neustart darf
    den Status nicht spurlos verlieren. `result` enthaelt personenbezogene
    Kandidatendaten und wird nach 24 h wieder geloescht."""

    __tablename__ = "cv_extraction_jobs"

    owner_user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    status: Mapped[CvExtractionJobStatus] = mapped_column(
        Enum(CvExtractionJobStatus, native_enum=False, length=20),
        default=CvExtractionJobStatus.PROCESSING,
        nullable=False,
        index=True,
    )
    result: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    error: Mapped[str | None] = mapped_column(Text)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
