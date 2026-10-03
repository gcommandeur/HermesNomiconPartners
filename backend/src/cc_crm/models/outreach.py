import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from cc_crm.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin

# Kanaele eines Sequenz-Schritts. Nur "email" wird automatisch versendet; alle
# anderen erzeugen einen Task fuer den zustaendigen Nutzer (es gibt bewusst
# keine LinkedIn-/Telefon-Automatisierung). Nur anwendungsseitig validiert
# (schemas/outreach.py), kein DB-CHECK - wie User.role.
CHANNELS = ("email", "linkedin", "phone", "other")

# Einschreibungs-Status: "active" (laeuft), "paused_reply" (Antwort
# eingegangen, automatisch pausiert), "completed" (letzter Schritt erledigt),
# "stopped" (manuell oder wegen eines nicht ausfuehrbaren Schritts beendet,
# Grund in stopped_reason).
ENROLLMENT_STATUSES = ("active", "paused_reply", "completed", "stopped")


class OutreachSequence(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Mehrstufige Kontaktfolge ("Sequenz"). Die Schritte stehen in einer
    eigenen Kind-Tabelle (OutreachSequenceStep) statt in einer JSON-Spalte:
    passt zum Projektstil (z.B. Candidate/Activity), erlaubt FK/Unique/
    Abfragen pro Schritt und eine saubere Validierung je Zeile."""

    __tablename__ = "outreach_sequences"

    name: Mapped[str] = mapped_column(String(160), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class OutreachSequenceStep(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "outreach_sequence_steps"
    __table_args__ = (UniqueConstraint("sequence_id", "step_index"),)

    sequence_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("outreach_sequences.id", ondelete="CASCADE"), index=True
    )
    step_index: Mapped[int] = mapped_column(Integer, nullable=False)
    # Tage nach dem Start der Einschreibung, an denen der Schritt faellig wird.
    day_offset: Mapped[int] = mapped_column(Integer, nullable=False)
    channel: Mapped[str] = mapped_column(String(20), nullable=False)
    # Bei "email" der Betreff, bei allen anderen Kanaelen der Task-Titel.
    subject: Mapped[str] = mapped_column(String(240), nullable=False)
    # Bei "email" der Text, sonst die Beschreibung/der Textvorschlag im Task.
    body_template: Mapped[str | None] = mapped_column(Text)


class SequenceEnrollment(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "sequence_enrollments"
    __table_args__ = (
        # Pro Sequenz und Kandidat hoechstens EINE laufende Einschreibung
        # (Mehrfacheinschreibung verhindern); beendete duerfen sich
        # wiederholen. Partieller Unique-Index, gilt auf SQLite und Postgres.
        Index(
            "uq_sequence_enrollments_active",
            "sequence_id",
            "candidate_id",
            unique=True,
            sqlite_where=text("status = 'active'"),
            postgresql_where=text("status = 'active'"),
        ),
    )

    sequence_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("outreach_sequences.id", ondelete="CASCADE"), index=True
    )
    candidate_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("candidates.id", ondelete="CASCADE"), index=True
    )
    # Zustaendiger Nutzer: Absender der Mails, Empfaenger der Tasks.
    owner_user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), index=True
    )
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    current_step_index: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    # Zeitpunkt des zuletzt ausgefuehrten Schritts - hoechstens ein Schritt
    # pro Kalendertag und Einschreibung (Idempotenz bei mehrfachem Tageslauf).
    last_step_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String(20), default="active", nullable=False, index=True)
    stopped_reason: Mapped[str | None] = mapped_column(String(240))
