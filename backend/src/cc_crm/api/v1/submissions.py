import uuid
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Query, Response, status

from cc_crm.api.dependencies import CurrentUser, DatabaseSession
from cc_crm.models.enums import SubmissionStatus
from cc_crm.schemas.pagination import Page
from cc_crm.schemas.recruiting import (
    FeedbackCreate,
    FeedbackRead,
    FeedbackUpdate,
    InterviewCreate,
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
)
from cc_crm.services.closing_score import ACTION_RECOMMENDATIONS
from cc_crm.services.recruiting import RecruitingProcessService
from cc_crm.services.submissions import CandidateSubmissionService

router = APIRouter(prefix="/submissions")


@router.get("", response_model=Page[CandidateSubmissionRead])
def list_submissions(
    session: DatabaseSession,
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
    # owner_user_id ist ein reiner Komfort-Filter ("Meine Prozesse") - ohne
    # ihn sehen weiterhin alle Nutzer alle Prozesse, keine Sichtbarkeitsgrenze.
    service = CandidateSubmissionService(session)
    entities, total = service.submissions.filtered(
        status=submission_status,
        candidate_id=candidate_id,
        client_id=client_id,
        job_id=job_id,
        owner_user_id=owner_user_id,
        created_from=created_from,
        created_to=created_to,
        offset=offset,
        limit=limit,
    )
    items = [CandidateSubmissionRead.model_validate(submission) for submission in entities]
    return Page(items=items, total_count=total, limit=limit, offset=offset)


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
def list_priority_view(session: DatabaseSession) -> list[CandidateSubmissionRead]:
    """Offene Prozesse sortiert nach closing_probability * erwartetem Honorar."""
    entities = CandidateSubmissionService(session).submissions.priority_candidates()
    return [CandidateSubmissionRead.model_validate(item) for item in entities]


@router.get("/{submission_id}", response_model=CandidateSubmissionRead)
def get_submission(
    submission_id: uuid.UUID,
    session: DatabaseSession,
) -> CandidateSubmissionRead:
    return CandidateSubmissionRead.model_validate(
        CandidateSubmissionService(session).get(submission_id)
    )


@router.patch("/{submission_id}", response_model=CandidateSubmissionRead)
def update_submission(
    submission_id: uuid.UUID,
    payload: CandidateSubmissionUpdate,
    session: DatabaseSession,
) -> CandidateSubmissionRead:
    return CandidateSubmissionRead.model_validate(
        CandidateSubmissionService(session).update(submission_id, payload)
    )


@router.patch("/{submission_id}/transition", response_model=CandidateSubmissionRead)
def transition_submission(
    submission_id: uuid.UUID,
    payload: CandidateSubmissionTransition,
    session: DatabaseSession,
) -> CandidateSubmissionRead:
    return CandidateSubmissionRead.model_validate(
        CandidateSubmissionService(session).transition(submission_id, payload)
    )


@router.patch("/{submission_id}/closing-score", response_model=ClosingScoreRead)
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


@router.get("/{submission_id}/feedback", response_model=list[FeedbackRead])
def list_feedback(submission_id: uuid.UUID, session: DatabaseSession) -> list[FeedbackRead]:
    return [
        FeedbackRead.model_validate(item)
        for item in RecruitingProcessService(session).list_feedback(submission_id)
    ]


@router.post(
    "/{submission_id}/feedback",
    response_model=FeedbackCreateResult,
    status_code=status.HTTP_201_CREATED,
)
def create_feedback(
    submission_id: uuid.UUID,
    payload: FeedbackCreate,
    session: DatabaseSession,
) -> FeedbackCreateResult:
    service = RecruitingProcessService(session)
    feedback = service.create_feedback(submission_id, payload)
    submission = service.submissions.get(submission_id)
    return FeedbackCreateResult(
        feedback=FeedbackRead.model_validate(feedback),
        submission=CandidateSubmissionRead.model_validate(submission),
    )


@router.patch("/{submission_id}/feedback/{feedback_id}", response_model=FeedbackRead)
def update_feedback(
    submission_id: uuid.UUID,
    feedback_id: uuid.UUID,
    payload: FeedbackUpdate,
    session: DatabaseSession,
) -> FeedbackRead:
    return FeedbackRead.model_validate(
        RecruitingProcessService(session).update_feedback(submission_id, feedback_id, payload)
    )


@router.delete("/{submission_id}/feedback/{feedback_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_feedback(
    submission_id: uuid.UUID,
    feedback_id: uuid.UUID,
    session: DatabaseSession,
) -> Response:
    RecruitingProcessService(session).delete_feedback(submission_id, feedback_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/{submission_id}/interviews", response_model=list[InterviewRead])
def list_interviews(submission_id: uuid.UUID, session: DatabaseSession) -> list[InterviewRead]:
    return [
        InterviewRead.model_validate(item)
        for item in RecruitingProcessService(session).list_interviews(submission_id)
    ]


@router.post(
    "/{submission_id}/interviews",
    response_model=InterviewRead,
    status_code=status.HTTP_201_CREATED,
)
def create_interview(
    submission_id: uuid.UUID,
    payload: InterviewCreate,
    session: DatabaseSession,
    current_user: CurrentUser,
) -> InterviewRead:
    return InterviewRead.model_validate(
        RecruitingProcessService(session).create_interview(submission_id, payload, current_user)
    )


@router.patch("/{submission_id}/interviews/{interview_id}", response_model=InterviewRead)
def update_interview(
    submission_id: uuid.UUID,
    interview_id: uuid.UUID,
    payload: InterviewUpdate,
    session: DatabaseSession,
) -> InterviewRead:
    return InterviewRead.model_validate(
        RecruitingProcessService(session).update_interview(submission_id, interview_id, payload)
    )


@router.delete("/{submission_id}/interviews/{interview_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_interview(
    submission_id: uuid.UUID,
    interview_id: uuid.UUID,
    session: DatabaseSession,
) -> Response:
    RecruitingProcessService(session).delete_interview(submission_id, interview_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/{submission_id}/offers", response_model=list[OfferRead])
def list_offers(submission_id: uuid.UUID, session: DatabaseSession) -> list[OfferRead]:
    return [
        OfferRead.model_validate(item)
        for item in RecruitingProcessService(session).list_offers(submission_id)
    ]


@router.post(
    "/{submission_id}/offers",
    response_model=OfferRead,
    status_code=status.HTTP_201_CREATED,
)
def create_offer(
    submission_id: uuid.UUID,
    payload: OfferCreate,
    session: DatabaseSession,
) -> OfferRead:
    return OfferRead.model_validate(
        RecruitingProcessService(session).create_offer(submission_id, payload)
    )


@router.patch("/{submission_id}/offers/{offer_id}", response_model=OfferRead)
def update_offer(
    submission_id: uuid.UUID,
    offer_id: uuid.UUID,
    payload: OfferUpdate,
    session: DatabaseSession,
) -> OfferRead:
    return OfferRead.model_validate(
        RecruitingProcessService(session).update_offer(submission_id, offer_id, payload)
    )


@router.delete("/{submission_id}/offers/{offer_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_offer(
    submission_id: uuid.UUID,
    offer_id: uuid.UUID,
    session: DatabaseSession,
) -> Response:
    RecruitingProcessService(session).delete_offer(submission_id, offer_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/{submission_id}/placement", response_model=PlacementRead)
def get_placement(submission_id: uuid.UUID, session: DatabaseSession) -> PlacementRead:
    return PlacementRead.model_validate(
        RecruitingProcessService(session).get_placement(submission_id)
    )


@router.post(
    "/{submission_id}/placement",
    response_model=PlacementRead,
    status_code=status.HTTP_201_CREATED,
)
def create_placement(
    submission_id: uuid.UUID,
    payload: PlacementCreate,
    session: DatabaseSession,
) -> PlacementRead:
    return PlacementRead.model_validate(
        RecruitingProcessService(session).create_placement(submission_id, payload)
    )


@router.patch("/{submission_id}/placement", response_model=PlacementRead)
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


@router.delete("/{submission_id}/placement", status_code=status.HTTP_204_NO_CONTENT)
def delete_placement(submission_id: uuid.UUID, session: DatabaseSession) -> Response:
    RecruitingProcessService(session).delete_placement(submission_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.delete("/{submission_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_submission(
    submission_id: uuid.UUID, session: DatabaseSession, current_user: CurrentUser
) -> Response:
    CandidateSubmissionService(session).delete(submission_id, current_user)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
