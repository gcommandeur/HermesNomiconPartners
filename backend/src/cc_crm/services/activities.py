from sqlalchemy.orm import Session

from cc_crm.models.activity import Activity
from cc_crm.repositories.activities import ActivityRepository
from cc_crm.schemas.activity import ActivityCreate, ActivityUpdate
from cc_crm.services.base import CrudService


class ActivityService(CrudService[Activity, ActivityCreate, ActivityUpdate]):
    def __init__(self, session: Session) -> None:
        repository = ActivityRepository(session)
        super().__init__(session, repository, "Activity")
        self.activities = repository
