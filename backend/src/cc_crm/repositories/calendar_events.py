import uuid
from collections.abc import Sequence
from datetime import datetime

from sqlalchemy import ColumnElement, select
from sqlalchemy.orm import Session

from cc_crm.models.calendar_event import CalendarEvent
from cc_crm.models.enums import CalendarEventType
from cc_crm.repositories.base import SQLAlchemyRepository


class CalendarEventRepository(SQLAlchemyRepository[CalendarEvent]):
    def __init__(self, session: Session) -> None:
        super().__init__(session, CalendarEvent)

    def filtered(
        self,
        *,
        owner_user_ids: Sequence[uuid.UUID] | None,
        start_from: datetime | None = None,
        start_to: datetime | None = None,
        event_type: CalendarEventType | None = None,
    ) -> Sequence[CalendarEvent]:
        """owner_user_ids=None bedeutet "keine Owner-Einschraenkung" (nur fuer
        Admins zulaessig, siehe CalendarEventService) - eine leere Liste
        wuerde dagegen (via .in_([])) korrekt keine Zeilen zurueckgeben."""
        filters: list[ColumnElement[bool]] = []
        if owner_user_ids is not None:
            filters.append(CalendarEvent.owner_user_id.in_(owner_user_ids))
        if start_from:
            filters.append(CalendarEvent.start_at >= start_from)
        if start_to:
            filters.append(CalendarEvent.start_at <= start_to)
        if event_type:
            filters.append(CalendarEvent.event_type == event_type)
        query = select(CalendarEvent).where(*filters).order_by(CalendarEvent.start_at)
        return self.session.scalars(query).all()

    def for_source_interview(self, interview_id: uuid.UUID) -> CalendarEvent | None:
        """Der (hoechstens eine) automatisch aus einem Interview erzeugte
        Kalendereintrag - Grundlage fuer den Sync bei Interview-Aenderung/
        -Loeschung (siehe services/recruiting.py::update_interview/
        delete_interview)."""
        return self.session.scalar(
            select(CalendarEvent).where(CalendarEvent.source_interview_id == interview_id)
        )

    def for_owner(self, owner_user_id: uuid.UUID) -> Sequence[CalendarEvent]:
        """Alle Termine eines Nutzers, ungefiltert - fuer den ICS-Feed (dort
        keine Datumsfilter, der ganze persoenliche Kalender wird exportiert)."""
        query = (
            select(CalendarEvent)
            .where(CalendarEvent.owner_user_id == owner_user_id)
            .order_by(CalendarEvent.start_at)
        )
        return self.session.scalars(query).all()
