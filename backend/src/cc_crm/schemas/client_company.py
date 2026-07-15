from datetime import date
from decimal import Decimal

from pydantic import BaseModel, EmailStr, Field

from cc_crm.models.enums import ClientStatus, HonorarStufe
from cc_crm.schemas.base import EntityRead


class ClientCompanyBase(BaseModel):
    name: str = Field(min_length=1, max_length=240)
    # Marken-/Netzwerkname für Kanzleien mit mehreren Standorten (z.B. "ECOVIS").
    kanzleigruppe: str | None = Field(default=None, max_length=160)
    status: ClientStatus = ClientStatus.PROSPECT
    website: str | None = Field(default=None, max_length=500)
    # str statt EmailStr hier: der Kanzlei-Domain-Import (siehe
    # scripts/import_kanzlei_domains_20260713.py) hat bei einer Kanzlei eine
    # im strengen RFC-Sinn ungueltige Adresse gespeichert (".beyer@
    # steuerberater-eb.de" - Punkt direkt nach dem "@"-Trenner nicht erlaubt),
    # weil sie so aus der Quelle (Rohe_Lokalteil) kam - dieselbe Klasse Bug
    # wie zuvor bei ContactPersonRead (siehe dort). Beim AUSLESEN darf das
    # nicht an einer Validierung scheitern - das riss zuvor JEDE Pagination-
    # Seite mit runter, auf der dieser eine Datensatz lag (503/500 fuer
    # limit=500&offset=500, waehrend offset=0 funktionierte). Strenge
    # Email-Validierung bleibt bei Create/Update bestehen.
    email: str | None = Field(default=None, max_length=255)
    phone: str | None = Field(default=None, max_length=80)
    street: str | None = Field(default=None, max_length=240)
    postal_code: str | None = Field(default=None, max_length=20)
    city: str | None = Field(default=None, max_length=160)
    region: str | None = Field(default=None, max_length=160)
    company_size: str | None = Field(default=None, max_length=120)
    focus: str | None = Field(default=None, max_length=240)
    linkedin_url: str | None = Field(default=None, max_length=500)
    last_contact_at: date | None = None
    next_follow_up_at: date | None = None
    terms_status: str = Field(default="not_sent", max_length=40)
    fee_percentage: Decimal = Field(default=Decimal("27.00"), gt=0, le=100)
    honorar_stufe: HonorarStufe = HonorarStufe.STANDARD
    nachlass_begruendung: str | None = None
    agb_version: str | None = Field(default=None, max_length=40)
    refund_terms: str = "50 % vor Antritt; 50 % im ersten Monat; 25 % im zweiten Monat"
    guarantee_period_months: int = Field(default=6, ge=0)
    payment_terms_days: int = Field(default=14, ge=0)
    special_terms: str | None = None
    commercial_notes: str | None = None
    notes: str | None = None


class ClientCompanyCreate(ClientCompanyBase):
    # Ueber das UI-Formular angelegte Kanzleien sollen weiterhin eine
    # gueltige E-Mail verlangen - nur der CSV-Import (der direkt ueber das
    # Repository/die Session geht, nicht ueber dieses Schema) darf davon
    # abweichende Adressen speichern.
    email: EmailStr | None = None


class ClientCompanyUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=240)
    kanzleigruppe: str | None = Field(default=None, max_length=160)
    status: ClientStatus | None = None
    website: str | None = Field(default=None, max_length=500)
    email: EmailStr | None = None
    phone: str | None = Field(default=None, max_length=80)
    street: str | None = Field(default=None, max_length=240)
    postal_code: str | None = Field(default=None, max_length=20)
    city: str | None = Field(default=None, max_length=160)
    region: str | None = Field(default=None, max_length=160)
    company_size: str | None = Field(default=None, max_length=120)
    focus: str | None = Field(default=None, max_length=240)
    linkedin_url: str | None = Field(default=None, max_length=500)
    last_contact_at: date | None = None
    next_follow_up_at: date | None = None
    terms_status: str | None = Field(default=None, max_length=40)
    fee_percentage: Decimal | None = Field(default=None, gt=0, le=100)
    honorar_stufe: HonorarStufe | None = None
    nachlass_begruendung: str | None = None
    agb_version: str | None = Field(default=None, max_length=40)
    refund_terms: str | None = None
    guarantee_period_months: int | None = Field(default=None, ge=0)
    payment_terms_days: int | None = Field(default=None, ge=0)
    special_terms: str | None = None
    commercial_notes: str | None = None
    notes: str | None = None


class ClientCompanyRead(ClientCompanyBase, EntityRead):
    pass


class ClientDuplicateCandidate(BaseModel):
    """Ein bestehender Kanzlei-Eintrag mit ähnlichem Namen - Warnhinweis vor
    dem Anlegen, kein hartes Duplikat-Verbot (mehrere Standorte derselben
    Marke sind ausdrücklich erlaubt und gewollt)."""

    id: str
    name: str
    kanzleigruppe: str | None
    city: str | None
    postal_code: str | None
    similarity: float
    same_location: bool
