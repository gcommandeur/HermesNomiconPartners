import uuid
from typing import Annotated

from fastapi import APIRouter, Query, Response, status

from cc_crm.api.dependencies import DatabaseSession
from cc_crm.schemas.activity import ActivityCreate, ActivityRead, ActivityUpdate
from cc_crm.services.activities import ActivityService

router = APIRouter(prefix="/activities")


@router.get("", response_model=list[ActivityRead])
def list_activities(
    session: DatabaseSession,
    candidate_id: uuid.UUID | None = None,
    client_company_id: uuid.UUID | None = None,
    submission_id: uuid.UUID | None = None,
    offset: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
) -> list[ActivityRead]:
    activities = ActivityService(session).activities.filtered(
        candidate_id=candidate_id,
        client_company_id=client_company_id,
        submission_id=submission_id,
        offset=offset,
        limit=limit,
    )
    return [ActivityRead.model_validate(activity) for activity in activities]


@router.post("", response_model=ActivityRead, status_code=status.HTTP_201_CREATED)
def create_activity(payload: ActivityCreate, session: DatabaseSession) -> ActivityRead:
    return ActivityRead.model_validate(ActivityService(session).create(payload))


@router.get("/{activity_id}", response_model=ActivityRead)
def get_activity(activity_id: uuid.UUID, session: DatabaseSession) -> ActivityRead:
    return ActivityRead.model_validate(ActivityService(session).get(activity_id))


@router.patch("/{activity_id}", response_model=ActivityRead)
def update_activity(
    activity_id: uuid.UUID,
    payload: ActivityUpdate,
    session: DatabaseSession,
) -> ActivityRead:
    return ActivityRead.model_validate(ActivityService(session).update(activity_id, payload))


@router.delete("/{activity_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_activity(activity_id: uuid.UUID, session: DatabaseSession) -> Response:
    ActivityService(session).delete(activity_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
