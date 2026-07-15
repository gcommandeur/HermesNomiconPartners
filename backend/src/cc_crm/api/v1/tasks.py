import uuid
from typing import Annotated

from fastapi import APIRouter, Query, Response, status

from cc_crm.api.dependencies import DatabaseSession
from cc_crm.models.enums import TaskStatus
from cc_crm.schemas.task import TaskCreate, TaskRead, TaskUpdate
from cc_crm.services.tasks import TaskService

router = APIRouter(prefix="/tasks")


@router.get("", response_model=list[TaskRead])
def list_tasks(
    session: DatabaseSession,
    candidate_id: uuid.UUID | None = None,
    client_company_id: uuid.UUID | None = None,
    submission_id: uuid.UUID | None = None,
    task_status: Annotated[TaskStatus | None, Query(alias="status")] = None,
    offset: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
) -> list[TaskRead]:
    tasks = TaskService(session).tasks.filtered(
        candidate_id=candidate_id,
        client_company_id=client_company_id,
        submission_id=submission_id,
        task_status=task_status,
        offset=offset,
        limit=limit,
    )
    return [TaskRead.model_validate(task) for task in tasks]


@router.post("", response_model=TaskRead, status_code=status.HTTP_201_CREATED)
def create_task(payload: TaskCreate, session: DatabaseSession) -> TaskRead:
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
