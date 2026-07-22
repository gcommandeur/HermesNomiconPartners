import uuid
from typing import Annotated

from fastapi import APIRouter, Query

from cc_crm.api.dependencies import CurrentUser, DatabaseSession
from cc_crm.models.enums import SourcingLeadStatus
from cc_crm.schemas.pagination import Page
from cc_crm.schemas.sourcing import SourcingLeadRead
from cc_crm.services.sourcing import SourcingService

router = APIRouter(prefix="/sourcing")


@router.get("/leads", response_model=Page[SourcingLeadRead])
def list_sourcing_leads(
    session: DatabaseSession,
    lead_status: Annotated[SourcingLeadStatus | None, Query(alias="status")] = None,
    offset: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
) -> Page[SourcingLeadRead]:
    leads, total = SourcingService(session).list_leads(
        status=lead_status, offset=offset, limit=limit
    )
    items = [SourcingLeadRead.model_validate(lead) for lead in leads]
    return Page(items=items, total_count=total, limit=limit, offset=offset)


@router.post("/leads/{lead_id}/approve", response_model=SourcingLeadRead)
def approve_sourcing_lead(
    lead_id: uuid.UUID, session: DatabaseSession, current_user: CurrentUser
) -> SourcingLeadRead:
    """Uebernimmt den Lead als echten Kandidaten (menschliche Bestaetigung -
    erst hier verlassen die Daten die Review-Ebene, siehe SourcingService)."""
    return SourcingLeadRead.model_validate(
        SourcingService(session).approve_lead(lead_id, current_user.id)
    )


@router.post("/leads/{lead_id}/reject", response_model=SourcingLeadRead)
def reject_sourcing_lead(
    lead_id: uuid.UUID, session: DatabaseSession, current_user: CurrentUser
) -> SourcingLeadRead:
    return SourcingLeadRead.model_validate(
        SourcingService(session).reject_lead(lead_id, current_user.id)
    )
