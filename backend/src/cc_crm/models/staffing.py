# NOMICON: Arbeitnehmerüberlassung (AÜG) - nur in der Nomicon-Kopie, nicht in Hermes.
# Alle Tabellen tragen das Praefix `staffing_`, damit spaetere Hermes-Tabellen nicht kollidieren.
"""Datenmodell der Arbeitnehmerüberlassung.

Ein Leiharbeitnehmer ist ein bestehender `Candidate` mit zusätzlichem Profil
(`StaffingWorker`, 1:1). Einsätze (`StaffingAssignment`) verbinden Leiharbeitnehmer, Kunde
(`ClientCompany`) und optional einen Überlassungs-/Rahmenvertrag. Lohn und Verrechnungssatz
sind Margendaten und werden nur Admins ausgeliefert (Schicht api/services, nicht hier).
Die Lohnabrechnung selbst bleibt extern - hier steht nur der Stundenlohn als Stammdatum."""

import uuid
from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from cc_crm.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from cc_crm.models.enums import InvoiceStatus


class StaffingWorkerStatus(StrEnum):
    APPLICANT = "applicant"  # Anwärter
    ACTIVE = "active"
    DORMANT = "dormant"  # ruhend
    LEFT = "left"  # ausgeschieden


class StaffingContractStatus(StrEnum):
    DRAFT = "draft"
    ACTIVE = "active"
    EXPIRED = "expired"
    TERMINATED = "terminated"


class StaffingAssignmentStatus(StrEnum):
    PLANNED = "planned"
    ACTIVE = "active"
    ENDED = "ended"
    ABORTED = "aborted"


class StaffingTimesheetStatus(StrEnum):
    OPEN = "open"
    SUBMITTED = "submitted"
    APPROVED = "approved"
    REJECTED = "rejected"


class StaffingChecklistKey(StrEnum):
    """Pflichtpunkte je Einsatz (Reihenfolge = Anzeigereihenfolge)."""

    EMPLOYMENT_CONTRACT = "employment_contract"  # Arbeitsvertrag / Nachweis nach Par. 11 AÜG
    INFO_LEAFLET = "info_leaflet"  # Merkblatt für Leiharbeitnehmer
    SUPPLY_CONTRACT = "supply_contract"  # Überlassungsvertrag, Par. 12 AÜG
    SPECIFICATION = "specification"  # Konkretisierung der Person im Überlassungsvertrag
    SAFETY_BRIEFING = "safety_briefing"  # Sicherheitsunterweisung
    PPE_PROTOCOL = "ppe_protocol"  # Übergabeprotokoll persönliche Schutzausrüstung


CHECKLIST_KEYS: tuple[StaffingChecklistKey, ...] = tuple(StaffingChecklistKey)


class StaffingWorker(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "staffing_workers"

    candidate_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("candidates.id", ondelete="RESTRICT"),
        nullable=False,
        unique=True,
    )
    status: Mapped[StaffingWorkerStatus] = mapped_column(
        Enum(StaffingWorkerStatus, native_enum=False, length=20),
        default=StaffingWorkerStatus.APPLICANT,
        nullable=False,
        index=True,
    )
    entry_date: Mapped[date | None] = mapped_column(Date)
    exit_date: Mapped[date | None] = mapped_column(Date)
    hourly_wage: Mapped[Decimal | None] = mapped_column(Numeric(8, 2))  # nur Admins sichtbar
    pay_grade: Mapped[str | None] = mapped_column(String(80))  # Tarif-/Entgeltgruppe
    weekly_hours: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))
    work_permit_valid_until: Mapped[date | None] = mapped_column(Date, index=True)
    notes: Mapped[str | None] = mapped_column(Text)


