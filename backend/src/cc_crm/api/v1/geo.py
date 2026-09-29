from typing import Annotated

from fastapi import APIRouter, Query

from cc_crm.api.dependencies import DatabaseSession
from cc_crm.schemas.geo import GeocodeResult, GeoMappingResult
from cc_crm.services.geo import GeoMappingService, resolve_place_query

router = APIRouter(prefix="/geo-mapping")


@router.get("/results", response_model=list[GeoMappingResult])
def geo_mapping_results(session: DatabaseSession) -> list[GeoMappingResult]:
    return GeoMappingService(session).results()


@router.get("/geocode", response_model=GeocodeResult)
def geocode_place(
    session: DatabaseSession, query: Annotated[str, Query(min_length=1)]
) -> GeocodeResult:
    # Der Kanzleien-Umkreisfilter auf der Geo-Mapping-Seite berechnet
    # Distanzen clientseitig (geo-results-table.tsx) statt serverseitig wie
    # candidates.py/clients.py/vacancy_matching.py - der precise-Flag aus
    # resolve_place_query() ist daher fuer DIESEN Endpunkt kein Teil des
    # aktuellen Radius-Praezisions-Fixes (nicht im Auftrag benannt), bleibt
    # hier bewusst unveraendert bestehen statt die Response-Form zu aendern.
    latitude, longitude, _precise = resolve_place_query(session, query)
    return GeocodeResult(latitude=latitude, longitude=longitude)
