import uuid
from datetime import datetime
from typing import Annotated, Literal

from fastapi import APIRouter, Query, Response, status

from cc_crm.api.dependencies import CurrentUser, DatabaseSession
from cc_crm.models.enums import ClientStatus
from cc_crm.schemas.client_company import (
    ClientCompanyCreate,
    ClientCompanyRead,
    ClientCompanyUpdate,
    ClientDistanceResult,
    ClientDuplicateCandidate,
    ClientsNearCandidateResult,
)
from cc_crm.schemas.pagination import Page
from cc_crm.services.client_grouping import ClientGroupingService
from cc_crm.services.clients import ClientCompanyService

router = APIRouter(prefix="/clients")


@router.get("", response_model=Page[ClientCompanyRead])
def list_clients(
    session: DatabaseSession,
    client_status: Annotated[ClientStatus | None, Query(alias="status")] = None,
    region: str | None = None,
    search: str | None = None,
    owner_user_id: uuid.UUID | None = None,
    created_from: datetime | None = None,
    created_to: datetime | None = None,
    sort_by: Annotated[
        Literal["name", "region", "company_size", "focus", "last_contact_at", "fee_percentage"]
        | None,
        Query(),
    ] = None,
    sort_dir: Annotated[Literal["asc", "desc"], Query()] = "asc",
    offset: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
) -> Page[ClientCompanyRead]:
    # owner_user_id ist ein reiner Komfort-Filter ("Meine Kanzleien") - ohne
    # ihn sehen weiterhin alle Nutzer alle Kanzleien, keine Sichtbarkeitsgrenze.
    entities, total = ClientCompanyService(session).clients.filtered(
        status=client_status,
        region=region,
        search=search,
        owner_user_id=owner_user_id,
        created_from=created_from,
        created_to=created_to,
        sort_by=sort_by,
        sort_dir=sort_dir,
        offset=offset,
        limit=limit,
    )
    items = [ClientCompanyRead.model_validate(client) for client in entities]
    return Page(items=items, total_count=total, limit=limit, offset=offset)


@router.get("/check-duplicate", response_model=list[ClientDuplicateCandidate])
def check_duplicate_client(
    session: DatabaseSession,
    name: str,
    postal_code: str | None = None,
    exclude_id: uuid.UUID | None = None,
) -> list[ClientDuplicateCandidate]:
    """Warnt vor wahrscheinlich schon vorhandenen Kanzleien mit ähnlichem
    Namen - blockiert nichts, da mehrere Standorte derselben Marke (z.B.
    Ecovis, Afileon, PWC) ausdrücklich erwünscht sind."""
    matches = ClientCompanyService(session).find_potential_duplicates(
        name=name, postal_code=postal_code, exclude_id=exclude_id
    )
    return [
        ClientDuplicateCandidate(
            id=str(client.id),
            name=client.name,
            kanzleigruppe=client.kanzleigruppe,
            city=client.city,
            postal_code=client.postal_code,
            similarity=round(score, 2),
            same_location=same_location,
        )
        for client, score, same_location in matches
    ]


@router.get("/near-candidate/{candidate_id}", response_model=ClientsNearCandidateResult)
def list_clients_near_candidate(
    candidate_id: uuid.UUID,
    session: DatabaseSession,
    # Gleiche Stufen/Grenzen wie der bestehende Kandidaten-Umkreisfilter
    # (siehe api/v1/candidates.py::list_candidates::radius_km).
    radius_km: Annotated[int, Query(ge=1, le=500)],
    client_status: Annotated[ClientStatus | None, Query(alias="status")] = None,
) -> ClientsNearCandidateResult:
    """Kanzleien im Umkreis eines Kandidaten (Zentrum: dessen PLZ/Ort) -
    eigenstaendiger Endpunkt, kein Kettenauftrag mit Profil-Erzeugung/
    Mailversand (siehe services/clients.py::ClientCompanyService.
    list_near_candidate fuer die Begruendung)."""
    in_radius, unresolved = ClientCompanyService(session).list_near_candidate(
        candidate_id, radius_km=radius_km, status=client_status
    )
    return ClientsNearCandidateResult(
        candidate_id=candidate_id,
        radius_km=radius_km,
        in_radius=[
            ClientDistanceResult(
                client=ClientCompanyRead.model_validate(client), distance_km=round(distance, 1)
            )
            for client, distance in in_radius
        ],
        unresolved=[ClientCompanyRead.model_validate(client) for client in unresolved],
    )


@router.post("", response_model=ClientCompanyRead, status_code=status.HTTP_201_CREATED)
def create_client(
    payload: ClientCompanyCreate,
    session: DatabaseSession,
    current_user: CurrentUser,
) -> ClientCompanyRead:
    if payload.owner_user_id is None:
        payload = payload.model_copy(update={"owner_user_id": current_user.id})
    return ClientCompanyRead.model_validate(ClientCompanyService(session).create(payload))


@router.get("/{client_id}", response_model=ClientCompanyRead)
def get_client(client_id: uuid.UUID, session: DatabaseSession) -> ClientCompanyRead:
    return ClientCompanyRead.model_validate(ClientCompanyService(session).get(client_id))


@router.get("/{client_id}/group-locations", response_model=list[ClientCompanyRead])
def list_group_locations(client_id: uuid.UUID, session: DatabaseSession) -> list[ClientCompanyRead]:
    """Andere Standorte derselben Kanzleigruppe (leer, falls keine
    Kanzleigruppe gesetzt ist oder es der einzige Standort ist)."""
    client = ClientCompanyService(session).get(client_id)
    if not client.kanzleigruppe:
        return []
    locations = ClientGroupingService(session).group_locations(
        client.kanzleigruppe, exclude_id=client_id
    )
    return [ClientCompanyRead.model_validate(item) for item in locations]


@router.patch("/{client_id}", response_model=ClientCompanyRead)
def update_client(
    client_id: uuid.UUID,
    payload: ClientCompanyUpdate,
    session: DatabaseSession,
) -> ClientCompanyRead:
    return ClientCompanyRead.model_validate(
        ClientCompanyService(session).update(client_id, payload)
    )


@router.delete("/{client_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_client(
    client_id: uuid.UUID, session: DatabaseSession, current_user: CurrentUser
) -> Response:
    ClientCompanyService(session).delete(client_id, current_user)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
