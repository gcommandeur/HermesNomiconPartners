"""Claude-Vorschlaege: Inbox fuer Menschen (siehe services/ai_proposals.py).

Nur mit normaler Anmeldung - ein MCP-API-Schluessel erreicht nur /api/v1/mcp
(api/dependencies.py) und kann hier also weder freigeben noch ablehnen."""

import uuid

from fastapi import APIRouter

from cc_crm.api.dependencies import CurrentUser, DatabaseSession
from cc_crm.schemas.ai_proposal import (
    AiProposalApprove,
    AiProposalRead,
    AiProposalReject,
    AiProposalSummary,
    ProposalStatus,
)
from cc_crm.services.ai_proposals import AiProposalService, ai_enabled

router = APIRouter(prefix="/ai-proposals")


@router.get("/summary", response_model=AiProposalSummary)
def proposal_summary(session: DatabaseSession, current_user: CurrentUser) -> AiProposalSummary:
    """Fuer die Seitenleiste: ist die Claude-Schnittstelle an, und wie viele
    Vorschlaege warten (nur die fuer den Nutzer sichtbaren)."""
    enabled = ai_enabled()
    pending = AiProposalService(session).pending_count(current_user) if enabled else 0
    return AiProposalSummary(enabled=enabled, pending=pending)


@router.get("", response_model=list[AiProposalRead])
def list_proposals(
    session: DatabaseSession,
    current_user: CurrentUser,
    status: ProposalStatus | None = None,
    limit: int = 100,
) -> list[AiProposalRead]:
    service = AiProposalService(session)
    return service.to_read(
        service.list_visible(current_user, status=status, limit=min(max(limit, 1), 200))
    )


@router.post("/{proposal_id}/approve", response_model=AiProposalRead)
def approve_proposal(
    proposal_id: uuid.UUID,
    payload: AiProposalApprove,
    session: DatabaseSession,
    current_user: CurrentUser,
) -> AiProposalRead:
    service = AiProposalService(session)
    proposal = service.approve(current_user, proposal_id, payload.payload)
    return service.to_read([proposal])[0]


@router.post("/{proposal_id}/reject", response_model=AiProposalRead)
def reject_proposal(
    proposal_id: uuid.UUID,
    payload: AiProposalReject,
    session: DatabaseSession,
    current_user: CurrentUser,
) -> AiProposalRead:
    service = AiProposalService(session)
    proposal = service.reject(current_user, proposal_id, payload.decision_note)
    return service.to_read([proposal])[0]
