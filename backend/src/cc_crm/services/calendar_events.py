import uuid
from collections.abc import Sequence
from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from cc_crm.core.errors import BusinessRuleError, PermissionDeniedError
from cc_crm.core.time import naive_utc
from cc_crm.models.calendar_event import CalendarEvent
from cc_crm.models.enums import CalendarEventType
from cc_crm.models.user import User
from cc_crm.repositories.calendar_events import CalendarEventRepository
from cc_crm.repositories.recruiting import AuditLogRepository
from cc_crm.schemas.calendar_event import CalendarEventCreate, CalendarEventUpdate
from cc_crm.services.base import CrudService
from cc_crm.services.calendar_graph_sync import (
    has_connected_account,
    push_delete_to_graph,
    push_event_now,
)

# Prod-Vorfall 2026-09-28: ein Termin mit end_at VOR start_at wurde vom
# Microsoft-Graph-Push dauerhaft mit 400 abgelehnt und liess den Kalender-Sync
# fuer dieses Event bei jedem Job-Lauf stillschweigend scheitern (nur
# logger.warning in calendar_graph_sync.py::_push_local_changes). end_at bleibt
# absichtlich nullable (siehe models/calendar_event.py) - hier wird stattdessen
# IMMER ein sinnvolles end_at erzwungen: fehlt es, wird es aus start_at
# berechnet; liegt ein mitgegebenes end_at zu nah an oder vor start_at, wird
# das abgelehnt statt es stillschweigend zu korrigieren, damit der Nutzer die
# Diskrepanz bewusst sieht (Nutzer-Vorgabe).
MINIMUM_EVENT_DURATION_MINUTES = 30


def default_invite_message(first_name: str, client_name: str | None, when: datetime) -> str:
    """Standard-Einladungstext an Kandidaten (statt interner Notizen)."""
    where = f" mit {client_name}" if client_name else ""
    return (
        f"Hallo {first_name},\n\nhiermit lade ich Sie zum Vorstellungsgespraech{where} ein "
        f"({when:%d.%m.%Y, %H:%M} Uhr). Den Link zum Online-Termin finden Sie in dieser "
        "Einladung.\n\nBei Rueckfragen melden Sie sich gern."
    )


def apply_minimum_duration(start_at: datetime, end_at: datetime | None) -> datetime:
    """Oeffentliche Modulfunktion (nicht privat), da auch services/
    recruiting.py::_create_calendar_event_for_interview automatisch erzeugte
    Interview-Termine denselben Mindestdauer-Regeln unterwerfen muss - dort
    wird end_at bislang gar nicht gesetzt, faellt also ebenfalls unter den
    "kein end_at angegeben"-Fall unten.

    Verglichen wird ueber naive UTC-Zeiten (core/time.py::naive_utc): unter
    Postgres liefert die Datenbank den gespeicherten Wert MIT Zeitzone, ein
    Payload ohne Offset ("2026-09-28T10:00:00") ist dagegen naiv - der direkte
    Vergleich warf "can't compare offset-naive and offset-aware datetimes"
    (HTTP 500), sobald nur start_at ODER nur end_at geaendert wurde."""
    minimum_end_at = start_at + timedelta(minutes=MINIMUM_EVENT_DURATION_MINUTES)
    if end_at is None:
        return minimum_end_at
    if naive_utc(end_at) < naive_utc(minimum_end_at):
        raise BusinessRuleError(
            f"Ende muss mindestens {MINIMUM_EVENT_DURATION_MINUTES} Minuten "
            "nach dem Start liegen."
        )
    return end_at


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
        values["end_at"] = apply_minimum_duration(payload.start_at, payload.end_at)
        if payload.attendee_email:
            self._require_outlook_for_invite(owner_user_id)
        elif payload.online_meeting:
            raise BusinessRuleError("Ein Teams-Link braucht einen eingeladenen Teilnehmer.")
        entity = self.repository.create(values)
        self.session.commit()
        if entity.attendee_email:
            self.push_invite(entity, current_user)
        return entity

    def _require_outlook_for_invite(self, owner_user_id: uuid.UUID) -> None:
        if not has_connected_account(self.session, owner_user_id):
            raise BusinessRuleError(
                "Einladungen laufen ueber Outlook: bitte zuerst mit Microsoft anmelden "
                "(Postfach verbinden)."
            )

    def push_invite(self, event: CalendarEvent, current_user: User | None) -> bool:
        """Schickt den Termin sofort nach Outlook (dabei geht die Einladung raus)
        und protokolliert das. False, wenn Outlook gerade nicht erreichbar war -
        der Zeitplan-Lauf holt es dann nach."""
        pushed = push_event_now(self.session, event)
        AuditLogRepository(self.session).create(
            {
                "entity_type": "calendar_event",
                "entity_id": event.id,
                "action": "invite_sent" if pushed else "invite_pending",
                "changed_by": current_user.email if current_user else None,
                "new_values": {"online_meeting": event.online_meeting},
            }
        )
        self.session.commit()
        return pushed

    def get_for_user(self, event_id: uuid.UUID, current_user: User) -> CalendarEvent:
        event = self.get(event_id)
        self._check_access(event, current_user)
        return event

    def update_for_user(
        self, event_id: uuid.UUID, payload: CalendarEventUpdate, current_user: User
    ) -> CalendarEvent:
        event = self.get(event_id)
        self._check_access(event, current_user)
        values = payload.model_dump(exclude_unset=True)
        if "start_at" in values or "end_at" in values:
            # CalendarEventUpdate macht alle Felder optional - fehlt eines der
            # beiden im Payload, muss gegen den bereits gespeicherten Wert
            # geprueft werden (gemergter Zustand), nicht nur gegen die im
            # Payload gesendeten Felder, sonst liesse sich die Mindestdauer-
            # Pruefung durch ein Update umgehen, das nur start_at ODER nur
            # end_at aendert.
            merged_start_at = values.get("start_at", event.start_at)
            merged_end_at = values.get("end_at", event.end_at)
            values["end_at"] = apply_minimum_duration(merged_start_at, merged_end_at)
        if "attendee_email" in values:
            if not values["attendee_email"] and event.attendee_email:
                raise BusinessRuleError(
                    "Ein eingeladener Teilnehmer kann nicht entfernt werden - bitte den "
                    "Termin loeschen (Outlook verschickt dann eine Absage) und neu anlegen."
                )
            if values["attendee_email"]:
                self._require_outlook_for_invite(event.owner_user_id)
        if values.get("online_meeting") and not (
            values.get("attendee_email") or event.attendee_email
        ):
            raise BusinessRuleError("Ein Teams-Link braucht einen eingeladenen Teilnehmer.")
        updated = self.repository.update(event, values)
        self.session.commit()
        if updated.attendee_email:
            self.push_invite(updated, current_user)
        return updated

    def delete_for_user(self, event_id: uuid.UUID, current_user: User) -> None:
        event = self.get(event_id)
        self._check_access(event, current_user)
        # Synchron VOR dem CRM-Loeschen (best effort, siehe M365-
        # Integrationsplan Abschnitt Kalender-Konfliktlogik) - danach ist
        # external_graph_event_id weg und ein spaeterer Retry nicht mehr
        # moeglich.
        push_delete_to_graph(self.session, event)
        self.delete(event_id)

    def _check_access(self, event: CalendarEvent, current_user: User) -> None:
        if current_user.is_admin or event.owner_user_id == current_user.id:
            return
        raise PermissionDeniedError("Kein Zugriff auf diesen Termin.")
