"""Admin-Endpunkte fuer die Loeschanfragen-Nachverfolgung (Art. 17 DSGVO,
Punkt 3 des Auftrags "5 Hoch-Punkte umsetzen")."""

import uuid
from typing import Annotated

from fastapi import APIRouter, Query

from cc_crm.api.dependencies import AdminUser, DatabaseSession
from cc_crm.schemas.deletion_request import DeletionRequestCreate, DeletionRequestRead
from cc_crm.services.deletion_requests import DeletionRequestService

router = APIRouter(prefix="/deletion-requests")


@router.get("", response_model=list[DeletionRequestRead])
def list_deletion_requests(
    session: DatabaseSession,
    _admin: AdminUser,
    open_only: Annotated[bool, Query()] = True,
) -> list[DeletionRequestRead]:
    service = DeletionRequestService(session)
    return service.list_open() if open_only else service.list_all()


@router.post("", response_model=DeletionRequestRead)
def create_deletion_request(
    payload: DeletionRequestCreate,
    session: DatabaseSession,
    _admin: AdminUser,
) -> DeletionRequestRead:
    return DeletionRequestService(session).create(payload.candidate_id, payload.requested_via)


@router.post("/{request_id}/complete", response_model=DeletionRequestRead)
def complete_deletion_request(
    request_id: uuid.UUID,
    session: DatabaseSession,
    admin: AdminUser,
) -> DeletionRequestRead:
    """Erledigt eine Loeschanfrage: ruft den bestehenden, unveraenderten
    Anonymisieren-Endpunkt (CandidateService.anonymize) auf und setzt
    anschliessend completed_at/completed_by_user_id."""
    return DeletionRequestService(session).complete(request_id, admin)
