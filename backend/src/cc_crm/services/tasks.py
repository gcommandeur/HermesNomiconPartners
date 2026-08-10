import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy.orm import Session

from cc_crm.core.errors import BusinessRuleError
from cc_crm.models.calendar_event import CalendarEvent
from cc_crm.models.enums import CalendarEventType, TaskStatus
from cc_crm.models.task import Task
from cc_crm.repositories.tasks import TaskRepository
from cc_crm.schemas.task import TaskCreate, TaskResolveRequest, TaskSnoozeRequest, TaskUpdate
from cc_crm.services.base import CrudService


class TaskService(CrudService[Task, TaskCreate, TaskUpdate]):
    def __init__(self, session: Session) -> None:
        repository = TaskRepository(session)
        super().__init__(session, repository, "Task")
        self.tasks = repository

    def snooze(self, task_id: uuid.UUID, payload: TaskSnoozeRequest) -> Task:
        task = self.get(task_id)
        task.snoozed_until = datetime.now(UTC) + timedelta(days=payload.days)
        self.session.commit()
        self.session.refresh(task)
        return task

    def resolve(self, task_id: uuid.UUID, payload: TaskResolveRequest, user_id: uuid.UUID) -> Task:
        """Reaktion auf ein (i.d.R. automatisch erzeugtes) Task, siehe
        api/v1/tasks.py fuer die Endpunkt-Doku. Beide Ausgaenge schliessen
        das Task (status=DONE) - der Unterschied ist, ob dabei zusaetzlich
        ein CalendarEvent entsteht."""
        task = self.get(task_id)

        if payload.outcome == "meeting_scheduled":
            if payload.scheduled_at is None:
                raise BusinessRuleError(
                    "scheduled_at ist bei outcome='meeting_scheduled' Pflicht."
                )
            candidate_label = task.title.split(":", 1)[-1].strip() or task.title
            self.session.add(
                CalendarEvent(
                    title=f"Quali-Call: {candidate_label}",
                    event_type=CalendarEventType.QUALI_CALL,
                    start_at=payload.scheduled_at,
                    notes=payload.notes,
                    # Owner/Ersteller = der Nutzer, der das Task aufloest -
                    # bei automatisch erzeugten Tasks gibt es sonst niemand
                    # Sinnvolleren, dem der Termin gehoeren wuerde.
                    owner_user_id=user_id,
                    created_by_user_id=user_id,
                    candidate_id=task.candidate_id,
                    client_company_id=task.client_company_id,
                    candidate_submission_id=task.candidate_submission_id,
                )
            )

        task.status = TaskStatus.DONE
        if payload.notes:
            task.description = (
                f"{task.description}\n\n{payload.notes}" if task.description else payload.notes
            )
        self.session.commit()
        self.session.refresh(task)
        return task
