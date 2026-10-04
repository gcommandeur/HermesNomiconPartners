import uuid
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Query, Response, status

from cc_crm.api.dependencies import (
    AdminUser,
    CurrentUser,
    DatabaseSession,
    SubmissionAccess,
    process_owner_scope,
    shared_submission_ids,
    user_can_manage_shares,
)
from cc_crm.core.errors import PermissionDeniedError
from cc_crm.models.enums import SubmissionStatus
from cc_crm.schemas.pagination import Page
from cc_crm.schemas.recruiting import (
    FeedbackCreate,
    FeedbackRead,
    FeedbackUpdate,
    InterviewCreateRequest,
    InterviewRead,
    InterviewUpdate,
    OfferCreate,
    OfferRead,
    OfferUpdate,
    PlacementCreate,
    PlacementRead,
    PlacementUpdate,
)
from cc_crm.schemas.submission import (
    CandidateSubmissionCreate,
    CandidateSubmissionRead,
    CandidateSubmissionTransition,
    CandidateSubmissionUpdate,
    ClosingScoreInput,
    ClosingScoreRead,
    FeedbackCreateResult,
    SubmissionOwnerAssign,
    SubmissionShareCreate,
    SubmissionShareRead,
    UnownedSubmissionList,
)
from cc_crm.services.closing_score import ACTION_RECOMMENDATIONS
from cc_crm.services.recruiting import RecruitingProcessService
from cc_crm.services.submission_shares import SubmissionShareService
from cc_crm.services.submissions import CandidateSubmissionService

router = APIRouter(prefix="/submissions")


@router.get("", response_model=Page[CandidateSubmissionRead])
def list_submissions(
    session: DatabaseSession,
    current_user: CurrentUser,
    submission_status: Annotated[SubmissionStatus | None, Query(alias="status")] = None,
    candidate_id: uuid.UUID | None = None,
    client_id: uuid.UUID | None = None,
    job_id: uuid.UUID | None = None,
    owner_user_id: uuid.UUID | None = None,
    created_from: datetime | None = None,
    created_to: datetime | None = None,
    offset: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
) -> Page[CandidateSubmissionRead]:
    # Sichtbarkeitsgrenze: Nicht-Admins sehen nur Prozesse ihres Scopes
    # (Mitarbeiter: eigene; Teamleiter: eigene + die ihres Teams). Ein
    # explizites owner_user_id darf innerhalb des Scopes einschraenken
    # ("Meine Prozesse"), ein fremdes wird verworfen - sonst liesse sich die
    # Grenze per Query-Parameter umgehen. Fuer Admins bleibt owner_user_id der
    # optionale Filter.
    scope = process_owner_scope(current_user, session)
    owner_user_ids = scope
    # Freigaben (submission_shares) kommen additiv dazu - ausser bei einem
    # gueltigen Owner-Filter ("Meine Prozesse"), der bewusst einschraenkt.
    shared_ids = shared_submission_ids(current_user, session)
    if owner_user_id is not None and (scope is None or owner_user_id in scope):
        owner_user_ids = [owner_user_id]
        shared_ids = []
    service = CandidateSubmissionService(session)
    entities, total = service.submissions.filtered(
        status=submission_status,
        candidate_id=candidate_id,
        client_id=client_id,
        job_id=job_id,
        owner_user_ids=owner_user_ids,
        shared_submission_ids=shared_ids,
        created_from=created_from,
        created_to=created_to,
        offset=offset,
        limit=limit,
    )
    items = [CandidateSubmissionRead.model_validate(submission) for submission in entities]
    return Page(items=items, total_count=total, limit=limit, offset=offset)


# Muss VOR "/{submission_id}" stehen, sonst wird "without-owner" als (ungueltige) ID gelesen.
@router.get("/without-owner", response_model=UnownedSubmissionList)
def list_submissions_without_owner(
    session: DatabaseSession, _admin: AdminUser
) -> UnownedSubmissionList:
    """Nur Admin: Prozesse ohne Verantwortlichen (aus der Zeit vor dem Feld). Fuer
    Nicht-Admins sind sie unsichtbar - hier tauchen sie sichtbar auf, bis sie zugewiesen sind."""
    return CandidateSubmissionService(session).list_without_owner()


@router.post(
    "",
    response_model=CandidateSubmissionRead,
    status_code=status.HTTP_201_CREATED,
)
def create_submission(
    payload: CandidateSubmissionCreate,
    session: DatabaseSession,
    current_user: CurrentUser,
) -> CandidateSubmissionRead:
    if payload.owner_user_id is None:
        payload = payload.model_copy(update={"owner_user_id": current_user.id})
    return CandidateSubmissionRead.model_validate(
        CandidateSubmissionService(session).create(payload)
    )


