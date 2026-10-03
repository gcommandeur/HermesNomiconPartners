import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, Index, String, Uuid, event, func, insert
from sqlalchemy.engine import Connection
from sqlalchemy.orm import Mapped, Mapper, mapped_column

from cc_crm.models.base import Base, UUIDPrimaryKeyMixin
from cc_crm.models.recruiting import AuditLog


class EventOutbox(UUIDPrimaryKeyMixin, Base):
    """Ereignis-Warteschlange (Outbox). Jeder Audit-Log-Eintrag erzeugt in
    DERSELBEN Transaktion eine Zeile hier (siehe Listener unten) - es gibt
    genau einen Weg, Ereignisse zu erzeugen, der nicht vergessen werden kann.
    Ein Dispatcher (services/webhooks.py) verteilt sie an Webhooks und setzt
    `dispatched_at`. Enthaelt NUR IDs und die Ereignisart, keine Personendaten.
    """

    __tablename__ = "event_outbox"
    __table_args__ = (Index("ix_event_outbox_dispatched_at", "dispatched_at"),)

    event_type: Mapped[str] = mapped_column(String(170), nullable=False)
    entity_type: Mapped[str] = mapped_column(String(80), nullable=False)
    entity_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    audit_log_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    dispatched_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


@event.listens_for(AuditLog, "after_insert")
def _audit_entry_to_outbox(_mapper: Mapper[Any], connection: Connection, target: AuditLog) -> None:
    connection.execute(
        insert(EventOutbox).values(
            event_type=f"{target.entity_type}.{target.action}"[:170],
            entity_type=target.entity_type,
            entity_id=target.entity_id,
            audit_log_id=target.id,
        )
    )
