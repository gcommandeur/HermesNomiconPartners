import uuid
from collections.abc import Sequence
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from cc_crm.models.client_company import ClientCompany

# Adressbezogene Felder, die beim Zusammenfuehren von Import-Zeilen fuer
# dieselbe (bereits bestehende) Kanzlei nur aufgefuellt werden, wenn sie am
# bestehenden Datensatz noch leer sind - nie ueberschrieben.
_MERGEABLE_ADDRESS_FIELDS = (
    "street",
    "postal_code",
    "city",
    "region",
    "email",
    "phone",
    "website",
)


class ClientGroupingService:
    """Kanzleigruppe (ClientCompany.kanzleigruppe) ist der bestehende
    Gruppierungsschluessel fuer Kanzleien mit mehreren Standorten - jeder
    Standort bleibt sein eigener ClientCompany-Datensatz. Dieser Service
    aggregiert nur zu Anzeige-/Merge-Zwecken, legt kein neues Konzept an."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def group_locations(
        self, kanzleigruppe: str, *, exclude_id: uuid.UUID | None = None
    ) -> Sequence[ClientCompany]:
        """Alle Standorte derselben Kanzleigruppe (fuer die Anzeige auf der
        Kanzlei-Detailseite, wenn mehr als ein Standort vorliegt)."""
        query = select(ClientCompany).where(ClientCompany.kanzleigruppe == kanzleigruppe)
        if exclude_id is not None:
            query = query.where(ClientCompany.id != exclude_id)
        return self.session.scalars(query).all()

    def find_existing_for_merge(self, name: str) -> ClientCompany | None:
        """Exakter Namenstreffer - Basis fuer den Import-Merge (Task 3):
        derselbe Standort, mehrfach importiert (z.B. aus zwei Vertragsdateien)."""
        return self.session.scalar(select(ClientCompany).where(ClientCompany.name == name))

    def merge_address_fields(
        self, existing: ClientCompany, incoming: dict[str, Any]
    ) -> dict[str, Any]:
        """Liefert die Felder, die auf `existing` nachgetragen werden sollen:
        nur Adressfelder, die am bestehenden Datensatz noch leer sind UND im
        importierten Datensatz einen Wert haben. Ueberschreibt nie vorhandene
        Werte - so gehen bei einem zweiten Import derselben Kanzleigruppe
        keine bereits erfassten Adressdaten verloren."""
        updates: dict[str, Any] = {}
        for field in _MERGEABLE_ADDRESS_FIELDS:
            current_value = getattr(existing, field, None)
            incoming_value = incoming.get(field)
            if not current_value and incoming_value:
                updates[field] = incoming_value
        return updates
