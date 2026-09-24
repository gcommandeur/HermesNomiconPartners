import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from cc_crm.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin

TRUSTED_DEVICE_LIFETIME_DAYS = 14


class TrustedDevice(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """"Dieses Geraet merken" fuer den 2FA-Login (services/auth.py) -
    ausgestellt nach einer erfolgreichen Code-Verifikation, umgeht den
    2FA-Schritt fuer TRUSTED_DEVICE_LIFETIME_DAYS auf demselben Browser.

    Gleiches Muster wie AuthSession/ApiKey (models/auth.py, models/
    api_key.py): ein zufaelliges Token im httpOnly-Cookie des Browsers,
    hier gehasht gespeichert - bewusst NICHT ein selbststaendig
    (JWT-artig) signiertes Cookie, damit ein einzelnes Geraet gezielt
    entzogen werden kann (z.B. verlorenes Geraet), ohne den kompletten
    Signierschluessel zu rotieren und damit ALLE vertrauten Geraete auf
    einmal abzumelden."""

    __tablename__ = "trusted_devices"

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    token_hash: Mapped[str] = mapped_column(String(128), nullable=False, unique=True, index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
