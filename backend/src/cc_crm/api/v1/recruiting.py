import uuid
from typing import Annotated

from fastapi import APIRouter, Query, status

from cc_crm.api.dependencies import DatabaseSession
from cc_crm.schemas.recruiting import (
    AuditLogRead,
    FeeCreate,
    FeedbackRead,
    FeeRead,
    InterviewRead,
    OfferRead,
    PlacementRead,
)
from cc_crm.services.recruiting import RecruitingProcessService

router = APIRouter()


@router.get("/feedback", response_model=list[FeedbackRead])
def list_all_feedback(
    session: DatabaseSession,
    offset: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
) -> list[FeedbackRead]:
    service = RecruitingProcessService(session)
    return [
        FeedbackRead.model_validate(item)
        for item in service.feedback.list(offset=offset, limit=limit)
    ]


@router.get("/interviews", response_model=list[InterviewRead])
def list_all_interviews(session: DatabaseSession) -> list[InterviewRead]:
    service = RecruitingProcessService(session)
    return [InterviewRead.model_validate(item) for item in service.interviews.list()]


@router.get("/offers", response_model=list[OfferRead])
def list_all_offers(session: DatabaseSession) -> list[OfferRead]:
    service = RecruitingProcessService(session)
    return [OfferRead.model_validate(item) for item in service.offers.list()]


@router.get("/placements", response_model=list[PlacementRead])
def list_all_placements(session: DatabaseSession) -> list[PlacementRead]:
    service = RecruitingProcessService(session)
    return [PlacementRead.model_validate(item) for item in service.placements.list()]


@router.get("/placements/active-warranties", response_model=list[PlacementRead])
def list_active_warranties(session: DatabaseSession) -> list[PlacementRead]:
    """Uebersicht "Laufende Gewaehrleistungen": Placements mit Status LAUFEND
    oder BALD_ABLAUFEND, sortiert nach dem naechstliegenden Ablaufdatum."""
    service = RecruitingProcessService(session)
    return [
        PlacementRead.model_validate(placement)
        for placement, _end_date, _status in service.warranty.active_warranties()
    ]


@router.get("/fees", response_model=list[FeeRead])
def list_fees(session: DatabaseSession) -> list[FeeRead]:
    service = RecruitingProcessService(session)
    return [FeeRead.model_validate(item) for item in service.fees.list()]


@router.post(
    "/placements/{placement_id}/fees",
    response_model=FeeRead,
    status_code=status.HTTP_201_CREATED,
)
def create_fee(
    placement_id: uuid.UUID,
    payload: FeeCreate,
    session: DatabaseSession,
) -> FeeRead:
    return FeeRead.model_validate(
        RecruitingProcessService(session).create_fee(placement_id, payload)
    )


@router.get("/audit-logs", response_model=list[AuditLogRead])
def list_audit_logs(session: DatabaseSession) -> list[AuditLogRead]:
    service = RecruitingProcessService(session)
    return [AuditLogRead.model_validate(item) for item in service.audit.list()]
