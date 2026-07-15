import uuid
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Query, Response, status

from cc_crm.api.dependencies import DatabaseSession
from cc_crm.models.enums import JobStatus
from cc_crm.schemas.job_mandate import JobMandateCreate, JobMandateRead, JobMandateUpdate
from cc_crm.schemas.pagination import Page
from cc_crm.services.jobs import JobMandateService

router = APIRouter(prefix="/vacancies")


@router.get("", response_model=Page[JobMandateRead])
def list_jobs(
    session: DatabaseSession,
    job_status: Annotated[JobStatus | None, Query(alias="status")] = None,
    client_id: uuid.UUID | None = None,
    role: str | None = None,
    region: str | None = None,
    search: str | None = None,
    created_from: datetime | None = None,
    created_to: datetime | None = None,
    offset: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
) -> Page[JobMandateRead]:
    entities, total = JobMandateService(session).jobs.filtered(
        status=job_status,
        client_id=client_id,
        role=role,
        region=region,
        search=search,
        created_from=created_from,
        created_to=created_to,
        offset=offset,
        limit=limit,
    )
    items = [JobMandateRead.model_validate(job) for job in entities]
    return Page(items=items, total_count=total, limit=limit, offset=offset)


@router.post("", response_model=JobMandateRead, status_code=status.HTTP_201_CREATED)
def create_job(payload: JobMandateCreate, session: DatabaseSession) -> JobMandateRead:
    return JobMandateRead.model_validate(JobMandateService(session).create(payload))


@router.get("/{job_id}", response_model=JobMandateRead)
def get_job(job_id: uuid.UUID, session: DatabaseSession) -> JobMandateRead:
    return JobMandateRead.model_validate(JobMandateService(session).get(job_id))


@router.patch("/{job_id}", response_model=JobMandateRead)
def update_job(
    job_id: uuid.UUID,
    payload: JobMandateUpdate,
    session: DatabaseSession,
) -> JobMandateRead:
    return JobMandateRead.model_validate(JobMandateService(session).update(job_id, payload))


@router.delete("/{job_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_job(job_id: uuid.UUID, session: DatabaseSession) -> Response:
    JobMandateService(session).delete(job_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
