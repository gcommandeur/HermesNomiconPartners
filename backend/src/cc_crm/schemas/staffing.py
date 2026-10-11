# NOMICON: Arbeitnehmerueberlassung - nur in der Nomicon-Kopie.
"""Schemas der Arbeitnehmerueberlassung.

Lohn (`hourly_wage`) und Verrechnungssatz (`billing_rate`) stehen in den Read-Schemas als
optionale Felder: fuer Nicht-Admins setzt die API-Schicht sie auf `None`
(services/staffing_visibility.py). Die Felder fehlen also nie im Schema, nur der Wert."""

import uuid
from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, Field, model_validator

from cc_crm.models.staffing import (
    StaffingAssignmentStatus,
    StaffingChecklistKey,
    StaffingContractStatus,
    StaffingTimesheetStatus,
    StaffingWorkerStatus,
)
from cc_crm.schemas.base import EntityRead, ORMModel
from cc_crm.services.staffing_deadlines import Traffic


def _check_range(start: date | None, end: date | None, message: str) -> None:
    if start is not None and end is not None and end < start:
        raise ValueError(message)


# --- Leiharbeitnehmer ---------------------------------------------------------------------------


class StaffingWorkerCreate(BaseModel):
    candidate_id: uuid.UUID
    status: StaffingWorkerStatus = StaffingWorkerStatus.APPLICANT
    entry_date: date | None = None
    exit_date: date | None = None
    hourly_wage: Decimal | None = Field(default=None, ge=0, le=Decimal("999.99"))
    pay_grade: str | None = Field(default=None, max_length=80)
    weekly_hours: Decimal | None = Field(default=None, gt=0, le=Decimal("80"))
    work_permit_valid_until: date | None = None
    notes: str | None = None

    @model_validator(mode="after")
    def _dates(self) -> "StaffingWorkerCreate":
        _check_range(self.entry_date, self.exit_date, "Austritt liegt vor dem Eintritt.")
        return self


class StaffingWorkerUpdate(BaseModel):
    status: StaffingWorkerStatus | None = None
    entry_date: date | None = None
    exit_date: date | None = None
    hourly_wage: Decimal | None = Field(default=None, ge=0, le=Decimal("999.99"))
    pay_grade: str | None = Field(default=None, max_length=80)
    weekly_hours: Decimal | None = Field(default=None, gt=0, le=Decimal("80"))
    work_permit_valid_until: date | None = None
    notes: str | None = None


class StaffingWorkerRead(EntityRead):
    candidate_id: uuid.UUID
    candidate_name: str
    candidate_number: str | None = None
    status: StaffingWorkerStatus
    entry_date: date | None
    exit_date: date | None
    hourly_wage: Decimal | None
    pay_grade: str | None
    weekly_hours: Decimal | None
    work_permit_valid_until: date | None
    notes: str | None


# --- Ueberlassungs-/Rahmenvertraege -------------------------------------------------------------


class StaffingContractCreate(BaseModel):
    client_company_id: uuid.UUID
    contract_number: str | None = Field(default=None, max_length=80)
    valid_from: date | None = None
    valid_to: date | None = None
    industry_sector: str | None = Field(default=None, max_length=120)
    document_id: uuid.UUID | None = None
    status: StaffingContractStatus = StaffingContractStatus.DRAFT
    notes: str | None = None

    @model_validator(mode="after")
    def _dates(self) -> "StaffingContractCreate":
        _check_range(self.valid_from, self.valid_to, "Vertragsende liegt vor dem Beginn.")
        return self


class StaffingContractUpdate(BaseModel):
    contract_number: str | None = Field(default=None, max_length=80)
    valid_from: date | None = None
    valid_to: date | None = None
    industry_sector: str | None = Field(default=None, max_length=120)
    document_id: uuid.UUID | None = None
    status: StaffingContractStatus | None = None
    notes: str | None = None


class StaffingContractRead(EntityRead):
    client_company_id: uuid.UUID
    client_name: str
    contract_number: str | None
    valid_from: date | None
    valid_to: date | None
    industry_sector: str | None
    document_id: uuid.UUID | None
    status: StaffingContractStatus
    notes: str | None


# --- Einsaetze ----------------------------------------------------------------------------------


