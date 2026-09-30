"""Rechnungsstatus einer Fee (Entwurf -> Gestellt -> Faellig -> Bezahlt, jederzeit
stornierbar solange nicht bezahlt). Nur "Rechnung stellen" (DRAFT -> ISSUED)
durch einen Nicht-Admin geht ueber die Freigabe-Inbox, alle anderen
Uebergaenge wirken sofort."""

import uuid
from datetime import UTC, date, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from cc_crm.core.errors import BusinessRuleError, EntityNotFoundError
from cc_crm.models.approval_request import ApprovalRequest
from cc_crm.models.candidate import Candidate
from cc_crm.models.enums import InvoiceStatus
from cc_crm.models.recruiting import Fee, Placement
from cc_crm.models.submission import CandidateSubmission
from cc_crm.models.user import User
from cc_crm.repositories.recruiting import AuditLogRepository
from cc_crm.schemas.approval import InvoiceStatusChange
from cc_crm.services.approvals import ApprovalService, needs_approval

ALLOWED_INVOICE_TRANSITIONS: dict[InvoiceStatus, set[InvoiceStatus]] = {
    InvoiceStatus.DRAFT: {InvoiceStatus.ISSUED, InvoiceStatus.CANCELLED},
    InvoiceStatus.ISSUED: {InvoiceStatus.DUE, InvoiceStatus.PAID, InvoiceStatus.CANCELLED},
    InvoiceStatus.DUE: {InvoiceStatus.PAID, InvoiceStatus.CANCELLED},
    InvoiceStatus.PAID: set(),
    InvoiceStatus.CANCELLED: set(),
}


def apply_invoice_status(fee: Fee, target: InvoiceStatus, values: dict[str, Any]) -> None:
    """Setzt den Status samt passender Datumsfelder - auch von der Freigabe
    (services/approvals.py) beim Genehmigen genutzt."""
    fee.invoice_status = target
    if target == InvoiceStatus.ISSUED:
        fee.invoice_date = _as_date(values.get("invoice_date")) or fee.invoice_date or date.today()
        due = _as_date(values.get("payment_due_date"))
        if due is not None:
            fee.payment_due_date = due
    if target == InvoiceStatus.PAID:
        fee.paid_at = datetime.now(UTC)


def _as_date(value: Any) -> date | None:
    if value is None or isinstance(value, date):
        return value
    return date.fromisoformat(str(value))


class InvoiceService:
    def __init__(self, session: Session) -> None:
        self.session = session
        self.audit_logs = AuditLogRepository(session)
        self.approvals = ApprovalService(session)

    def fees_for_placement(self, placement_id: uuid.UUID) -> list[Fee]:
        return list(
            self.session.scalars(
                select(Fee).where(Fee.placement_id == placement_id).order_by(Fee.created_at)
            ).all()
        )

    def change_status(
        self, fee_id: uuid.UUID, change: InvoiceStatusChange, current_user: User
    ) -> tuple[Fee, ApprovalRequest | None]:
        fee = self.session.get(Fee, fee_id)
        if fee is None:
            raise EntityNotFoundError("Rechnung nicht gefunden")
        old_status = fee.invoice_status
        target = change.invoice_status
        if target not in ALLOWED_INVOICE_TRANSITIONS[old_status]:
            raise BusinessRuleError(
                f"Rechnungsstatus {old_status.value} -> {target.value} ist nicht erlaubt"
            )
        values = change.model_dump(exclude={"invoice_status"}, exclude_none=True, mode="json")

        if target == InvoiceStatus.ISSUED and needs_approval(current_user):
            approval = self.approvals.request(
                entity_type="fee",
                entity_id=fee.id,
                kind="invoice_issue",
                requested_by=current_user,
                old_values={"invoice_status": old_status.value},
                proposed_values={
                    "invoice_status": target.value,
                    "amount_net": str(fee.amount_net),
                    "amount_gross": str(fee.amount_gross),
                    "label": self._label(fee),
                    **values,
                },
            )
            self.session.commit()
            return fee, approval

        apply_invoice_status(fee, target, values)
        self.audit_logs.create(
            {
                "entity_type": "fee",
                "entity_id": fee.id,
                "action": "invoice_status_changed",
                "changed_by": current_user.email,
                "old_values": {"invoice_status": old_status.value},
                "new_values": {"invoice_status": target.value},
            }
        )
        self.session.commit()
        return fee, None

    def _label(self, fee: Fee) -> str:
        """"Rechnung Max Muster (12.345,00 EUR netto)" fuer die Inbox."""
        placement = self.session.get(Placement, fee.placement_id)
        submission = (
            self.session.get(CandidateSubmission, placement.submission_id) if placement else None
        )
        candidate = self.session.get(Candidate, submission.candidate_id) if submission else None
        name = f"{candidate.first_name} {candidate.last_name}" if candidate else "Placement"
        return f"Rechnung {name} ({fee.amount_net} EUR netto)"
