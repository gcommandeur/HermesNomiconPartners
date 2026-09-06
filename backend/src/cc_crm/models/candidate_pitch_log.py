import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Text
from sqlalchemy.orm import Mapped, mapped_column

from cc_crm.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class CandidatePitchLog(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Ein geloggtes "Pitch/InMail" (Ansprache eines Kandidaten zu einer
    Vakanz/Kanzlei, BEVOR ein Quali Call stattfindet) - Konsolidierter
    Auftrag "Analytics/Prozess-Timeline: 7 Stufen", Nutzer-Entscheidung:
    Pitch wird bewusst NICHT als weitere SubmissionStatus-Kanban-Stufe
    gefuehrt (kein eigener Kanban-Status, keine Kanzlei-Bindung wie bei
    CV-Outs), sondern als eigenstaendiges, zaehlbares Ereignis direkt am
    Kandidaten - ueber die "+ Notiz"-Aktion in der Prozess-Timeline
    (candidate-process-log.tsx) geloggt, GENAU WIE die drei bestehenden
    fruehen Stufen (qualification_call/cv_in/cv_out), nur ohne begleitenden
    Statuswechsel einer CandidateSubmission. Ein Kandidat kann mehrere
    Pitch-Eintraege haben (z.B. mehrfach zu unterschiedlichen Zeitpunkten
    angesprochen) - Nutzer-Vorgabe: "es kann auch mehrmals da sein"."""

    __tablename__ = "candidate_pitch_logs"

    candidate_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("candidates.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    notes_text: Mapped[str | None] = mapped_column(Text)
    next_step: Mapped[str | None] = mapped_column(Text)