class StaffingAssignmentCreate(BaseModel):
    worker_id: uuid.UUID
    client_company_id: uuid.UUID
    contract_id: uuid.UUID | None = None
    owner_user_id: uuid.UUID | None = None  # leer = der anlegende Nutzer
    start_date: date
    planned_end_date: date | None = None
    location: str | None = Field(default=None, max_length=240)
    activity: str | None = Field(default=None, max_length=240)
    billing_rate: Decimal | None = Field(default=None, ge=0, le=Decimal("999.99"))
    hourly_wage: Decimal | None = Field(default=None, ge=0, le=Decimal("999.99"))
    notes: str | None = None

    @model_validator(mode="after")
    def _dates(self) -> "StaffingAssignmentCreate":
        _check_range(self.start_date, self.planned_end_date, "Geplantes Ende liegt vor dem Start.")
        return self


class StaffingAssignmentUpdate(BaseModel):
    contract_id: uuid.UUID | None = None
    owner_user_id: uuid.UUID | None = None
    start_date: date | None = None
    planned_end_date: date | None = None
    location: str | None = Field(default=None, max_length=240)
    activity: str | None = Field(default=None, max_length=240)
    billing_rate: Decimal | None = Field(default=None, ge=0, le=Decimal("999.99"))
    hourly_wage: Decimal | None = Field(default=None, ge=0, le=Decimal("999.99"))
    notes: str | None = None


class StaffingAssignmentStatusChange(BaseModel):
    status: StaffingAssignmentStatus
    # Nur fuer "ended"/"aborted": tatsaechliches Ende, Standard = heute.
    actual_end_date: date | None = None


class StaffingChecklistItemRead(ORMModel):
    id: uuid.UUID
    item_key: StaffingChecklistKey
    done: bool
    done_on: date | None
    document_id: uuid.UUID | None


class StaffingChecklistItemUpdate(BaseModel):
    done: bool
    done_on: date | None = None  # Standard beim Abhaken: heute
    document_id: uuid.UUID | None = None


class StaffingAssignmentRead(EntityRead):
    worker_id: uuid.UUID
    worker_name: str
    client_company_id: uuid.UUID
    client_name: str
    contract_id: uuid.UUID | None
    owner_user_id: uuid.UUID | None
    start_date: date
    planned_end_date: date | None
    actual_end_date: date | None
    location: str | None
    activity: str | None
    billing_rate: Decimal | None
    hourly_wage: Decimal | None
    status: StaffingAssignmentStatus
    notes: str | None
    checklist_done: int
    checklist_total: int


class StaffingDeadlineRead(BaseModel):
    """Fristen eines Paares (Leiharbeitnehmer, Kunde), siehe services/staffing_deadlines.py."""

    has_chain: bool
    chain_start: date | None
    elapsed_months: int
    elapsed_days: int
    counted_days: int
    equal_pay_from: date | None
    equal_pay_reached: bool
    max_end_date: date | None
    days_remaining: int | None
    exceeded: bool
    traffic: Traffic


class StaffingPairDeadlineRead(StaffingDeadlineRead):
    worker_id: uuid.UUID
    worker_name: str
    client_company_id: uuid.UUID
    client_name: str
    owner_user_id: uuid.UUID | None


class StaffingAssignmentDetail(StaffingAssignmentRead):
    checklist: list[StaffingChecklistItemRead]
    deadline: StaffingDeadlineRead
    # Nicht erfuellte Voraussetzungen fuer die Aktivierung (leer = aktivierbar).
    activation_problems: list[str]


# --- Erlaubnis ----------------------------------------------------------------------------------


class StaffingLicenseCreate(BaseModel):
    authority: str = Field(min_length=1, max_length=160)
    file_number: str | None = Field(default=None, max_length=80)
    valid_from: date
    valid_to: date | None = None
    document_id: uuid.UUID | None = None
    reminder_days: int = Field(default=90, ge=0, le=730)
    notes: str | None = None

    @model_validator(mode="after")
    def _dates(self) -> "StaffingLicenseCreate":
        _check_range(self.valid_from, self.valid_to, "Gueltig-bis liegt vor Gueltig-ab.")
        return self


