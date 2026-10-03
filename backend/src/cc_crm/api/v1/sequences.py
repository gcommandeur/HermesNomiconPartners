import uuid

from fastapi import APIRouter, status

from cc_crm.api.dependencies import AdminUser, CurrentUser, DatabaseSession
from cc_crm.schemas.outreach import (
    EnrollmentCreate,
    EnrollmentRead,
    EnrollmentStop,
    SequenceCreate,
    SequenceRead,
    SequenceUpdate,
)
from cc_crm.services.outreach_sequences import EnrollmentService, SequenceService

router = APIRouter()

# Sequenzen anlegen/aendern ist Admin-Sache (Firmenkommunikation, Mailtexte,
# die automatisch im Namen der Mitarbeiter rausgehen). Ansehen und einschreiben
# darf jeder: Kandidaten sind der gemeinsame Pool der Agentur.


@router.get("/sequences", response_model=list[SequenceRead])
def list_sequences(
    session: DatabaseSession, current_user: CurrentUser, include_inactive: bool = False
) -> list[SequenceRead]:
    service = SequenceService(session)
    # Deaktivierte Sequenzen sieht nur ein Admin (zum Bearbeiten/Reaktivieren).
    only_active = not (include_inactive and current_user.is_admin)
    return [service.to_read(item) for item in service.list(only_active=only_active)]


@router.post("/sequences", response_model=SequenceRead, status_code=status.HTTP_201_CREATED)
def create_sequence(
    payload: SequenceCreate, session: DatabaseSession, _admin: AdminUser
) -> SequenceRead:
    service = SequenceService(session)
    return service.to_read(service.create(payload))


@router.patch("/sequences/{sequence_id}", response_model=SequenceRead)
def update_sequence(
    sequence_id: uuid.UUID,
    payload: SequenceUpdate,
    session: DatabaseSession,
    _admin: AdminUser,
) -> SequenceRead:
    service = SequenceService(session)
    return service.to_read(service.update(sequence_id, payload))


@router.post(
    "/sequence-enrollments",
    response_model=EnrollmentRead,
    status_code=status.HTTP_201_CREATED,
)
def enroll_candidate(
    payload: EnrollmentCreate, session: DatabaseSession, current_user: CurrentUser
) -> EnrollmentRead:
    service = EnrollmentService(session)
    enrollment = service.enroll(payload.sequence_id, payload.candidate_id, current_user)
    return service.to_read(enrollment)


@router.get(
    "/candidates/{candidate_id}/sequence-enrollments", response_model=list[EnrollmentRead]
)
def list_candidate_enrollments(
    candidate_id: uuid.UUID, session: DatabaseSession, _user: CurrentUser
) -> list[EnrollmentRead]:
    service = EnrollmentService(session)
    return [service.to_read(item) for item in service.for_candidate(candidate_id)]


@router.post("/sequence-enrollments/{enrollment_id}/stop", response_model=EnrollmentRead)
def stop_enrollment(
    enrollment_id: uuid.UUID,
    session: DatabaseSession,
    current_user: CurrentUser,
    payload: EnrollmentStop | None = None,
) -> EnrollmentRead:
    service = EnrollmentService(session)
    enrollment = service.stop(enrollment_id, current_user, payload.reason if payload else None)
    return service.to_read(enrollment)
