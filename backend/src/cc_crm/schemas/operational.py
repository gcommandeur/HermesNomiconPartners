import uuid
from datetime import date, datetime

from pydantic import BaseModel, Field

from cc_crm.schemas.base import EntityRead


class DocumentCreate(BaseModel):
    owner_type: str = Field(pattern="^(candidate|client|submission|placement|fee)$")
    owner_id: uuid.UUID
    document_type: str = Field(min_length=1, max_length=60)
    filename: str = Field(min_length=1, max_length=255)
    storage_key: str = Field(min_length=1, max_length=500)
    content_type: str | None = None
    size_bytes: int | None = Field(default=None, ge=0)
    uploaded_by: str | None = None
    sent_with_submission_id: uuid.UUID | None = None


class DocumentRead(DocumentCreate, EntityRead):
    has_generic_filename: bool = False


class SourcingMetricCreate(BaseModel):
    period_start: date
    period_end: date
    source: str = Field(default="LinkedIn", max_length=80)
    campaign: str | None = Field(default=None, max_length=240)
    pitches: int = Field(default=0, ge=0)
    responses: int = Field(default=0, ge=0)
    positive_responses: int = Field(default=0, ge=0)
    qualification_calls: int = Field(default=0, ge=0)
    notes: str | None = None


class SourcingMetricRead(SourcingMetricCreate, EntityRead):
    pass


class EmailTemplateRead(BaseModel):
    key: str
    name: str
    subject: str
    body: str
    placeholders: list[str]


class EmailDraftCreate(BaseModel):
    template_key: str
    candidate_id: uuid.UUID | None = None
    client_company_id: uuid.UUID | None = None
    candidate_submission_id: uuid.UUID | None = None
    recipient: str | None = None
    subject: str
    body: str


class EmailDraftRead(EmailDraftCreate, EntityRead):
    provider: str
    external_draft_id: str | None
    drafted_at: datetime | None


class ProfileSuggestion(BaseModel):
    candidate_id: uuid.UUID
    text: str
    is_draft: bool = True


class CockpitItem(BaseModel):
    kind: str
    title: str
    detail: str
    due_at: datetime | None = None
    candidate_id: uuid.UUID | None = None
    client_company_id: uuid.UUID | None = None
    submission_id: uuid.UUID | None = None
    priority: str = "normal"
    # Nur bei kind="task" gesetzt (siehe CockpitService.build) - die
    # Dashboard-To-Do-Sektion braucht die Task-ID fuer die Snooze/Resolve-
    # Aktionen (POST /tasks/{id}/snooze bzw. /resolve).
    task_id: uuid.UUID | None = None


class CockpitKpis(BaseModel):
    qualification_calls: int
    cv_available: int
    submissions: int
    interviews: int
    offers: int
    placements: int
    expected_fees: float
    realized_fees: float


class CockpitRates(BaseModel):
    submission_to_interview: float
    interview_to_offer: float
    offer_to_placement: float
    placement_to_paid: float


class SourcingFunnel(BaseModel):
    has_data: bool
    pitches: int
    responses: int
    positive_responses: int
    qualification_calls: int
    pitch_to_response_rate: float | None
    response_to_qualification_call_rate: float | None


class RecruitingKpis(BaseModel):
    """Etablierte Standard-Recruiting-Kennzahlen (siehe CockpitService::
    _recruiting_kpis) - bewusst NICHT auf den gewaehlten period-Zeitraum
    beschraenkt, sondern ueber den gesamten historischen Bestand berechnet,
    da Median-Durchlaufzeiten ueber wenige Wochen/Monate zu wenig Datenpunkte
    haetten, um aussagekraeftig zu sein. None, solange keine einzige
    Placement/Interview-Transition vorliegt (keine Kennzahl vorspiegeln)."""

    time_to_fill_days: float | None
    time_to_interview_days: float | None
    average_fee_per_placement: float | None


class CockpitRead(BaseModel):
    period: str
    important: list[CockpitItem]
    hot_processes: list[CockpitItem]
    kpis: CockpitKpis
    recruiting_kpis: RecruitingKpis
    rates: CockpitRates
    sourcing: SourcingFunnel
