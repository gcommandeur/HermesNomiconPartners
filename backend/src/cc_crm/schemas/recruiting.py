import uuid
from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, Field, computed_field

from cc_crm.models.enums import (
    FeedbackType,
    InterviewStatus,
    InvoiceStatus,
    OfferStatus,
    PlacementStatus,
    SubmissionStatus,
    WarrantyStatus,
)
from cc_crm.schemas.base import EntityRead, ORMModel
from cc_crm.services.warranty import warranty_end_date, warranty_status


class FeedbackCreate(BaseModel):
    feedback_type: FeedbackType
    feedback_text: str = Field(min_length=1)
    received_at: datetime
    next_step: str | None = None
    created_by: str | None = None
    stage: SubmissionStatus | None = None
    # Bullhorn-artiges "Action"-Feld: wird der Notiz ein Zielstatus mitgegeben
    # und weicht dieser vom aktuellen Submission-Status ab, wendet
    # RecruitingProcessService.create_feedback in derselben Transaktion die
    # bestehende Transition-Logik (services/submissions.py::ALLOWED_TRANSITIONS)
    # an und setzt `stage` auf diesen Zielstatus - siehe Frontend
    # feedback-panel.tsx, wo das bisherige "Art"-Dropdown dadurch ersetzt wurde.
    target_status: SubmissionStatus | None = None


class FeedbackRead(FeedbackCreate, EntityRead):
    submission_id: uuid.UUID


class FeedbackUpdate(BaseModel):
    feedback_type: FeedbackType | None = None
    feedback_text: str | None = Field(default=None, min_length=1)
    received_at: datetime | None = None
    next_step: str | None = None
    created_by: str | None = None
    stage: SubmissionStatus | None = None


class InterviewCreate(BaseModel):
    scheduled_at: datetime
    interview_type: str = Field(min_length=1, max_length=120)
    location_or_link: str | None = None
    participants: list[str] = Field(default_factory=list)
    status: InterviewStatus = InterviewStatus.SCHEDULED
    notes: str | None = None


class InterviewRead(InterviewCreate, EntityRead):
    submission_id: uuid.UUID


class InterviewUpdate(BaseModel):
    scheduled_at: datetime | None = None
    interview_type: str | None = Field(default=None, min_length=1, max_length=120)
    location_or_link: str | None = None
    participants: list[str] | None = None
    status: InterviewStatus | None = None
    notes: str | None = None


class OfferCreate(BaseModel):
    offered_salary: Decimal = Field(gt=0)
    variable_compensation: Decimal | None = Field(default=None, ge=0)
    start_date: date | None = None
    offer_status: OfferStatus = OfferStatus.RECEIVED
    notes: str | None = None


class OfferRead(OfferCreate, EntityRead):
    submission_id: uuid.UUID


class OfferUpdate(BaseModel):
    offered_salary: Decimal | None = Field(default=None, gt=0)
    variable_compensation: Decimal | None = Field(default=None, ge=0)
    start_date: date | None = None
    offer_status: OfferStatus | None = None
    notes: str | None = None


class PlacementCreate(BaseModel):
    start_date: date
    final_salary: Decimal = Field(gt=0)
    fee_percentage: Decimal | None = Field(default=None, gt=0, le=100)
    rabatt_percentage: Decimal = Field(default=Decimal("0"), ge=0, le=100)
    fee_fix: Decimal | None = Field(default=None, gt=0)
    guarantee_period_months: int = Field(default=0, ge=0)
    status: PlacementStatus = PlacementStatus.PLANNED


class PlacementRead(PlacementCreate, EntityRead):
    submission_id: uuid.UUID
    calculated_fee: Decimal

    @computed_field  # type: ignore[prop-decorator]
    @property
    def warranty_end_date(self) -> date:
        return warranty_end_date(self.start_date, self.guarantee_period_months)

    @computed_field  # type: ignore[prop-decorator]
    @property
    def warranty_status(self) -> WarrantyStatus:
        return warranty_status(self.warranty_end_date)


class PlacementUpdate(BaseModel):
    start_date: date | None = None
    final_salary: Decimal | None = Field(default=None, gt=0)
    fee_percentage: Decimal | None = Field(default=None, gt=0, le=100)
    rabatt_percentage: Decimal | None = Field(default=None, ge=0, le=100)
    fee_fix: Decimal | None = Field(default=None, gt=0)
    # Einziger Weg, fee_fix nach dem Speichern wieder auf "kein Fixbetrag"
    # zurueckzusetzen (Umschalter zurueck auf "Berechnet") - `fee_fix: None`
    # allein ist von "Feld nicht mitgeschickt" nicht unterscheidbar, da
    # PlacementUpdate ueber `model_dump(exclude_unset=True)` angewendet wird.
    clear_fee_fix: bool = False
    guarantee_period_months: int | None = Field(default=None, ge=0)
    status: PlacementStatus | None = None


class FeeCreate(BaseModel):
    amount_net: Decimal = Field(gt=0)
    vat_rate: Decimal | None = Field(default=None, ge=0, le=100)
    invoice_status: InvoiceStatus = InvoiceStatus.DRAFT
    invoice_date: date | None = None
    payment_due_date: date | None = None
    paid_at: datetime | None = None


class FeeRead(FeeCreate, EntityRead):
    placement_id: uuid.UUID
    vat_rate: Decimal
    amount_gross: Decimal


class AuditLogRead(ORMModel):
    id: uuid.UUID
    entity_type: str
    entity_id: uuid.UUID
    action: str
    changed_at: datetime
    changed_by: str | None
    old_values: dict[str, object] | None
    new_values: dict[str, object] | None