@router.get("/priority-view", response_model=list[CandidateSubmissionRead])
def list_priority_view(
    session: DatabaseSession, current_user: CurrentUser
) -> list[CandidateSubmissionRead]:
    """Offene Prozesse sortiert nach closing_probability * erwartetem Honorar."""
    scope = process_owner_scope(current_user, session)
    shared_ids = set(shared_submission_ids(current_user, session))
    entities = CandidateSubmissionService(session).submissions.priority_candidates()
    return [
        CandidateSubmissionRead.model_validate(item)
        for item in entities
        if scope is None or item.owner_user_id in scope or item.id in shared_ids
    ]


@router.get(
    "/{submission_id}", dependencies=[SubmissionAccess], response_model=CandidateSubmissionRead
)
def get_submission(
    submission_id: uuid.UUID,
    session: DatabaseSession,
) -> CandidateSubmissionRead:
    return CandidateSubmissionRead.model_validate(
        CandidateSubmissionService(session).get(submission_id)
    )


@router.patch(
    "/{submission_id}", dependencies=[SubmissionAccess], response_model=CandidateSubmissionRead
)
def update_submission(
    submission_id: uuid.UUID,
    payload: CandidateSubmissionUpdate,
    session: DatabaseSession,
    current_user: CurrentUser,
) -> CandidateSubmissionRead:
    return CandidateSubmissionRead.model_validate(
        CandidateSubmissionService(session).update(submission_id, payload, current_user)
    )


@router.post(
    "/{submission_id}/assign-owner",
    dependencies=[SubmissionAccess],
    response_model=CandidateSubmissionRead,
)
def assign_submission_owner(
    submission_id: uuid.UUID,
    payload: SubmissionOwnerAssign,
    session: DatabaseSession,
    admin: AdminUser,
) -> CandidateSubmissionRead:
    """Nur Admin: Verantwortlichen setzen (Audit-Eintrag `updated` mit alt/neu)."""
    return CandidateSubmissionRead.model_validate(
        CandidateSubmissionService(session).assign_owner(
            submission_id, payload.owner_user_id, admin
        )
    )


@router.patch(
    "/{submission_id}/transition",
    dependencies=[SubmissionAccess],
    response_model=CandidateSubmissionRead,
)
def transition_submission(
    submission_id: uuid.UUID,
    payload: CandidateSubmissionTransition,
    session: DatabaseSession,
    current_user: CurrentUser,
) -> CandidateSubmissionRead:
    # changed_by war hier bisher IMMER None (Nutzer-Feedback "Änderungshistorie
    # im Kandidatenprofil sichtbar machen", Punkt 4) - der Kanban-Drag ist der
    # mit Abstand haeufigste Statuswechsel-Ausloeser, jeder resultierende
    # AuditLog-Eintrag ("status_changed") war dadurch keinem Menschen
    # zuzuordnen. Nur setzen, wenn der Aufrufer nicht bereits explizit einen
    # Wert mitgibt (z.B. ein spaeterer automatischer Ausloeser, der sich
    # selbst als "automatisch" kennzeichnen will statt einem Nutzer
    # zugeschrieben zu werden).
    if payload.changed_by is None:
        payload = payload.model_copy(update={"changed_by": current_user.email})
    return CandidateSubmissionRead.model_validate(
        CandidateSubmissionService(session).transition(submission_id, payload)
    )


@router.post(
    "/{submission_id}/archive",
    dependencies=[SubmissionAccess],
    response_model=CandidateSubmissionRead,
)
def archive_submission(
    submission_id: uuid.UUID, session: DatabaseSession, current_user: CurrentUser
) -> CandidateSubmissionRead:
    """Expliziter Abschluss NACH einem Placement - blendet den Prozess aus
    dem Kanban aus, ohne Status/Historie anzufassen (siehe services/
    submissions.py::CandidateSubmissionService.archive). Nur ab
    status=='placement' erlaubt."""
    return CandidateSubmissionRead.model_validate(
        CandidateSubmissionService(session).archive(submission_id, current_user)
    )


@router.post(
    "/{submission_id}/unarchive",
    dependencies=[SubmissionAccess],
    response_model=CandidateSubmissionRead,
)
def unarchive_submission(
    submission_id: uuid.UUID, session: DatabaseSession, current_user: CurrentUser
) -> CandidateSubmissionRead:
    return CandidateSubmissionRead.model_validate(
        CandidateSubmissionService(session).unarchive(submission_id, current_user)
    )


