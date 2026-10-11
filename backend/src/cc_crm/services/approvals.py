"""Freigabe-Inbox: Nicht-Admins loesen fuer neue Kanzleien, Honorar-
Aenderungen und das Stellen einer Rechnung eine Anfrage aus, statt dass die
Aenderung sofort wirkt. Ein Admin/GF genehmigt (Aenderung wird jetzt
angewendet) oder lehnt ab (alter Zustand bleibt). Beides landet im AuditLog.
Admins selbst loesen nie eine Anfrage aus."""

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from cc_crm.core.errors import BusinessRuleError, ConflictError, EntityNotFoundError
from cc_crm.models.approval_request import ApprovalRequest
from cc_crm.models.client_company import ClientCompany
from cc_crm.models.enums import ClientStatus, InvoiceStatus
from cc_crm.models.recruiting import Fee
from cc_crm.models.user import User
from cc_crm.repositories.recruiting import AuditLogRepository

HONORAR_FIELDS = frozenset(
    {
        "fee_percentage",
        "honorar_stufe",
        "nachlass_begruendung",
        "guarantee_period_months",
        "payment_terms_days",
        "refund_terms",
        "special_terms",
    }
)

PENDING = "pending"
APPROVED = "approved"
REJECTED = "rejected"


def needs_approval(current_user: User | None) -> bool:
    """Nur echte Nicht-Admin-Aufrufe ueber die API; interne Aufrufe (Importe,
    Skripte) ohne current_user bleiben unberuehrt."""
    return current_user is not None and not current_user.is_admin


