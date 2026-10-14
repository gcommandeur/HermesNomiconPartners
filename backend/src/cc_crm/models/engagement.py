# NOMICON: gemeinsamer Kandidatenstatus - nur in der Nomicon-Kopie.
"""Praeferenz des Kandidaten, fuer welchen Kanal er offen ist. Eigene Tabelle statt Spalten an
`candidates` (Hermes-Tabelle). Der eigentliche Status ("wo ist der Kandidat im Austausch") wird aus
Prozessen und Einsaetzen abgeleitet, nichts davon doppelt gespeichert."""

import uuid

from sqlalchemy import ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from cc_crm.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class CandidateEngagementPrefs(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "candidate_engagement_prefs"

    candidate_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("candidates.id", ondelete="CASCADE"), nullable=False, unique=True
    )
    # "yes" | "no" | "unknown" (Standard: nicht geklaert)
    open_for_direct: Mapped[str] = mapped_column(String(10), nullable=False, default="unknown")
    open_for_staffing: Mapped[str] = mapped_column(String(10), nullable=False, default="unknown")
    updated_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