@router.patch(
    "/{submission_id}/closing-score",
    dependencies=[SubmissionAccess],
    response_model=ClosingScoreRead,
)
def update_closing_score(
    submission_id: uuid.UUID,
    payload: ClosingScoreInput,
    session: DatabaseSession,
) -> ClosingScoreRead:
    updated = CandidateSubmissionService(session).update_closing_score(submission_id, payload)
    assert updated.closing_probability is not None
    assert updated.closing_status is not None
    return ClosingScoreRead(
        closing_probability=updated.closing_probability,
        closing_status=updated.closing_status,
        action_recommendation=ACTION_RECOMMENDATIONS[updated.closing_status],
    )


@router.get(
    "/{submission_id}/feedback", dependencies=[SubmissionAccess], response_model=list[FeedbackRead]
)
def list_feedback(submission_id: uuid.UUID, session: DatabaseSession) -> list[FeedbackRead]:
    return [
        FeedbackRead.model_validate(item)
        for item in RecruitingProcessService(session).list_feedback(submission_id)
    ]


@router.post(
    "/{submission_id}/feedback",
    dependencies=[SubmissionAccess],
    response_model=FeedbackCreateResult,
    status_code=status.HTTP_201_CREATED,
)
def create_feedback(
    submission_id: uuid.UUID,
    payload: FeedbackCreate,
    session: DatabaseSession,
    current_user: CurrentUser,
) -> FeedbackCreateResult:
    service = RecruitingProcessService(session)
    feedback = service.create_feedback(submission_id, payload, changed_by=current_user.email)
    submission = service.submissions.get(submission_id)
    return FeedbackCreateResult(
        feedback=FeedbackRead.model_validate(feedback),
        submission=CandidateSubmissionRead.model_validate(submission),
    )


@router.patch(
    "/{submission_id}/feedback/{feedback_id}",
    dependencies=[SubmissionAccess],
    response_model=FeedbackRead,
)
def update_feedback(
    submission_id: uuid.UUID,
    feedback_id: uuid.UUID,
    payload: FeedbackUpdate,
    session: DatabaseSession,
) -> FeedbackRead:
    return FeedbackRead.model_validate(
        RecruitingProcessService(session).update_feedback(submission_id, feedback_id, payload)
    )


