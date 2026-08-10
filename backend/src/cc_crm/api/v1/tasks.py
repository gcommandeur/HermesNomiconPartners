import uuid
from typing import Annotated

from fastapi import APIRouter, Query, Response, status

from cc_crm.api.dependencies import CurrentUser, DatabaseSession
from cc_crm.models.enums import TaskStatus
from cc_crm.schemas.task import (
    TaskCreate,
    TaskRead,
    TaskResolveRequest,
    TaskSnoozeRequest,
    TaskUpdate,
)
from cc_crm.services.tasks import TaskService

router = APIRouter(prefix="/tasks")


@router.get("", response_model=list[TaskRead])
def list_tasks(
    session: DatabaseSession,
    candidate_id: uuid.UUID | None = None,
    client_company_id: uuid.UUID | None = None,
    submission_id: uuid.UUID | None = None,
    task_status: Annotated[TaskStatus | None, Query(alias="status")] = None,
    owner_user_id: uuid.UUID | None = None,
    offset: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
) -> list[TaskRead]:
    # owner_user_id ist ein reiner Komfort-Filter ("Meine Aufgaben") - ohne
    # ihn sehen weiterhin alle Nutzer alle Aufgaben, keine Sichtbarkeitsgrenze.
    #
    # exclude_snoozed nur bei status=open automatisch aktiv (Nutzer-Vorgabe:
    # "GET /tasks?status=open filtert ... standardmaessig raus") - bei einer
    # ungefilterten oder anders gefilterten Abfrage (z.B. status=done fuers
    # Archiv, oder gar kein Status) sollen zurueckgestellte Tasks weiterhin
    # auffindbar bleiben.
    tasks = TaskService(session).tasks.filtered(
        candidate_id=candidate_id,
        client_company_id=client_company_id,
        submission_id=submission_id,
        task_status=task_status,
        owner_user_id=owner_user_id,
        exclude_snoozed=task_status == TaskStatus.OPEN,
        offset=offset,
        limit=limit,
    )
    return [TaskRead.model_validate(task) for task in tasks]


@router.post("", response_model=TaskRead, status_code=status.HTTP_201_CREATED)
def create_task(
    payload: TaskCreate,
    session: DatabaseSession,
    current_user: CurrentUser,
) -> TaskRead:
    if payload.owner_user_id is None:
        payload = payload.model_copy(update={"owner_user_id": current_user.id})
    return TaskRead.model_validate(TaskService(session).create(payload))


@router.get("/{task_id}", response_model=TaskRead)
def get_task(task_id: uuid.UUID, session: DatabaseSession) -> TaskRead:
    return TaskRead.model_validate(TaskService(session).get(task_id))


@router.patch("/{task_id}", response_model=TaskRead)
def update_task(
    task_id: uuid.UUID,
    payload: TaskUpdate,
    session: DatabaseSession,
) -> TaskRead:
    return TaskRead.model_validate(TaskService(session).update(task_id, payload))


@router.delete("/{task_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_task(task_id: uuid.UUID, session: DatabaseSession) -> Response:
    TaskService(session).delete(task_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/{task_id}/snooze", response_model=TaskRead)
def snooze_task(
    task_id: uuid.UUID, payload: TaskSnoozeRequest, session: DatabaseSession
) -> TaskRead:
    return TaskRead.model_validate(TaskService(session).snooze(task_id, payload))


@router.post("/{task_id}/resolve", response_model=TaskRead)
def resolve_task(
    task_id: uuid.UUID,
    payload: TaskResolveRequest,
    session: DatabaseSession,
    current_user: CurrentUser,
) -> TaskRead:
    return TaskRead.model_validate(TaskService(session).resolve(task_id, payload, current_user.id))
