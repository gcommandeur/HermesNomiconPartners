from fastapi import APIRouter

from cc_crm.api.dependencies import DatabaseSession
from cc_crm.schemas.search import NlSearchRequest, NlSearchResponse
from cc_crm.services.nl_search import NlSearchService

router = APIRouter(prefix="/candidates")


@router.post("/nl-search", response_model=NlSearchResponse)
def nl_search_candidates(payload: NlSearchRequest, session: DatabaseSession) -> NlSearchResponse:
    return NlSearchService(session).search(payload.query)
