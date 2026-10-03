import uuid

from fastapi import APIRouter

from cc_crm.api.dependencies import AdminUser, DatabaseSession
from cc_crm.schemas.background_job import BackgroundJobRead
from cc_crm.services.job_queue import list_jobs, retry_job

router = APIRouter(prefix="/background-jobs")


@router.get("", response_model=list[BackgroundJobRead])
def get_background_jobs(
    session: DatabaseSession, _admin: AdminUser, status: str | None = None, limit: int = 100
) -> list[BackgroundJobRead]:
    """Nur Admin: Hintergrundjobs ansehen (z.B. fehlgeschlagene)."""
    jobs = list_jobs(session, status=status, limit=min(max(limit, 1), 500))
    return [BackgroundJobRead.model_validate(job) for job in jobs]


@router.post("/{job_id}/retry", response_model=BackgroundJobRead)
def retry_background_job(
    job_id: uuid.UUID, session: DatabaseSession, _admin: AdminUser
) -> BackgroundJobRead:
    return BackgroundJobRead.model_validate(retry_job(session, job_id))
