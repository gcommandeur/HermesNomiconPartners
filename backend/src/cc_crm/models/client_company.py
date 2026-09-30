import uuid
from datetime import date
from decimal import Decimal

from sqlalchemy import Boolean, Date, Enum, ForeignKey, Integer, Numeric, String, Text, false
from sqlalchemy.orm import Mapped, mapped_column

from cc_crm.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from cc_crm.models.enums import ClientStatus, HonorarStufe


class ClientCompany(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "client_companies"

    name: Mapped[str] = mapped_column(String(240), nullable=False, unique=True, index=True)
    # Marken-/Netzwerkname für Kanzleien mit mehreren Standorten (z.B. "ECOVIS",
    # "Afileon") - jeder Standort bleibt ein eigener ClientCompany-Datensatz mit
    # eigener Anschrift/eigenen Kontakten, aber teilt sich diesen Gruppennamen,
    # damit man sie zusammen filtern/finden kann.
    kanzleigruppe: Mapped[str | None] = mapped_column(String(160), index=True)
    status: Mapped[ClientStatus] = mapped_column(
        Enum(ClientStatus, native_enum=False, length=32),
        # PROSPECT (grau/"noch keine Kundenbeziehung") ist der ehrliche Default
        # für einen frisch angelegten Datensatz ohne bisherigen Kontakt - siehe
        # ClientStatus-Docstring für die vollständige Ampel-Logik.
        default=ClientStatus.PROSPECT,
        nullable=False,
        index=True,
    )
    website: Mapped[str | None] = mapped_column(String(500))
    email: Mapped[str | None] = mapped_column(String(320))
    phone: Mapped[str | None] = mapped_column(String(80))
    street: Mapped[str | None] = mapped_column(String(240))
    postal_code: Mapped[str | None] = mapped_column(String(20), index=True)
    city: Mapped[str | None] = mapped_column(String(160))
    region: Mapped[str | None] = mapped_column(String(160))
    company_size: Mapped[str | None] = mapped_column(String(120))
    focus: Mapped[str | None] = mapped_column(String(240))
    linkedin_url: Mapped[str | None] = mapped_column(String(500))
    last_contact_at: Mapped[date | None] = mapped_column(Date)
    next_follow_up_at: Mapped[date | None] = mapped_column(Date)
    terms_status: Mapped[str] = mapped_column(String(40), default="not_sent", nullable=False)
    fee_percentage: Mapped[Decimal] = mapped_column(
        Numeric(5, 2), default=Decimal("27.00"), nullable=False
    )
    honorar_stufe: Mapped[HonorarStufe] = mapped_column(
        Enum(HonorarStufe, native_enum=False, length=32),
        default=HonorarStufe.STANDARD,
        nullable=False,
    )
    nachlass_begruendung: Mapped[str | None] = mapped_column(Text)
    agb_version: Mapped[str | None] = mapped_column(String(40))
    refund_terms: Mapped[str] = mapped_column(
        Text,
        default="50 % vor Antritt; 50 % im ersten Monat; 25 % im zweiten Monat",
        nullable=False,
    )
    guarantee_period_months: Mapped[int] = mapped_column(Integer, default=6, nullable=False)
    payment_terms_days: Mapped[int] = mapped_column(Integer, default=14, nullable=False)
    special_terms: Mapped[str | None] = mapped_column(Text)
    # Von einem Nicht-Admin neu angelegt, Freigabe durch die GF steht aus
    # (siehe models/approval_request.py).
    approval_pending: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default=false(), nullable=False
    )
    commercial_notes: Mapped[str | None] = mapped_column(Text)
    notes: Mapped[str | None] = mapped_column(Text)

    # Zustaendiger Mitarbeiter (Komfort-Filter "Meine Kanzleien", KEINE
    # Sichtbarkeitsgrenze) - siehe models/candidate.py::owner_user_id fuer
    # die vollstaendige Begruendung.
    owner_user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), index=True
    )
