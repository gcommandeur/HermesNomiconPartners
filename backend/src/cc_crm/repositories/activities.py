import uuid
from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.orm import Session

from cc_crm.models.activity import Activity
from cc_crm.repositories.base import SQLAlchemyRepository


class ActivityRepository(SQLAlchemyRepository[Activity]):
    def __init__(self, session: Session) -> None:
        super().__init__(session, Activity)

    def filtered(
        self,
        *,
        candidate_id: uuid.UUID | None = None,
        client_company_id: uuid.UUID | None = None,
        submission_id: uuid.UUID | None = None,
        offset: int = 0,
        limit: int = 100,
    ) -> Sequence[Activity]:
        filters = []
        if candidate_id is not None:
            filters.append(Activity.candidate_id == candidate_id)
        if client_company_id is not None:
            filters.append(Activity.client_company_id == client_company_id)
        if submission_id is not None:
            filters.append(Activity.candidate_submission_id == submission_id)
        statement = (
            select(Activity)
            .where(*filters)
            .order_by(Activity.occurred_at.desc())
            .offset(offset)
            .limit(limit)
        )
        return self.session.scalars(statement).all()
