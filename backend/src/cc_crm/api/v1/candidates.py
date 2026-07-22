import uuid
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Query, Response, status

from cc_crm.api.dependencies import AdminUser, CurrentUser, DatabaseSession
from cc_crm.models.enums import CandidateStatus
from cc_crm.schemas.candidate import (
    CandidateCreate,
    CandidateRead,
    CandidateUpdate,
    CvExtractionRequest,
    CvExtractionSuggestion,
)
from cc_crm.schemas.pagination import Page
from cc_crm.schemas.submission import (
    CandidateQuickLogCreate,
    CandidateQuickLogResult,
    CandidateStageSummary,
    CandidateSubmissionRead,
)
from cc_crm.services.candidates import CandidateService
from cc_crm.services.cv_extraction import extract_text_from_bytes
from cc_crm.services.operational import DocumentService
from cc_crm.services.recruiting import RecruitingProcessService
from cc_crm.services.storage import read_document_bytes
from cc_crm.services.submissions import CandidateSubmissionService

router = APIRouter(prefix="/candidates")


@router.get("", response_model=Page[CandidateRead])
def list_candidates(
    session: DatabaseSession,
    candidate_status: Annotated[CandidateStatus | None, Query(alias="status")] = None,
    role: str | None = None,
    region: str | None = None,
    search: str | None = None,
    owner_user_id: uuid.UUID | None = None,
    created_from: datetime | None = None,
    created_to: datetime | None = None,
    offset: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
) -> Page[CandidateRead]:
    # owner_user_id ist ein reiner Komfort-Filter ("Meine Kandidaten") - ohne
    # ihn sehen weiterhin alle Nutzer alle Kandidaten, keine Sichtbarkeitsgrenze.
    entities, total = CandidateService(session).list_filtered(
        status=candidate_status,
        role=role,
        region=region,
        search=search,
        owner_user_id=owner_user_id,
        created_from=created_from,
        created_to=created_to,
        offset=offset,
        limit=limit,
    )
    items = [CandidateRead.model_validate(candidate) for candidate in entities]
    return Page(items=items, total_count=total, limit=limit, offset=offset)


@router.post("", response_model=CandidateRead, status_code=status.HTTP_201_CREATED)
def create_candidate(
    payload: CandidateCreate,
    session: DatabaseSession,
    current_user: CurrentUser,
) -> CandidateRead:
    if payload.owner_user_id is None:
        payload = payload.model_copy(update={"owner_user_id": current_user.id})
    return CandidateRead.model_validate(CandidateService(session).create(payload))


# Muss vor /{candidate_id} registriert sein, sonst faengt die Path-Param-Route
# "reactivation-list" als ungueltige candidate_id ab.
@router.get("/reactivation-list", response_model=list[CandidateRead])
def list_reactivation_candidates(
    session: DatabaseSession,
    threshold_months: Annotated[int | None, Query(ge=1)] = None,
) -> list[CandidateRead]:
    candidates = CandidateService(session).reactivation_candidates(threshold_months)
    return [CandidateRead.model_validate(candidate) for candidate in candidates]


@router.get("/{candidate_id}", response_model=CandidateRead)
def get_candidate(candidate_id: uuid.UUID, session: DatabaseSession) -> CandidateRead:
    return CandidateRead.model_validate(CandidateService(session).get(candidate_id))


@router.patch("/{candidate_id}", response_model=CandidateRead)
def update_candidate(
    candidate_id: uuid.UUID,
    payload: CandidateUpdate,
    session: DatabaseSession,
) -> CandidateRead:
    return CandidateRead.model_validate(CandidateService(session).update(candidate_id, payload))


@router.delete("/{candidate_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_candidate(
    candidate_id: uuid.UUID, session: DatabaseSession, current_user: CurrentUser
) -> Response:
    CandidateService(session).delete(candidate_id, current_user)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/{candidate_id}/anonymize", response_model=CandidateRead)
def anonymize_candidate(
    candidate_id: uuid.UUID, session: DatabaseSession, admin: AdminUser
) -> CandidateRead:
    """Admin-only, technische DSGVO-Vorbereitung (Punkt 4 des Auftrags,
    keine Rechtsberatung) - siehe CandidateService.anonymize."""
    return CandidateRead.model_validate(CandidateService(session).anonymize(candidate_id, admin))


@router.get("/{candidate_id}/submissions", response_model=list[CandidateSubmissionRead])
def list_candidate_submissions(
    candidate_id: uuid.UUID,
    session: DatabaseSession,
    offset: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
) -> list[CandidateSubmissionRead]:
    return [
        CandidateSubmissionRead.model_validate(submission)
        for submission in CandidateSubmissionService(session).list_for_candidate(
            candidate_id, offset=offset, limit=limit
        )
    ]


@router.post("/{candidate_id}/quick-log", response_model=CandidateQuickLogResult)
def quick_log_candidate_stage(
    candidate_id: uuid.UUID,
    payload: CandidateQuickLogCreate,
    session: DatabaseSession,
) -> CandidateQuickLogResult:
    """Pitch-/Quali-Call-Notiz anlegen - startet dabei bei Bedarf automatisch
    einen Prozess (siehe RecruitingProcessService.quick_log), ohne dass vorher
    eine separate "Prozess erstellen"-Aktion noetig ist."""
    return RecruitingProcessService(session).quick_log(candidate_id, payload)


@router.get("/{candidate_id}/stage-summary", response_model=CandidateStageSummary)
def get_candidate_stage_summary(
    candidate_id: uuid.UUID, session: DatabaseSession
) -> CandidateStageSummary:
    return RecruitingProcessService(session).stage_summary(candidate_id)


@router.post("/{candidate_id}/cv-extraction", response_model=CvExtractionSuggestion)
def extract_cv_fields(
    candidate_id: uuid.UUID,
    payload: CvExtractionRequest,
    session: DatabaseSession,
) -> CvExtractionSuggestion:
    document = DocumentService(session).get(uuid.UUID(payload.document_id))
    content = read_document_bytes(document.storage_key)
    cv_text = extract_text_from_bytes(document.filename, content)
    return CandidateService(session).suggest_cv_fields(candidate_id, cv_text)
