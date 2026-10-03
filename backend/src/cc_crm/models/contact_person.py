import uuid
from typing import Any

from sqlalchemy import JSON, ForeignKey, String, text
from sqlalchemy.orm import Mapped, mapped_column

from cc_crm.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class ContactPerson(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "contact_persons"

    client_company_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("client_companies.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    first_name: Mapped[str] = mapped_column(String(120), nullable=False)
    last_name: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    role_title: Mapped[str | None] = mapped_column(String(180))
    email: Mapped[str | None] = mapped_column(String(320), index=True)
    phone: Mapped[str | None] = mapped_column(String(80))
    is_primary: Mapped[bool] = mapped_column(default=False, nullable=False)

    # Eigene Felder (Admin-definiert, siehe models/custom_field.py). Bewusst plain JSON
    # ohne GIN-Index (wie rollen): Filter ueber JSON-Pfad, portabel fuer SQLite/Postgres.
    custom_fields: Mapped[dict[str, Any]] = mapped_column(
        JSON, nullable=False, default=dict, server_default=text("'{}'")
    )
