import uuid
from collections.abc import Sequence
from datetime import datetime

from sqlalchemy.orm import Session

from cc_crm.core.errors import PermissionDeniedError
from cc_crm.models.calendar_event import CalendarEvent
from cc_crm.models.enums import CalendarEventType
from cc_crm.models.user import User
from cc_crm.repositories.calendar_events import CalendarEventRepository
from cc_crm.schemas.calendar_event import CalendarEventCreate, CalendarEventUpdate
from cc_crm.services.base import CrudService


class CalendarEventService(CrudService[CalendarEvent, CalendarEventCreate, CalendarEventUpdate]):
    def __init__(self, session: Session) -> None:
        repository = CalendarEventRepository(session)
        super().__init__(session, repository, "CalendarEvent")
        self.events = repository

    def list_visible(
        self,
        current_user: User,
        *,
        start_from: datetime | None = None,
        start_to: datetime | None = None,
        event_type: CalendarEventType | None = None,
        owner_user_id: uuid.UUID | None = None,
    ) -> Sequence[CalendarEvent]:
        """Standardnutzer sehen ausschliesslich eigene Termine - ein
        mitgeschickter owner_user_id-Filter wird fuer sie stillschweigend
        ignoriert (nicht mit einem Fehler quittiert, da er fuer sie ohnehin
        keine andere Bedeutung haben kann als "meine eigenen"). Admins sehen
        per Default alle, koennen optional auf einen einzelnen Nutzer filtern."""
        if current_user.is_admin:
            owner_user_ids = [owner_user_id] if owner_user_id is not None else None
        else:
            owner_user_ids = [current_user.id]
        return self.events.filtered(
            owner_user_ids=owner_user_ids,
            start_from=start_from,
            start_to=start_to,
            event_type=event_type,
        )

    def create_for_user(self, payload: CalendarEventCreate, current_user: User) -> CalendarEvent:
        # Normalnutzer duerfen nur fuer sich selbst anlegen - ein
        # abweichender owner_user_id im Body wird serverseitig ignoriert statt
        # nur clientseitig verhindert. Admins duerfen fuer jeden Nutzer anlegen.
        owner_user_id = current_user.id
        if current_user.is_admin and payload.owner_user_id is not None:
            owner_user_id = payload.owner_user_id

        values = payload.model_dump(exclude={"owner_user_id"})
        values["owner_user_id"] = owner_user_id
        values["created_by_user_id"] = current_user.id
        entity = self.repository.create(values)
        self.session.commit()
        return entity

    def get_for_user(self, event_id: uuid.UUID, current_user: User) -> CalendarEvent:
        event = self.get(event_id)
        self._check_access(event, current_user)
        return event

    def update_for_user(
        self, event_id: uuid.UUID, payload: CalendarEventUpdate, current_user: User
    ) -> CalendarEvent:
        event = self.get(event_id)
        self._check_access(event, current_user)
        return self.update(event_id, payload)

    def delete_for_user(self, event_id: uuid.UUID, current_user: User) -> None:
        event = self.get(event_id)
        self._check_access(event, current_user)
        self.delete(event_id)

    def _check_access(self, event: CalendarEvent, current_user: User) -> None:
        if current_user.is_admin or event.owner_user_id == current_user.id:
            return
        raise PermissionDeniedError("Kein Zugriff auf diesen Termin.")
