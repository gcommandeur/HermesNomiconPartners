from typing import Any

from sqlalchemy import JSON, Boolean, Integer, String, UniqueConstraint, text
from sqlalchemy.orm import Mapped, mapped_column

from cc_crm.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin

CUSTOM_FIELD_ENTITIES = ("candidate", "client", "contact")
CUSTOM_FIELD_TYPES = ("text", "number", "date", "boolean", "select")


class CustomFieldDefinition(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Vom Admin definiertes Zusatzfeld fuer Kandidaten, Kanzleien oder
    Kontakte. Die Werte liegen in der JSON-Spalte `custom_fields` des jeweiligen
    Objekts (Schluessel -> Wert), NICHT in echten Spalten - ein neues Feld
    braucht so weder Migration noch ALTER TABLE. Felder werden deaktiviert statt
    geloescht, damit gespeicherte Werte nicht verwaisen.
    `entity_type`: candidate | client | contact.
    `field_type`: text | number | date | boolean | select (`options` nur fuer select).
    """

    __tablename__ = "custom_field_definitions"
    __table_args__ = (UniqueConstraint("entity_type", "key", name="uq_custom_field_entity_key"),)

    entity_type: Mapped[str] = mapped_column(String(20), nullable=False)
    key: Mapped[str] = mapped_column(String(60), nullable=False)
    label: Mapped[str] = mapped_column(String(120), nullable=False)
    field_type: Mapped[str] = mapped_column(String(20), nullable=False)
    options: Mapped[list[Any]] = mapped_column(JSON, nullable=False, default=list)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default=text("true")
    )
