from datetime import datetime

from sqlalchemy import Boolean, DateTime, Enum, Integer, func
from sqlalchemy.orm import Mapped, mapped_column

from cc_crm.models.base import Base, UUIDPrimaryKeyMixin
from cc_crm.models.enums import SourcingRunStatus, SourcingSourceType


class SourcingRun(UUIDPrimaryKeyMixin, Base):
    """Laufzeit-Tracking fuer den Hintergrund-Sourcing-Lauf "alle Kanzleien
    scannen" (services/sourcing.py:scan_team_pages_in_background). Bewusst
    DB-gestuetzt statt eines In-Memory-Flags: der Hintergrund-Lauf und das
    Stop-Kommando laufen in unterschiedlichen HTTP-Requests/Sessions, und ein
    In-Memory-Flag wuerde einen Prozess-Neustart (z.B. Deploy) nicht
    ueberleben - der Lauf wuerde dann weiterlaufen, ohne stoppbar zu sein."""

    __tablename__ = "sourcing_runs"

    source_type: Mapped[SourcingSourceType] = mapped_column(
        Enum(SourcingSourceType, native_enum=False, length=40), nullable=False
    )
    status: Mapped[SourcingRunStatus] = mapped_column(
        Enum(SourcingRunStatus, native_enum=False, length=20),
        default=SourcingRunStatus.RUNNING,
        nullable=False,
        index=True,
    )
    total: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    processed: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    leads_created: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    # Vom Stop-Endpunkt gesetzt; der Hintergrund-Lauf prueft dieses Feld nach
    # jeder abgeschlossenen Kanzlei und bricht dann ab (ein bereits
    # laufender externer/LLM-Request wird nicht mitten drin abgebrochen).
    stop_requested: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
