import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import JSON, DateTime, ForeignKey, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from cc_crm.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class AiProposal(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Vorschlag, den Claude (ueber die MCP-Schnittstelle) gemacht hat.

    Grundregel: Claude darf vorbereiten, aber nichts anlegen oder senden - eine
    Notiz, Aufgabe oder Mail entsteht erst, wenn ein Mensch den Vorschlag in
    Hermes freigibt (services/ai_proposals.py). Der Klick zur Kommunikation mit
    Kunde oder Kandidat bleibt immer beim Menschen.

    `kind`: note | task | mail_draft. `status`: pending | approved | rejected.
    `target_type`: candidate | client | contact (Bezugsobjekt, bei mail_draft der
    Empfaenger). `payload` enthaelt nur den vorgeschlagenen Text (siehe
    schemas/ai_proposal.py)."""

    __tablename__ = "ai_proposals"

    kind: Mapped[str] = mapped_column(String(20), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending", index=True)
    target_type: Mapped[str | None] = mapped_column(String(20))
    target_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True))
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    # Besitzer des API-Schluessels, ueber den Claude den Vorschlag angelegt hat.
    created_by_user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    decided_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    decision_note: Mapped[str | None] = mapped_column(Text)
    # Was nach der Freigabe entstanden ist (Notiz / Aufgabe).
    result_entity_type: Mapped[str | None] = mapped_column(String(20))
    result_entity_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True))
