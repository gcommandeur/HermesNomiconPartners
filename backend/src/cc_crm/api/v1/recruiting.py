import uuid
from typing import Annotated

from fastapi import APIRouter, Query, status

from cc_crm.api.dependencies import (
    CurrentUser,
    DatabaseSession,
    PlacementAccess,
    process_owner_scope,
)
from cc_crm.core.errors import BusinessRuleError
from cc_crm.models.enums import InvoiceStatus
from cc_crm.models.recruiting import Interview, Offer, Placement, SubmissionFeedback
from cc_crm.schemas.recruiting import (
    FeeCreate,
    FeedbackRead,
    FeeRead,
    InterviewRead,
    OfferRead,
    PlacementRead,
)
from cc_crm.services.approvals import needs_approval
from cc_crm.services.recruiting import RecruitingProcessService

router = APIRouter()


@router.get("/feedback", response_model=list[FeedbackRead])
def list_all_feedback(
    session: DatabaseSession,
    current_user: CurrentUser,
    offset: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
) -> list[FeedbackRead]:
    service = RecruitingProcessService(session)
    return [
        FeedbackRead.model_validate(item)
        for item in service.list_scoped(
            SubmissionFeedback,
            process_owner_scope(current_user, session),
            offset=offset,
            limit=limit,
        )
    ]


@router.get("/interviews", response_model=list[InterviewRead])
def list_all_interviews(
    session: DatabaseSession, current_user: CurrentUser
) -> list[InterviewRead]:
    service = RecruitingProcessService(session)
    return [
        InterviewRead.model_validate(item)
        for item in service.list_scoped(Interview, process_owner_scope(current_user, session))
    ]


@router.get("/offers", response_model=list[OfferRead])
def list_all_offers(session: DatabaseSession, current_user: CurrentUser) -> list[OfferRead]:
    service = RecruitingProcessService(session)
    return [
        OfferRead.model_validate(item)
        for item in service.list_scoped(Offer, process_owner_scope(current_user, session))
    ]


@router.get("/placements", response_model=list[PlacementRead])
def list_all_placements(
    session: DatabaseSession, current_user: CurrentUser
) -> list[PlacementRead]:
    service = RecruitingProcessService(session)
    return [
        PlacementRead.model_validate(item)
        for item in service.list_scoped(Placement, process_owner_scope(current_user, session))
    ]


@router.get("/placements/active-warranties", response_model=list[PlacementRead])
def list_active_warranties(
    session: DatabaseSession, current_user: CurrentUser
) -> list[PlacementRead]:
    """Uebersicht "Laufende Gewaehrleistungen": Placements mit Status LAUFEND
    oder BALD_ABLAUFEND, sortiert nach dem naechstliegenden Ablaufdatum -
    fuer Nicht-Admins nur die eigener Prozesse."""
    service = RecruitingProcessService(session)
    scope = process_owner_scope(current_user, session)
    own_ids = service.submission_ids_for_owners(scope) if scope is not None else None
    return [
        PlacementRead.model_validate(placement)
        for placement, _end_date, _status in service.warranty.active_warranties()
        if own_ids is None or placement.submission_id in own_ids
    ]


@router.get("/fees", response_model=list[FeeRead])
def list_fees(session: DatabaseSession, current_user: CurrentUser) -> list[FeeRead]:
    service = RecruitingProcessService(session)
    return [
        FeeRead.model_validate(item)
        for item in service.list_fees_scoped(process_owner_scope(current_user, session))
    ]


@router.post(
    "/placements/{placement_id}/fees",
    dependencies=[PlacementAccess],
    response_model=FeeRead,
    status_code=status.HTTP_201_CREATED,
)
def create_fee(
    placement_id: uuid.UUID,
    payload: FeeCreate,
    session: DatabaseSession,
    current_user: CurrentUser,
) -> FeeRead:
    # Sonst liesse sich die Freigabe fuer "Rechnung stellen" umgehen, indem
    # die Fee direkt als gestellt angelegt wird.
    if needs_approval(current_user) and payload.invoice_status != InvoiceStatus.DRAFT:
        raise BusinessRuleError(
            "Neue Rechnungen starten als Entwurf - das Stellen erfordert eine Freigabe."
        )
    return FeeRead.model_validate(
        RecruitingProcessService(session).create_fee(placement_id, payload, current_user)
    )
