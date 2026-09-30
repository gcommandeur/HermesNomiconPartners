import uuid
from datetime import date, datetime
from typing import Any

from pydantic import BaseModel, Field

from cc_crm.models.enums import InvoiceStatus
from cc_crm.schemas.base import ORMModel
from cc_crm.schemas.recruiting import FeeRead


class ApprovalRequestRead(ORMModel):
    id: uuid.UUID
    entity_type: str
    entity_id: uuid.UUID
    kind: str
    status: str
    requested_by: str | None
    requested_at: datetime
    old_values: dict[str, Any] | None
    proposed_values: dict[str, Any] | None
    decided_by: str | None
    decided_at: datetime | None
    decision_note: str | None
    # Anzeigename der betroffenen Kanzlei/Rechnung fuer die Inbox.
    entity_label: str | None = None


class ApprovalDecision(BaseModel):
    decision_note: str | None = Field(default=None, max_length=2000)


class InvoiceStatusChange(BaseModel):
    invoice_status: InvoiceStatus
    invoice_date: date | None = None
    payment_due_date: date | None = None


class InvoiceStatusChangeResult(BaseModel):
    fee: FeeRead
    # Gesetzt, wenn die Aenderung (Rechnung stellen durch Nicht-Admin) auf
    # Freigabe wartet statt sofort zu wirken.
    approval_request: ApprovalRequestRead | None = None
