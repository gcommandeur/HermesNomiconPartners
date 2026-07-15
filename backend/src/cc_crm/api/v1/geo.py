from fastapi import APIRouter

from cc_crm.api.dependencies import DatabaseSession
from cc_crm.schemas.geo import GeoMappingResult
from cc_crm.services.geo import GeoMappingService

router = APIRouter(prefix="/geo-mapping")


@router.get("/results", response_model=list[GeoMappingResult])
def geo_mapping_results(session: DatabaseSession) -> list[GeoMappingResult]:
    return GeoMappingService(session).results()
