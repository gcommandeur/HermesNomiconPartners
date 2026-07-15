import uuid
from collections.abc import Sequence
from datetime import datetime

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from cc_crm.models.enums import JobStatus
from cc_crm.models.job_mandate import JobMandate
from cc_crm.repositories.base import SQLAlchemyRepository


class JobMandateRepository(SQLAlchemyRepository[JobMandate]):
    def __init__(self, session: Session) -> None:
        super().__init__(session, JobMandate)

    def filtered(
        self,
        *,
        status: JobStatus | None = None,
        client_id: uuid.UUID | None = None,
        role: str | None = None,
        region: str | None = None,
        search: str | None = None,
        created_from: datetime | None = None,
        created_to: datetime | None = None,
        offset: int = 0,
        limit: int = 100,
    ) -> tuple[Sequence[JobMandate], int]:
        filters = []
        if status is not None:
            filters.append(JobMandate.status == status)
        if client_id:
            filters.append(JobMandate.client_company_id == client_id)
        if role:
            filters.append(JobMandate.title.ilike(f"%{role}%"))
        if region:
            filters.append(JobMandate.location.ilike(f"%{region}%"))
        if search:
            term = f"%{search}%"
            filters.append(or_(JobMandate.title.ilike(term), JobMandate.description.ilike(term)))
        if created_from:
            filters.append(JobMandate.created_at >= created_from)
        if created_to:
            filters.append(JobMandate.created_at <= created_to)
        query = (
            select(JobMandate)
            .where(*filters)
            .order_by(JobMandate.created_at.desc())
            .offset(offset)
            .limit(limit)
        )
        count = select(func.count()).select_from(JobMandate).where(*filters)
        return self.session.scalars(query).all(), int(self.session.scalar(count) or 0)
