import uuid
from typing import Annotated, Literal

from fastapi import APIRouter, Query

from cc_crm.api.dependencies import AdminUser, CurrentUser, DatabaseSession
from cc_crm.models.approval_request import ApprovalRequest
from cc_crm.schemas.approval import (
    ApprovalDecision,
    ApprovalRequestRead,
    InvoiceStatusChange,
    InvoiceStatusChangeResult,
)
from cc_crm.schemas.recruiting import FeeRead
from cc_crm.services.approvals import ApprovalService
from cc_crm.services.invoices import InvoiceService

router = APIRouter()


def _read(service: ApprovalService, approval: ApprovalRequest) -> ApprovalRequestRead:
    return ApprovalRequestRead.model_validate(approval).model_copy(
        update={"entity_label": service.entity_label(approval)}
    )


@router.get("/approval-requests", response_model=list[ApprovalRequestRead])
def list_approval_requests(
    session: DatabaseSession,
    _admin: AdminUser,
    status: Annotated[Literal["pending", "approved", "rejected"] | None, Query()] = "pending",
) -> list[ApprovalRequestRead]:
    service = ApprovalService(session)
    return [_read(service, item) for item in service.list_requests(status)]


@router.get(
    "/approval-requests/for/{entity_type}/{entity_id}",
    response_model=list[ApprovalRequestRead],
)
def pending_approvals_for_entity(
    entity_type: Literal["client_company", "fee"],
    entity_id: uuid.UUID,
    session: DatabaseSession,
    _user: CurrentUser,
) -> list[ApprovalRequestRead]:
    """Offene Anfragen zu einem Objekt - fuer den "Freigabe ausstehend"-
    Hinweis beim anfragenden Nutzer, daher nicht admin-only."""
    service = ApprovalService(session)
    return [_read(service, item) for item in service.pending_for(entity_type, entity_id)]


@router.post("/approval-requests/{request_id}/approve", response_model=ApprovalRequestRead)
def approve_request(
    request_id: uuid.UUID, session: DatabaseSession, admin: AdminUser
) -> ApprovalRequestRead:
    service = ApprovalService(session)
    return _read(service, service.approve(request_id, admin))


@router.post("/approval-requests/{request_id}/reject", response_model=ApprovalRequestRead)
def reject_request(
    request_id: uuid.UUID,
    payload: ApprovalDecision,
    session: DatabaseSession,
    admin: AdminUser,
) -> ApprovalRequestRead:
    service = ApprovalService(session)
    return _read(service, service.reject(request_id, admin, payload.decision_note))


@router.get("/placements/{placement_id}/fees", response_model=list[FeeRead])
def list_placement_fees(
    placement_id: uuid.UUID, session: DatabaseSession, _user: CurrentUser
) -> list[FeeRead]:
    return [
        FeeRead.model_validate(fee)
        for fee in InvoiceService(session).fees_for_placement(placement_id)
    ]


@router.post("/fees/{fee_id}/invoice-status", response_model=InvoiceStatusChangeResult)
def change_invoice_status(
    fee_id: uuid.UUID,
    payload: InvoiceStatusChange,
    session: DatabaseSession,
    current_user: CurrentUser,
) -> InvoiceStatusChangeResult:
    fee, approval = InvoiceService(session).change_status(fee_id, payload, current_user)
    return InvoiceStatusChangeResult(
        fee=FeeRead.model_validate(fee),
        approval_request=(
            _read(ApprovalService(session), approval) if approval is not None else None
        ),
    )
