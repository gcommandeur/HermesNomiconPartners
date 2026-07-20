from collections.abc import Sequence
from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

from icalendar import Alarm, Calendar
from icalendar import Event as VEvent

from cc_crm.models.calendar_event import CalendarEvent
from cc_crm.models.user import User

# Alle Termine werden als Europe/Berlin-Wanduhrzeit behandelt (Nutzer-Vorgabe:
# "Zeitzone: Europe/Berlin konsistent verwenden") - kein Multi-Timezone-
# Handling noetig, da Hermes CRM ausschliesslich fuer den deutschen Markt
# betrieben wird. Auf SQLite kommen DateTime(timezone=True)-Werte beim
# Auslesen naiv zurueck (siehe core/time.py::naive_utc), auf Postgres bleiben
# sie aware - _as_berlin() vereinheitlicht beide Faelle auf denselben
# aware-Berlin-Wert statt einer echten UTC-Konvertierung, da der gespeicherte
# Wert bereits die gewollte lokale Uhrzeit ist (kein Umrechnen noetig/gewollt).
_BERLIN = ZoneInfo("Europe/Berlin")


def _as_berlin(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=_BERLIN)
    return value.astimezone(_BERLIN)


def build_ics_feed(user: User, events: Sequence[CalendarEvent]) -> bytes:
    """Baut ein RFC-5545-VCALENDAR-Dokument fuer den persoenlichen Kalender-
    Feed eines Nutzers - ein VEVENT pro Termin, inkl. VALARM fuer die
    Erinnerung. Nutzt die icalendar-Bibliothek statt eigenem String-Bauen, um
    Escaping-/Faltungs-/Zeitzonenfehler zu vermeiden (siehe Nutzer-Vorgabe)."""
    calendar = Calendar()
    calendar.add("prodid", "-//Hermes CRM//Kalender-Feed//DE")
    calendar.add("version", "2.0")
    calendar.add("calscale", "GREGORIAN")
    calendar.add("method", "PUBLISH")
    calendar.add("x-wr-calname", f"Hermes CRM – {user.display_name or user.email}")
    calendar.add("x-wr-timezone", "Europe/Berlin")

    for event in events:
        vevent = VEvent()
        vevent.add("uid", f"calendar-event-{event.id}@hermescrm")
        vevent.add("summary", event.title)
        vevent.add("dtstart", _as_berlin(event.start_at))
        if event.end_at:
            vevent.add("dtend", _as_berlin(event.end_at))
        if event.location:
            vevent.add("location", event.location)
        if event.notes:
            vevent.add("description", event.notes)
        vevent.add("dtstamp", datetime.now(UTC))
        vevent.add("last-modified", _as_berlin(event.updated_at))
        vevent.add("created", _as_berlin(event.created_at))

        if event.reminder_minutes_before > 0:
            alarm = Alarm()
            alarm.add("action", "DISPLAY")
            alarm.add("description", event.title)
            alarm.add("trigger", timedelta(minutes=-event.reminder_minutes_before))
            vevent.add_component(alarm)

        calendar.add_component(vevent)

    return bytes(calendar.to_ical())
