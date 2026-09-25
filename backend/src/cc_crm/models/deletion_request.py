"""Nachverfolgung von Löschanfragen (Art. 17 DSGVO) - Punkt 3 des Auftrags
"5 Hoch-Punkte umsetzen". Bewusst NUR eine Nachverfolgung UM die bestehende
Anonymisierung (CandidateService.anonymize) herum, keine eigene
Löschlogik - siehe services/deletion_requests.py.
"""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from cc_crm.models.base import Base, UUIDPrimaryKeyMixin


class DeletionRequest(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "deletion_requests"

    candidate_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("candidates.id", ondelete="CASCADE"), nullable=False, index=True
    )
    requested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    # Freitext (z.B. "email", "telefon", "sonstiges") statt festem Vokabular -
    # Nutzer-Vorgabe: "freies Textfeld reicht".
    requested_via: Mapped[str] = mapped_column(String(240), nullable=False)
    # requested_at + 30 Tage (DSGVO-Standardfrist), von
    # DeletionRequestService.create() beim Anlegen berechnet - kein
    # DB-Default, weil er von requested_at zum Anlagezeitpunkt abhaengt.
    deadline: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