class StaffingContract(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Überlassungs- bzw. Rahmenvertrag mit einem Kunden."""

    __tablename__ = "staffing_contracts"

    client_company_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("client_companies.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    contract_number: Mapped[str | None] = mapped_column(String(80))
    valid_from: Mapped[date | None] = mapped_column(Date)
    valid_to: Mapped[date | None] = mapped_column(Date)
    industry_sector: Mapped[str | None] = mapped_column(String(120))  # für Branchenzuschlag
    document_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("documents.id", ondelete="SET NULL")
    )
    status: Mapped[StaffingContractStatus] = mapped_column(
        Enum(StaffingContractStatus, native_enum=False, length=20),
        default=StaffingContractStatus.DRAFT,
        nullable=False,
        index=True,
    )
    notes: Mapped[str | None] = mapped_column(Text)


class StaffingAssignment(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Einsatz eines Leiharbeitnehmers bei einem Kunden."""

    __tablename__ = "staffing_assignments"

    worker_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("staffing_workers.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    client_company_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("client_companies.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    contract_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("staffing_contracts.id", ondelete="SET NULL"), index=True
    )
    # Disponent: bestimmt die Sichtbarkeit (staffing_owner_scope), wie bei Prozessen.
    owner_user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), index=True
    )
    start_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    planned_end_date: Mapped[date | None] = mapped_column(Date)
    actual_end_date: Mapped[date | None] = mapped_column(Date)
    location: Mapped[str | None] = mapped_column(String(240))
    activity: Mapped[str | None] = mapped_column(String(240))
    billing_rate: Mapped[Decimal | None] = mapped_column(Numeric(8, 2))  # nur Admins sichtbar
    hourly_wage: Mapped[Decimal | None] = mapped_column(Numeric(8, 2))  # nur Admins sichtbar
    status: Mapped[StaffingAssignmentStatus] = mapped_column(
        Enum(StaffingAssignmentStatus, native_enum=False, length=20),
        default=StaffingAssignmentStatus.PLANNED,
        nullable=False,
        index=True,
    )
    notes: Mapped[str | None] = mapped_column(Text)


class StaffingAssignmentExtension(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Verlaengerung eines Einsatzes (geplantes Ende wurde nach hinten verschoben). Jede Zeile ist
    fuer das Provisionsmodell ein NEUER Deal (Bonus bei der ersten Zahlung einer Rechnung ueber
    Zeitraeume nach `previous_end`). Ein Folgeeinsatz ist dagegen ein neuer `StaffingAssignment`."""

    __tablename__ = "staffing_assignment_extensions"

    assignment_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("staffing_assignments.id", ondelete="CASCADE"), nullable=False, index=True
    )
    previous_end: Mapped[date] = mapped_column(Date, nullable=False)
    new_end: Mapped[date] = mapped_column(Date, nullable=False)
    extended_on: Mapped[date] = mapped_column(Date, nullable=False)
    created_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )


class StaffingChecklistItem(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "staffing_assignment_checklist_items"
    __table_args__ = (UniqueConstraint("assignment_id", "item_key"),)

    assignment_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("staffing_assignments.id", ondelete="CASCADE"), nullable=False, index=True
    )
    item_key: Mapped[StaffingChecklistKey] = mapped_column(
        Enum(StaffingChecklistKey, native_enum=False, length=40), nullable=False
    )
    done: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    done_on: Mapped[date | None] = mapped_column(Date)
    document_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("documents.id", ondelete="SET NULL")
    )


class StaffingLicense(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Erlaubnis zur Arbeitnehmerüberlassung nach AÜG."""

    __tablename__ = "staffing_licenses"

    authority: Mapped[str] = mapped_column(String(160), nullable=False)
    file_number: Mapped[str | None] = mapped_column(String(80))
    valid_from: Mapped[date] = mapped_column(Date, nullable=False)
    valid_to: Mapped[date | None] = mapped_column(Date, index=True)  # NULL = unbefristet
    document_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("documents.id", ondelete="SET NULL")
    )
    reminder_days: Mapped[int] = mapped_column(Integer, default=90, nullable=False)
    notes: Mapped[str | None] = mapped_column(Text)


