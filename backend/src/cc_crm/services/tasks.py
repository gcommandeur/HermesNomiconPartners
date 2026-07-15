from sqlalchemy.orm import Session

from cc_crm.models.task import Task
from cc_crm.repositories.tasks import TaskRepository
from cc_crm.schemas.task import TaskCreate, TaskUpdate
from cc_crm.services.base import CrudService


class TaskService(CrudService[Task, TaskCreate, TaskUpdate]):
    def __init__(self, session: Session) -> None:
        repository = TaskRepository(session)
        super().__init__(session, repository, "Task")
        self.tasks = repository
