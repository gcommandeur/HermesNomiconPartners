from sqlalchemy import Float, Index, String
from sqlalchemy.orm import Mapped, mapped_column

from cc_crm.models.base import Base, UUIDPrimaryKeyMixin


class PostalLocality(UUIDPrimaryKeyMixin, Base):
    """Statischer PLZ<->Ort-Referenzdatensatz fuer Deutschland (Phase 4b) -
    Basis fuer bidirektionales Ort/PLZ-Matching bei der Kanzleien-Suche
    (siehe repositories/clients.py::filtered()) UND (seit der PLZ-Koordinaten-
    Erweiterung) fuer echte, PLZ-genaue Umkreissuche-Koordinaten (siehe
    services/geo.py::candidate_coordinates/resolve_place_query) - vorher
    gab es hier nur Text-Matching, keine Koordinaten, und die Umkreissuche
    musste auf die viel groebere Stadt-/PLZ-Zonen-Naeherung
    (CITY_COORDINATES/PLZ_ZONE_COORDINATES) zurueckfallen.

    Zwei Datenquellen in DERSELBEN Tabelle (nicht dupliziert):
    - postal_code/locality/borough/suburb: openpotato/openplzapi.data
      (OpenStreetMap-Auswertung, ODbL-1.0 -
      https://github.com/openpotato/openplzapi.data), verdichtet auf
      eindeutige (PLZ, Ort, Stadtbezirk, Ortsteil)-Kombinationen durch
      scripts/import_postal_localities.py aus backend/data/reference/
      de_postal_codes.csv.
    - latitude/longitude: zauberware/postal-codes-json-xml-csv (Geonames-
      Daten, CC-BY-4.0 - https://github.com/zauberware/postal-codes-json-xml-csv),
      DE-Datensatz mit 23.297 Eintraegen (Stand 2026-07-31), aus
      backend/data/reference/de_postal_coordinates.csv ueber dieselbe
      postal_code-Spalte zugeordnet (bei mehreren Orten pro PLZ nach
      Moeglichkeit ueber den Ortsnamen gematcht, siehe import-Skript).
      Nullable, da nicht jede PLZ in der Koordinaten-Quelle vorkommt.

    Rein interne Nutzung (keine Weitergabe der Datenbank), daher keine
    Share-Alike-Pflicht bei der ODbL-Quelle - Attribution hier im Docstring
    sowie im Lade-Skript; die CC-BY-4.0-Quelle verlangt ohnehin nur
    Namensnennung, ebenfalls hier erfuellt."""

    __tablename__ = "postal_localities"
    __table_args__ = (
        Index("ix_postal_localities_postal_code", "postal_code"),
        Index("ix_postal_localities_locality", "locality"),
    )

    postal_code: Mapped[str] = mapped_column(String(5), nullable=False)
    locality: Mapped[str] = mapped_column(String(160), nullable=False)
    borough: Mapped[str | None] = mapped_column(String(160))
    suburb: Mapped[str | None] = mapped_column(String(160))
    latitude: Mapped[float | None] = mapped_column(Float)
    longitude: Mapped[float | None] = mapped_column(Float)