class StaffingTimesheet(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Stundenzettel je Einsatz und Zeitraum. Der Freigabe-Token für den Kunden wird nur als
    SHA-256-Hash gespeichert (der Klartext existiert nur in dem einen Link)."""

    __tablename__ = "staffing_timesheets"
    __table_args__ = (UniqueConstraint("assignment_id", "period_start"),)

    assignment_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("staffing_assignments.id", ondelete="CASCADE"), nullable=False, index=True
    )
    period_start: Mapped[date] = mapped_column(Date, nullable=False)
    period_end: Mapped[date] = mapped_column(Date, nullable=False)
    status: Mapped[StaffingTimesheetStatus] = mapped_column(
        Enum(StaffingTimesheetStatus, native_enum=False, length=20),
        default=StaffingTimesheetStatus.OPEN,
        nullable=False,
        index=True,
    )
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    decided_by_name: Mapped[str | None] = mapped_column(String(160))
    rejection_reason: Mapped[str | None] = mapped_column(Text)
    approval_token_hash: Mapped[str | None] = mapped_column(String(64), unique=True)
    approval_token_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    approval_token_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class StaffingTimesheetEntry(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "staffing_timesheet_entries"
    __table_args__ = (UniqueConstraint("timesheet_id", "work_date"),)

    timesheet_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("staffing_timesheets.id", ondelete="CASCADE"), nullable=False, index=True
    )
    work_date: Mapped[date] = mapped_column(Date, nullable=False)
    hours: Mapped[Decimal] = mapped_column(Numeric(4, 2), nullable=False)
    break_minutes: Mapped[int] = mapped_column(Integer, default=0, nullable=False)


class StaffingInvoice(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Rechnung über freigegebene Stundenzettel. Folgt dem Rechnungsmodell der Vermittlung
    (`Fee`): gleiche Betragsfelder, derselbe Status (`InvoiceStatus`) und dieselbe Freigabe-Inbox
    ("Rechnung stellen" durch Nicht-Admins braucht einen Admin), aber an Kunde und Stundenzettel
    statt an ein Placement gehängt."""

    __tablename__ = "staffing_invoices"

    client_company_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("client_companies.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    period_start: Mapped[date] = mapped_column(Date, nullable=False)
    period_end: Mapped[date] = mapped_column(Date, nullable=False)
    amount_net: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    vat_rate: Mapped[Decimal] = mapped_column(Numeric(5, 2), nullable=False)
    amount_gross: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    invoice_status: Mapped[InvoiceStatus] = mapped_column(
        Enum(InvoiceStatus, native_enum=False, length=32),
        default=InvoiceStatus.DRAFT,
        nullable=False,
        index=True,
    )
    invoice_date: Mapped[date | None] = mapped_column(Date)
    payment_due_date: Mapped[date | None] = mapped_column(Date)
    paid_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), index=True
    )
    notes: Mapped[str | None] = mapped_column(Text)


class StaffingInvoiceLine(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Eine Zeile je Stundenzettel (Momentaufnahme von Name, Stunden und Satz). `timesheet_id` ist
    eindeutig: ein Stundenzettel kann nur auf einer Rechnung stehen; bei Storno wird er auf NULL
    gesetzt (wieder abrechenbar), die Zeile bleibt als Nachweis."""

    __tablename__ = "staffing_invoice_lines"

    invoice_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("staffing_invoices.id", ondelete="CASCADE"), nullable=False, index=True
    )
    timesheet_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("staffing_timesheets.id", ondelete="SET NULL"), unique=True
    )
    assignment_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("staffing_assignments.id", ondelete="SET NULL"), index=True
    )
    worker_name: Mapped[str] = mapped_column(String(240), nullable=False)
    description: Mapped[str] = mapped_column(String(400), nullable=False)
    period_start: Mapped[date] = mapped_column(Date, nullable=False)
    period_end: Mapped[date] = mapped_column(Date, nullable=False)
    hours: Mapped[Decimal] = mapped_column(Numeric(8, 2), nullable=False)
    rate: Mapped[Decimal] = mapped_column(Numeric(8, 2), nullable=False)
    amount_net: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
