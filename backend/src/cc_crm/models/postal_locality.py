from sqlalchemy import Index, String
from sqlalchemy.orm import Mapped, mapped_column

from cc_crm.models.base import Base, UUIDPrimaryKeyMixin


class PostalLocality(UUIDPrimaryKeyMixin, Base):
    """Statischer PLZ<->Ort-Referenzdatensatz fuer Deutschland (Phase 4b) -
    Basis fuer bidirektionales Ort/PLZ-Matching bei der Kanzleien-Suche
    (siehe repositories/clients.py::filtered()), NICHT zu verwechseln mit
    services/geo.py::CITY_COORDINATES/PLZ_ZONE_COORDINATES (nur fuer die
    Kartenanzeige, kein Text-Matching).

    Quelle: openpotato/openplzapi.data (OpenStreetMap-Auswertung, ODbL-1.0 -
    https://github.com/openpotato/openplzapi.data), verdichtet auf eindeutige
    (PLZ, Ort, Stadtbezirk, Ortsteil)-Kombinationen durch
    scripts/import_postal_localities.py aus backend/data/reference/
    de_postal_codes.csv. Rein interne Nutzung (keine Weitergabe der
    Datenbank), daher keine Share-Alike-Pflicht - Attribution hier im
    Docstring sowie im Lade-Skript."""

    __tablename__ = "postal_localities"
    __table_args__ = (
        Index("ix_postal_localities_postal_code", "postal_code"),
        Index("ix_postal_localities_locality", "locality"),
    )

    postal_code: Mapped[str] = mapped_column(String(5), nullable=False)
    locality: Mapped[str] = mapped_column(String(160), nullable=False)
    borough: Mapped[str | None] = mapped_column(String(160))
    suburb: Mapped[str | None] = mapped_column(String(160))