class ApprovalService:
    def __init__(self, session: Session) -> None:
        self.session = session
        self.audit_logs = AuditLogRepository(session)

    def request(
        self,
        *,
        entity_type: str,
        entity_id: uuid.UUID,
        kind: str,
        requested_by: User,
        old_values: dict[str, Any] | None = None,
        proposed_values: dict[str, Any] | None = None,
    ) -> ApprovalRequest:
        """Legt eine Anfrage an - oder aktualisiert eine bereits offene
        derselben Art fuer dasselbe Objekt (z.B. zweite Honorar-Aenderung vor
        der Freigabe), damit nie zwei widerspruechliche Anfragen offen sind.
        Committet nicht - der Aufrufer committet zusammen mit seiner eigenen
        Aenderung."""
        existing = self.session.scalars(
            select(ApprovalRequest).where(
                ApprovalRequest.entity_type == entity_type,
                ApprovalRequest.entity_id == entity_id,
                ApprovalRequest.kind == kind,
                ApprovalRequest.status == PENDING,
            )
        ).first()
        now = datetime.now(UTC)
        if existing is not None:
            # Urspruenglicher Altwert bleibt erhalten, neue Vorschlaege
            # ueberschreiben aeltere fuer dieselben Felder.
            merged_old = dict(existing.old_values or {})
            for key, value in (old_values or {}).items():
                merged_old.setdefault(key, value)
            existing.old_values = merged_old
            existing.proposed_values = {
                **(existing.proposed_values or {}),
                **(proposed_values or {}),
            }
            existing.requested_by = requested_by.email
            existing.requested_at = now
            self.session.flush()
            return existing
        approval = ApprovalRequest(
            entity_type=entity_type,
            entity_id=entity_id,
            kind=kind,
            status=PENDING,
            requested_by=requested_by.email,
            requested_at=now,
            old_values=old_values,
            proposed_values=proposed_values,
        )
        self.session.add(approval)
        self.session.flush()
        return approval

    def get(self, request_id: uuid.UUID) -> ApprovalRequest:
        approval = self.session.get(ApprovalRequest, request_id)
        if approval is None:
            raise EntityNotFoundError("Freigabe-Anfrage nicht gefunden")
        return approval

    def list_requests(self, status: str | None = PENDING) -> list[ApprovalRequest]:
        query = select(ApprovalRequest).order_by(ApprovalRequest.requested_at.desc())
        if status is not None:
            query = query.where(ApprovalRequest.status == status)
        return list(self.session.scalars(query).all())

    def pending_for(self, entity_type: str, entity_id: uuid.UUID) -> list[ApprovalRequest]:
        return list(
            self.session.scalars(
                select(ApprovalRequest).where(
                    ApprovalRequest.entity_type == entity_type,
                    ApprovalRequest.entity_id == entity_id,
                    ApprovalRequest.status == PENDING,
                )
            ).all()
        )

    def entity_label(self, approval: ApprovalRequest) -> str | None:
        if approval.entity_type == "client_company":
            client = self.session.get(ClientCompany, approval.entity_id)
            return client.name if client else None
        if approval.entity_type in ("fee", "staffing_invoice"):  # NOMICON: staffing_invoice
            return str((approval.proposed_values or {}).get("label") or "Rechnung")
        return None

    def approve(self, request_id: uuid.UUID, admin: User) -> ApprovalRequest:
        approval = self._pending(request_id)
        if approval.kind == "new_client":
            client = self._client(approval)
            client.approval_pending = False
        elif approval.kind == "honorar_change":
            client = self._client(approval)
            for key, value in (approval.proposed_values or {}).items():
                if key in HONORAR_FIELDS:
                    setattr(client, key, _from_json(client, key, value))
        elif approval.kind == "invoice_issue" and approval.entity_type == "staffing_invoice":
            # NOMICON: Rechnung der Arbeitnehmerueberlassung (services/staffing_invoices.py)
            from cc_crm.services.staffing_invoices import apply_staffing_invoice_issue

            apply_staffing_invoice_issue(self.session, approval)
        elif approval.kind == "invoice_issue":
            from cc_crm.services.invoices import apply_invoice_status

            fee = self.session.get(Fee, approval.entity_id)
            if fee is None:
                raise EntityNotFoundError("Rechnung nicht gefunden")
            if fee.invoice_status != InvoiceStatus.DRAFT:
                raise ConflictError("Die Rechnung ist nicht mehr im Entwurf.")
            apply_invoice_status(fee, InvoiceStatus.ISSUED, approval.proposed_values or {})
        else:
            raise BusinessRuleError(f"Unbekannte Freigabe-Art: {approval.kind}")
        self._decide(approval, APPROVED, admin, None)
        return approval

    def reject(
        self, request_id: uuid.UUID, admin: User, decision_note: str | None
    ) -> ApprovalRequest:
        approval = self._pending(request_id)
        if approval.kind == "new_client":
            # Nicht loeschen (koennte schon mit Prozessen/Kontakten verknuepft
            # sein) - als gesperrt markieren, bleibt nachvollziehbar.
            client = self._client(approval)
            client.approval_pending = False
            client.status = ClientStatus.BLOCKED
        self._decide(approval, REJECTED, admin, decision_note)
        return approval

    def _pending(self, request_id: uuid.UUID) -> ApprovalRequest:
        approval = self.get(request_id)
        if approval.status != PENDING:
            raise ConflictError("Diese Anfrage wurde bereits entschieden.")
        return approval

    def _client(self, approval: ApprovalRequest) -> ClientCompany:
        client = self.session.get(ClientCompany, approval.entity_id)
        if client is None:
            raise EntityNotFoundError("Kanzlei nicht gefunden")
        return client

    def _decide(
        self, approval: ApprovalRequest, status: str, admin: User, note: str | None
    ) -> None:
        now = datetime.now(UTC)
        approval.status = status
        approval.decided_by = admin.email
        approval.decided_at = now
        approval.decision_note = note
        self.audit_logs.create(
            {
                "entity_type": approval.entity_type,
                "entity_id": approval.entity_id,
                "action": status,
                "changed_at": now,
                "changed_by": admin.email,
                "old_values": approval.old_values,
                "new_values": {
                    "kind": approval.kind,
                    "requested_by": approval.requested_by,
                    **(approval.proposed_values or {}),
                    **({"decision_note": note} if note else {}),
                },
            }
        )
        self.session.commit()


def _from_json(client: ClientCompany, key: str, value: Any) -> Any:
    """proposed_values sind JSON (Decimal/Enum als String) - zurueck in den
    Spaltentyp wandeln, den das Modell erwartet."""
    if value is None:
        return None
    column_type = ClientCompany.__table__.columns[key].type
    python_type = column_type.python_type
    if isinstance(value, python_type):
        return value
    return python_type(value)
