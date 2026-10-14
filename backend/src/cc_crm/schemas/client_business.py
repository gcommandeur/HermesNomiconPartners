# NOMICON: "Geschaeft mit dieser Kanzlei" - nur in der Nomicon-Kopie.
import uuid
from datetime import date
from decimal import Decimal

from pydantic import BaseModel

from cc_crm.schemas.staffing import StaffingPairDeadlineRead


class ClientProcessRead(BaseModel):
    id: uuid.UUID
    candidate_name: str
    status: str
    owner_name: str | None
    expected_fee: Decimal | None


class ClientAssignmentRead(BaseModel):
    id: uuid.UUID
    worker_name: str
    status: str
    start_date: date
    end_date: date | None
    owner_name: str | None


class ClientRevenueRead(BaseModel):
    """Nur fuer Admins."""

    placement_fees_paid: Decimal
    staffing_invoiced: Decimal


class ClientBusinessRead(BaseModel):
    """Jeder Abschnitt ist `None`, wenn dem Nutzer die zugehoerige Ansicht fehlt (processes: Direct,
    assignments/deadlines: Ueberlassung, revenue: Admin). Prozesse und Einsaetze nur im eigenen
    Sichtbereich (Owner-Scope)."""

    processes: list[ClientProcessRead] | None
    assignments: list[ClientAssignmentRead] | None
    deadlines: list[StaffingPairDeadlineRead] | None
    revenue: ClientRevenueRead | None
