from sqlalchemy import Float, String
from sqlalchemy.orm import Mapped, mapped_column

from cc_crm.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class RegionModifier(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Konfigurierbare Lookup-Tabelle PLZ-Praefix -> Markt-Fit-Modifikator
    (-0.5 bis +0.5) fuer das Closing-Probability-Modell - bewusst keine
    hartcodierte Regionsliste, sondern per API/Admin pflegbar."""

    __tablename__ = "region_modifiers"

    plz_prefix: Mapped[str] = mapped_column(String(10), nullable=False, unique=True, index=True)
    label: Mapped[str | None] = mapped_column(String(160))
    modifier: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