@router.delete(
    "/{submission_id}/feedback/{feedback_id}",
    dependencies=[SubmissionAccess],
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_feedback(
    submission_id: uuid.UUID,
    feedback_id: uuid.UUID,
    session: DatabaseSession,
) -> Response:
    RecruitingProcessService(session).delete_feedback(submission_id, feedback_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get(
    "/{submission_id}/interviews",
    dependencies=[SubmissionAccess],
    response_model=list[InterviewRead],
)
def list_interviews(submission_id: uuid.UUID, session: DatabaseSession) -> list[InterviewRead]:
    return [
        InterviewRead.model_validate(item)
        for item in RecruitingProcessService(session).list_interviews(submission_id)
    ]


@router.post(
    "/{submission_id}/interviews",
    dependencies=[SubmissionAccess],
    response_model=InterviewRead,
    status_code=status.HTTP_201_CREATED,
)
def create_interview(
    submission_id: uuid.UUID,
    payload: InterviewCreateRequest,
    session: DatabaseSession,
    current_user: CurrentUser,
) -> InterviewRead:
    return InterviewRead.model_validate(
        RecruitingProcessService(session).create_interview(submission_id, payload, current_user)
    )


@router.patch(
    "/{submission_id}/interviews/{interview_id}",
    dependencies=[SubmissionAccess],
    response_model=InterviewRead,
)
def update_interview(
    submission_id: uuid.UUID,
    interview_id: uuid.UUID,
    payload: InterviewUpdate,
    session: DatabaseSession,
) -> InterviewRead:
    return InterviewRead.model_validate(
        RecruitingProcessService(session).update_interview(submission_id, interview_id, payload)
    )


@router.delete(
    "/{submission_id}/interviews/{interview_id}",
    dependencies=[SubmissionAccess],
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_interview(
    submission_id: uuid.UUID,
    interview_id: uuid.UUID,
    session: DatabaseSession,
) -> Response:
    RecruitingProcessService(session).delete_interview(submission_id, interview_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get(
    "/{submission_id}/offers", dependencies=[SubmissionAccess], response_model=list[OfferRead]
)
def list_offers(submission_id: uuid.UUID, session: DatabaseSession) -> list[OfferRead]:
    return [
        OfferRead.model_validate(item)
        for item in RecruitingProcessService(session).list_offers(submission_id)
    ]


@router.post(
    "/{submission_id}/offers",
    dependencies=[SubmissionAccess],
    response_model=OfferRead,
    status_code=status.HTTP_201_CREATED,
)
def create_offer(
    submission_id: uuid.UUID,
    payload: OfferCreate,
    session: DatabaseSession,
    current_user: CurrentUser,
) -> OfferRead:
    return OfferRead.model_validate(
        RecruitingProcessService(session).create_offer(submission_id, payload, current_user)
    )


@router.patch(
    "/{submission_id}/offers/{offer_id}", dependencies=[SubmissionAccess], response_model=OfferRead
)
def update_offer(
    submission_id: uuid.UUID,
    offer_id: uuid.UUID,
    payload: OfferUpdate,
    session: DatabaseSession,
) -> OfferRead:
    return OfferRead.model_validate(
        RecruitingProcessService(session).update_offer(submission_id, offer_id, payload)
    )


@router.delete(
    "/{submission_id}/offers/{offer_id}",
    dependencies=[SubmissionAccess],
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_offer(
    submission_id: uuid.UUID,
    offer_id: uuid.UUID,
    session: DatabaseSession,
) -> Response:
    RecruitingProcessService(session).delete_offer(submission_id, offer_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get(
    "/{submission_id}/placement", dependencies=[SubmissionAccess], response_model=PlacementRead
)
def get_placement(submission_id: uuid.UUID, session: DatabaseSession) -> PlacementRead:
    return PlacementRead.model_validate(
        RecruitingProcessService(session).get_placement(submission_id)
    )


@router.post(
    "/{submission_id}/placement",
    dependencies=[SubmissionAccess],
    response_model=PlacementRead,
    status_code=status.HTTP_201_CREATED,
)
def create_placement(
    submission_id: uuid.UUID,
    payload: PlacementCreate,
    session: DatabaseSession,
    current_user: CurrentUser,
) -> PlacementRead:
    return PlacementRead.model_validate(
        RecruitingProcessService(session).create_placement(submission_id, payload, current_user)
    )


@router.patch(
    "/{submission_id}/placement", dependencies=[SubmissionAccess], response_model=PlacementRead
)
def update_placement(
    submission_id: uuid.UUID,
    payload: PlacementUpdate,
    session: DatabaseSession,
) -> PlacementRead:
    # Placement ist singulaer (ein Objekt pro Submission) - kein :id-Segment
    # im Pfad, analog zum bestehenden GET/POST oben.
    return PlacementRead.model_validate(
        RecruitingProcessService(session).update_placement(submission_id, payload)
    )


@router.delete(
    "/{submission_id}/placement",
    dependencies=[SubmissionAccess],
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_placement(submission_id: uuid.UUID, session: DatabaseSession) -> Response:
    RecruitingProcessService(session).delete_placement(submission_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get(
    "/{submission_id}/shares",
    dependencies=[SubmissionAccess],
    response_model=list[SubmissionShareRead],
)
def list_shares(submission_id: uuid.UUID, session: DatabaseSession) -> list[SubmissionShareRead]:
    service = SubmissionShareService(session)
    return [service.to_read(item) for item in service.list_for_submission(submission_id)]


@router.post(
    "/{submission_id}/shares",
    dependencies=[SubmissionAccess],
    response_model=SubmissionShareRead,
    status_code=status.HTTP_201_CREATED,
)
def create_share(
    submission_id: uuid.UUID,
    payload: SubmissionShareCreate,
    session: DatabaseSession,
    current_user: CurrentUser,
) -> SubmissionShareRead:
    # SubmissionAccess (404 fuer Fremde) + Verwaltungsrecht: nur Eigentuemer,
    # dessen Teamleiter und Admins - ein Empfaenger darf nicht weiterteilen.
    # Doppelte Freigabe ist idempotent (siehe Service).
    if not user_can_manage_shares(session, current_user, submission_id):
        raise PermissionDeniedError("Nur Eigentuemer, Teamleiter oder Admins duerfen teilen.")
    service = SubmissionShareService(session)
    return service.to_read(service.create(submission_id, payload.shared_with_user_id, current_user))


@router.delete(
    "/{submission_id}/shares/{share_id}",
    dependencies=[SubmissionAccess],
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_share(
    submission_id: uuid.UUID,
    share_id: uuid.UUID,
    session: DatabaseSession,
    current_user: CurrentUser,
) -> Response:
    # Entziehen: Eigentuemer/Teamleiter/Admin - ein Empfaenger nur die EIGENE
    # Freigabe (Rueckgabe).
    service = SubmissionShareService(session)
    if not user_can_manage_shares(session, current_user, submission_id):
        share = service.get(submission_id, share_id)
        if share.shared_with_user_id != current_user.id:
            raise PermissionDeniedError("Nur die eigene Freigabe kann zurueckgegeben werden.")
    service.delete(submission_id, share_id, current_user)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.delete(
    "/{submission_id}", dependencies=[SubmissionAccess], status_code=status.HTTP_204_NO_CONTENT
)
def delete_submission(
    submission_id: uuid.UUID, session: DatabaseSession, current_user: CurrentUser
) -> Response:
    CandidateSubmissionService(session).delete(submission_id, current_user)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