class StaffingLicenseUpdate(BaseModel):
    authority: str | None = Field(default=None, min_length=1, max_length=160)
    file_number: str | None = Field(default=None, max_length=80)
    valid_from: date | None = None
    valid_to: date | None = None
    document_id: uuid.UUID | None = None
    reminder_days: int | None = Field(default=None, ge=0, le=730)
    notes: str | None = None


class StaffingLicenseRead(EntityRead):
    authority: str
    file_number: str | None
    valid_from: date
    valid_to: date | None
    document_id: uuid.UUID | None
    reminder_days: int
    notes: str | None


# --- Uebersicht und Einstellungen -------------------------------------------------------------


class StaffingLicenseStatus(BaseModel):
    """Zustand der AÜG-Erlaubnis heute."""

    valid: bool
    valid_to: date | None  # Ende der heute gueltigen Erlaubnis (None = unbefristet oder keine)
    days_remaining: int | None
    traffic: Traffic


class StaffingOverviewRead(BaseModel):
    active_assignments: int
    planned_assignments: int
    open_checklist_assignments: int  # geplante/aktive Einsaetze mit unvollstaendiger Checkliste
    license: StaffingLicenseStatus
    deadlines: list[StaffingPairDeadlineRead]  # dringendste zuerst, nur Paare mit Zaehler


class StaffingSettingsRead(BaseModel):
    max_months: int
    equal_pay_months: int
    reset_gap_months: int
    yellow_days: int
    red_days: int
    notice: str


class StaffingSettingsUpdate(BaseModel):
    max_months: int = Field(gt=0, le=120)
    equal_pay_months: int = Field(gt=0, le=120)
    reset_gap_months: int = Field(gt=0, le=60)
    yellow_days: int = Field(gt=0, le=3650)
    red_days: int = Field(gt=0, le=3650)


# --- Stundenzettel und Kundenfreigabe ---------------------------------------------------------


class StaffingTimesheetCreate(BaseModel):
    period_start: date
    period_end: date

    @model_validator(mode="after")
    def _dates(self) -> "StaffingTimesheetCreate":
        _check_range(self.period_start, self.period_end, "Das Ende liegt vor dem Beginn.")
        return self


class StaffingTimesheetEntryInput(BaseModel):
    work_date: date
    hours: Decimal = Field(gt=0, le=Decimal("24"), decimal_places=2)
    break_minutes: int = Field(default=0, ge=0, le=600)


class StaffingTimesheetEntriesUpdate(BaseModel):
    """Ersetzt ALLE Eintraege des Stundenzettels (idempotent). Leere Liste = alles loeschen."""

    entries: list[StaffingTimesheetEntryInput] = Field(max_length=93)


class StaffingTimesheetEntryRead(ORMModel):
    work_date: date
    hours: Decimal
    break_minutes: int


class StaffingTimesheetRead(EntityRead):
    assignment_id: uuid.UUID
    worker_name: str
    client_name: str
    period_start: date
    period_end: date
    status: StaffingTimesheetStatus
    submitted_at: datetime | None
    decided_at: datetime | None
    decided_by_name: str | None
    rejection_reason: str | None
    approval_link_expires_at: datetime | None  # nur solange ein Link gilt
    total_hours: Decimal
    entries: list[StaffingTimesheetEntryRead]


class StaffingTimesheetSubmitResult(BaseModel):
    timesheet: StaffingTimesheetRead
    # Pfad der Freigabeseite (ohne Host, das Frontend setzt die Adresse davor). Der Klartext
    # steht NUR in dieser Antwort - in der Datenbank liegt nur der Hash.
    approval_path: str
    expires_at: datetime


class PublicTimesheetRead(BaseModel):
    """Alles, was der Kunde ueber den Freigabelink sieht - keine IDs, keine Lohn- oder
    Verrechnungsdaten."""

    worker_name: str
    client_name: str
    period_start: date
    period_end: date
    status: StaffingTimesheetStatus
    total_hours: Decimal
    entries: list[StaffingTimesheetEntryRead]
    decided_at: datetime | None
    decided_by_name: str | None
    rejection_reason: str | None
    expires_at: datetime | None


class PublicTimesheetApprove(BaseModel):
    approver_name: str = Field(min_length=2, max_length=160)


class PublicTimesheetReject(BaseModel):
    approver_name: str = Field(min_length=2, max_length=160)
    reason: str = Field(min_length=3, max_length=2000)
