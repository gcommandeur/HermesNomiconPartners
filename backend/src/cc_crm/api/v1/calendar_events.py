import uuid
from datetime import datetime

from fastapi import APIRouter, Response, status

from cc_crm.api.dependencies import CurrentUser, DatabaseSession
from cc_crm.models.enums import CalendarEventType
from cc_crm.schemas.calendar_event import (
    CalendarEventCreate,
    CalendarEventRead,
    CalendarEventUpdate,
)
from cc_crm.services.calendar_events import CalendarEventService

router = APIRouter(prefix="/calendar-events")


@router.get("", response_model=list[CalendarEventRead])
def list_calendar_events(
    session: DatabaseSession,
    current_user: CurrentUser,
    start_from: datetime | None = None,
    start_to: datetime | None = None,
    event_type: CalendarEventType | None = None,
    owner_user_id: uuid.UUID | None = None,
) -> list[CalendarEventRead]:
    events = CalendarEventService(session).list_visible(
        current_user,
        start_from=start_from,
        start_to=start_to,
        event_type=event_type,
        owner_user_id=owner_user_id,
    )
    return [CalendarEventRead.model_validate(event) for event in events]


@router.post("", response_model=CalendarEventRead, status_code=status.HTTP_201_CREATED)
def create_calendar_event(
    payload: CalendarEventCreate,
    session: DatabaseSession,
    current_user: CurrentUser,
) -> CalendarEventRead:
    event = CalendarEventService(session).create_for_user(payload, current_user)
    return CalendarEventRead.model_validate(event)


@router.get("/{event_id}", response_model=CalendarEventRead)
def get_calendar_event(
    event_id: uuid.UUID, session: DatabaseSession, current_user: CurrentUser
) -> CalendarEventRead:
    event = CalendarEventService(session).get_for_user(event_id, current_user)
    return CalendarEventRead.model_validate(event)


@router.patch("/{event_id}", response_model=CalendarEventRead)
def update_calendar_event(
    event_id: uuid.UUID,
    payload: CalendarEventUpdate,
    session: DatabaseSession,
    current_user: CurrentUser,
) -> CalendarEventRead:
    event = CalendarEventService(session).update_for_user(event_id, payload, current_user)
    return CalendarEventRead.model_validate(event)


@router.delete("/{event_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_calendar_event(
    event_id: uuid.UUID, session: DatabaseSession, current_user: CurrentUser
) -> Response:
    CalendarEventService(session).delete_for_user(event_id, current_user)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
