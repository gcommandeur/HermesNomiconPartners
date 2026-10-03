from datetime import datetime
from typing import Any

from sqlalchemy import JSON, DateTime, Index, Integer, LargeBinary, String, Text, func, text
from sqlalchemy.orm import Mapped, mapped_column

from cc_crm.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class BackgroundJob(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Eintrag der Job-Warteschlange (services/job_queue.py).

    Bewusst eine eigene kleine Tabelle statt Redis/Bibliothek: ein Job
    ueberlebt Neustarts, wird bei Fehlern mit wachsendem Abstand wiederholt
    und ist fuer Admins sichtbar. `status`: queued | running | done | failed
    (String wie bei den anderen Statusfeldern dieses Projekts, keine
    DB-Enum). Ein abgestuerzter Worker laesst `locked_until` ablaufen, danach
    nimmt ein anderer Worker den Job wieder auf. `payload` enthaelt nur IDs
    bzw. technische Parameter; `payload_blob` nur, wenn ein Job Bytes braucht
    (gescanntes CV) - wird nach Abschluss geleert.
    """

    __tablename__ = "background_jobs"
    __table_args__ = (Index("ix_background_jobs_status_run_after", "status", "run_after"),)

    kind: Mapped[str] = mapped_column(String(60), nullable=False, index=True)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    payload_blob: Mapped[bytes | None] = mapped_column(LargeBinary)
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="queued", server_default=text("'queued'")
    )
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    max_attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=3)
    run_after: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    locked_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_error: Mapped[str | None] = mapped_column(Text)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
