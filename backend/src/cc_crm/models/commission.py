# NOMICON: Provisionsmodell - nur in der Nomicon-Kopie, nur fuer Admins.
"""Zuordnung Mitarbeiter -> Rang des Provisionsmodells. Das Modell selbst (Saetze, Schwellen,
Gehaelter) steht als JSON in `app_settings` (services/commission_settings.py); hier steht nur, wer
welchen Rang hat."""

import uuid
from datetime import date

from sqlalchemy import Date, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from cc_crm.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class CommissionUserRank(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "commission_user_ranks"

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, unique=True
    )
    rank_key: Mapped[str] = mapped_column(String(40), nullable=False)
    effective_from: Mapped[date | None] = mapped_column(Date)
    updated_by: Mapped[str | None] = mapped_column(String(320))
