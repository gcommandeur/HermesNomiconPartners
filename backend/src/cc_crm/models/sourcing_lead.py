import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import JSON, DateTime, Enum, ForeignKey, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from cc_crm.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from cc_crm.models.enums import SourcingLeadStatus, SourcingSourceType


class SourcingLead(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Vorschlags-Ebene des Sourcing-Agents: automatisiert aus oeffentlichen
    Berufsregistern/Kanzlei-Team-Seiten gefundene Personen. Bewusst getrennt
    vom produktiven Kandidatenbestand - erst nach expliziter menschlicher
    Bestaetigung (approve) entsteht ein echter Candidate-Datensatz
    (Datenqualitaet + Datenschutz, siehe SourcingLeadStatus-Docstring)."""

    __tablename__ = "sourcing_leads"

    source_type: Mapped[SourcingSourceType] = mapped_column(
        Enum(SourcingSourceType, native_enum=False, length=40), nullable=False, index=True
    )
    source_url: Mapped[str | None] = mapped_column(Text)
    first_name: Mapped[str] = mapped_column(String(120), nullable=False)
    last_name: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    # Kanzlei/Gesellschaft laut Quelle (Freitext, nicht zwingend im CRM bekannt).
    current_employer: Mapped[str | None] = mapped_column(String(240))
    city: Mapped[str | None] = mapped_column(String(160))
    postal_code: Mapped[str | None] = mapped_column(String(20), index=True)
    # Alles sonst in der Quelle Gefundene (Kammer, Bestellungsdatum,
    # Fachgebiet, Titel, ...) - bewusst schemalos, da jede Quelle andere
    # Zusatzfelder liefert.
    raw_data: Mapped[dict[str, Any] | None] = mapped_column(JSON)

    # Falls die gefundene Kanzlei einer bestehenden Kanzlei im CRM zugeordnet
    # werden konnte (bei Team-Seiten-Scrapes immer gesetzt, da von der
    # Kanzlei aus gestartet wird).
    matched_client_company_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("client_companies.id", ondelete="SET NULL")
    )

    status: Mapped[SourcingLeadStatus] = mapped_column(
        Enum(SourcingLeadStatus, native_enum=False, length=32),
        default=SourcingLeadStatus.PENDING,
        nullable=False,
        index=True,
    )
    # Gesetzt, wenn der Fuzzy-Namensabgleich beim Anlegen einen bestehenden
    # Kandidaten nahegelegt hat (status == POSSIBLE_DUPLICATE).
    duplicate_of_candidate_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("candidates.id", ondelete="SET NULL")
    )
    # Gesetzt, sobald aus dem Lead per approve ein echter Kandidat wurde.
    created_candidate_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("candidates.id", ondelete="SET NULL")
    )

    found_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    reviewed_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
