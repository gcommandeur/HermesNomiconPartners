import uuid
from typing import Annotated

from fastapi import APIRouter, Query

from cc_crm.api.dependencies import DatabaseSession
from cc_crm.schemas.matching import BulkSubmitRequest, BulkSubmitResponse, ClientMatchRead
from cc_crm.services.matching import CandidateMatchingService

router = APIRouter(prefix="/candidates")


@router.get("/{candidate_id}/matches", response_model=list[ClientMatchRead])
def match_candidate_to_clients(
    candidate_id: uuid.UUID,
    session: DatabaseSession,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
) -> list[ClientMatchRead]:
    return CandidateMatchingService(session).find_matches(candidate_id, limit=limit)


@router.post("/{candidate_id}/bulk-submit", response_model=BulkSubmitResponse)
def bulk_submit_candidate(
    candidate_id: uuid.UUID,
    payload: BulkSubmitRequest,
    session: DatabaseSession,
) -> BulkSubmitResponse:
    return CandidateMatchingService(session).bulk_submit(candidate_id, payload)
