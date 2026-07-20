import uuid
from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.orm import Session

from cc_crm.models.enums import TaskStatus
from cc_crm.models.task import Task
from cc_crm.repositories.base import SQLAlchemyRepository


class TaskRepository(SQLAlchemyRepository[Task]):
    def __init__(self, session: Session) -> None:
        super().__init__(session, Task)

    def find_open_by_submission_and_title(
        self, submission_id: uuid.UUID, title: str
    ) -> Task | None:
        statement = select(Task).where(
            Task.candidate_submission_id == submission_id,
            Task.title == title,
            Task.status == TaskStatus.OPEN,
        )
        return self.session.scalar(statement.limit(1))

    def filtered(
        self,
        *,
        candidate_id: uuid.UUID | None = None,
        client_company_id: uuid.UUID | None = None,
        submission_id: uuid.UUID | None = None,
        task_status: TaskStatus | None = None,
        owner_user_id: uuid.UUID | None = None,
        offset: int = 0,
        limit: int = 100,
    ) -> Sequence[Task]:
        filters = []
        if candidate_id is not None:
            filters.append(Task.candidate_id == candidate_id)
        if client_company_id is not None:
            filters.append(Task.client_company_id == client_company_id)
        if submission_id is not None:
            filters.append(Task.candidate_submission_id == submission_id)
        if task_status is not None:
            filters.append(Task.status == task_status)
        if owner_user_id is not None:
            filters.append(Task.owner_user_id == owner_user_id)
        statement = (
            select(Task)
            .where(*filters)
            .order_by(Task.due_at.is_(None), Task.due_at.asc())
            .offset(offset)
            .limit(limit)
        )
        return self.session.scalars(statement).all()
