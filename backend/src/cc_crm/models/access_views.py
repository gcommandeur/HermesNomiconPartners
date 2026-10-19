# NOMICON: Ansichten (Direct, Ueberlassung, Gesamt) - nur in der Nomicon-Kopie.
"""Freischaltung der Ansichten je Mitarbeiter. Bewusst in eigenen Tabellen statt als Spalten an
`users` (Hermes-Tabelle). Die Rolle (member/team_lead/admin) regelt weiter, WELCHE Datensaetze
man sieht; die Ansicht regelt, WELCHE Module."""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from cc_crm.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class UserViewAccess(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Eine freigeschaltete Ansicht eines Mitarbeiters ("direct", "staffing", "management")."""

    __tablename__ = "user_view_access"
    __table_args__ = (UniqueConstraint("user_id", "view"),)

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    view: Mapped[str] = mapped_column(String(20), nullable=False)
    granted_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
    granted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class UserViewSettings(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Startansicht je Nutzer (1:1). Wird auch beim Umschalten im Kopf der Oberflaeche gemerkt."""

    __tablename__ = "user_view_settings"

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, unique=True
    )
    default_view: Mapped[str | None] = mapped_column(String(20))
