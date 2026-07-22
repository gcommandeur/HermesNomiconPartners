import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from cc_crm.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class ApiKey(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Long-lived credential for agents/integrations (Bullhorn sync, future AI
    agents, webhooks) that authenticate as a service account instead of a
    human login session. See docs/API_KEYS.md.
    """

    __tablename__ = "api_keys"

    name: Mapped[str] = mapped_column(String(160), nullable=False)
    key_hash: Mapped[str] = mapped_column(String(128), nullable=False, unique=True, index=True)
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # Optionales Ablaufdatum - NULL bedeutet "laeuft nie ab" (unveraendertes
    # Verhalten fuer bestehende Schluessel ohne Backfill). Wird beim
    # Erzeugen optional gesetzt (siehe ApiKeyService.create) und bei jeder
    # Auth-Pruefung wie ein widerrufener Key behandelt, sobald er
    # abgelaufen ist (siehe ApiKeyService.user_for_key).
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
