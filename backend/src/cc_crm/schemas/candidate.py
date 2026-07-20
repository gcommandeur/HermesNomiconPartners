import uuid
from datetime import date, datetime

from pydantic import BaseModel, EmailStr, Field

from cc_crm.models.enums import Anrede, CandidateStatus
from cc_crm.schemas.base import EntityRead


class BeruflicheStation(BaseModel):
    kanzleityp: str = Field(min_length=1, max_length=160)
    kanzleigroesse: str = Field(min_length=1, max_length=160)
    dauer_jahre: float = Field(ge=0)


class CandidateBase(BaseModel):
    candidate_number: str | None = Field(default=None, max_length=40)
    first_name: str = Field(min_length=1, max_length=120)
    last_name: str = Field(min_length=1, max_length=120)
    email: EmailStr | None = None
    phone: str | None = Field(default=None, max_length=80)
    job_title: str | None = Field(default=None, max_length=180)
    qualification: str | None = Field(default=None, max_length=240)
    postal_code: str | None = Field(default=None, max_length=20)
    city: str | None = Field(default=None, max_length=160)
    linkedin_url: str | None = Field(default=None, max_length=500)
    salary_expectation: str | None = Field(default=None, max_length=120)
    notice_period: str | None = Field(default=None, max_length=160)
    available_from: date | None = None
    last_contact_at: date | None = None
    next_step: str | None = Field(default=None, max_length=240)
    cv_available: bool = False
    short_profile: str | None = None
    consent_received: bool = False
    summary: str | None = None
    status: CandidateStatus = CandidateStatus.ACTIVE
    anrede: Anrede | None = None
    referred_by: str | None = Field(default=None, max_length=240)

    # --- Quali-Call-Erweiterung ---
    fachliche_schwerpunkte: list[str] = Field(default_factory=list)
    ausbildung_titel: str | None = Field(default=None, max_length=240)
    berufliche_stationen: list[BeruflicheStation] = Field(default_factory=list)
    aktuelles_umfeld_kanzleityp: str | None = Field(default=None, max_length=160)
    aktuelles_umfeld_kanzleigroesse: str | None = Field(default=None, max_length=160)
    # INTERN — niemals in anonyme Profile / ausgehende Dokumente übernehmen.
    wechselgrund: str | None = None
    remote_teilzeit_wuensche: str | None = Field(default=None, max_length=240)
    passender_kanzleityp: str | None = Field(default=None, max_length=160)
    # INTERN — niemals in anonyme Profile / ausgehende Dokumente übernehmen.
    no_gos: list[str] = Field(default_factory=list)
    freitext_notizen: str | None = None
    # Zustaendiger Mitarbeiter (Komfort-Filter, keine Sichtbarkeitsgrenze -
    # siehe models/candidate.py::owner_user_id).
    owner_user_id: uuid.UUID | None = None


class CandidateCreate(CandidateBase):
    pass


class CandidateUpdate(BaseModel):
    candidate_number: str | None = Field(default=None, max_length=40)
    first_name: str | None = Field(default=None, min_length=1, max_length=120)
    last_name: str | None = Field(default=None, min_length=1, max_length=120)
    email: EmailStr | None = None
    phone: str | None = Field(default=None, max_length=80)
    job_title: str | None = Field(default=None, max_length=180)
    qualification: str | None = Field(default=None, max_length=240)
    postal_code: str | None = Field(default=None, max_length=20)
    city: str | None = Field(default=None, max_length=160)
    linkedin_url: str | None = Field(default=None, max_length=500)
    salary_expectation: str | None = Field(default=None, max_length=120)
    notice_period: str | None = Field(default=None, max_length=160)
    available_from: date | None = None
    last_contact_at: date | None = None
    next_step: str | None = Field(default=None, max_length=240)
    cv_available: bool | None = None
    short_profile: str | None = None
    consent_received: bool | None = None
    summary: str | None = None
    status: CandidateStatus | None = None
    anrede: Anrede | None = None
    referred_by: str | None = Field(default=None, max_length=240)

    fachliche_schwerpunkte: list[str] | None = None
    ausbildung_titel: str | None = Field(default=None, max_length=240)
    berufliche_stationen: list[BeruflicheStation] | None = None
    aktuelles_umfeld_kanzleityp: str | None = Field(default=None, max_length=160)
    aktuelles_umfeld_kanzleigroesse: str | None = Field(default=None, max_length=160)
    wechselgrund: str | None = None
    remote_teilzeit_wuensche: str | None = Field(default=None, max_length=240)
    passender_kanzleityp: str | None = Field(default=None, max_length=160)
    no_gos: list[str] | None = None
    freitext_notizen: str | None = None
    owner_user_id: uuid.UUID | None = None


class CandidateRead(CandidateBase, EntityRead):
    has_ghosting_history: bool = False
    # System-gesetzt (siehe CandidateService.update()), nicht ueber
    # Create/Update durch den Nutzer steuerbar - deshalb nur im Read-Schema.
    cv_in_recorded_at: datetime | None = None


class CvExtractionRequest(BaseModel):
    document_id: str


class CvExtractionSuggestion(BaseModel):
    """Aus einem hochgeladenen CV extrahierte Feldvorschläge (Phase M, Punkt
    2) - enthält nur Felder, die beim Kandidaten aktuell leer sind (siehe
    services/cv_extraction.py); der Nutzer entscheidet im Frontend pro Feld,
    ob er den Vorschlag übernimmt, bevor irgendetwas gespeichert wird."""

    postal_code: str | None = None
    city: str | None = None
    phone: str | None = None
    job_title: str | None = None
    qualification: str | None = None
    ausbildung_titel: str | None = None
    source_is_agency_profile: bool = False
