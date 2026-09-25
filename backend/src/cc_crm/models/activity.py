import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from cc_crm.models.base import Base, UUIDPrimaryKeyMixin


class Activity(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "activities"

    candidate_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("candidates.id", ondelete="CASCADE"),
        index=True,
    )
    client_company_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("client_companies.id", ondelete="CASCADE"),
        index=True,
    )
    candidate_submission_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("candidate_submissions.id", ondelete="CASCADE"),
        index=True,
    )
    # Wer die Aktivitaet ausgeloest hat (Punkt 2 des Auftrags "5 Hoch-Punkte
    # umsetzen": Audit-Trail fuer Mail-Versand - "wer hat wann welches Profil
    # an wen geschickt") - nullable, weil nicht jede Activity-Erzeugung einen
    # eingeloggten Nutzer hat (z.B. eingehende Mails aus dem Mail-Sync).
    sent_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), index=True
    )
    activity_type: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    subject: Mapped[str] = mapped_column(String(240), nullable=False)
    details: Mapped[str | None] = mapped_column(Text)
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
        index=True,
    )
