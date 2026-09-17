"""Microsoft-Graph-API-Aufrufe (Mail + Kalender) - reines HTTP (httpx), kein
DB-/Session-Zugriff. Nimmt einen bereits gueltigen Access-Token entgegen
(siehe services/graph_token_service.py fuer die Beschaffung) statt selbst zu
refreshen, damit dieses Modul unabhaengig von Verschluesselung/Persistenz
bleibt und leicht mit einem Fake-httpx-Client testbar ist.
"""

from __future__ import annotations

import contextlib
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

import httpx

from cc_crm.core.errors import BusinessRuleError

_GRAPH_ROOT = "https://graph.microsoft.com/v1.0"

# CalendarEvent.start_at/end_at werden in der gesamten App (Modell, Frontend,
# manuell per "Termin anlegen" angelegte Termine) als naive Europe/Berlin-
# Wanduhrzeit-Ziffern behandelt, nie als UTC. Graph liefert start/end als
# {"dateTime": "...", "timeZone": "..."} OHNE Offset/Z-Suffix in der
# angegebenen Zeitzone - da nirgends ein `Prefer: outlook.timezone=...`-
# Header gesetzt wird, ist das defaultmaessig "UTC". Prod-Vorfall: die rohen
# UTC-Ziffern wurden 1:1 als Berlin-Ziffern uebernommen -> 2h Differenz im
# Sommer/CEST (Termin um 16:00 Berlin/14:00 UTC wurde als 14:00 gespeichert).
_BERLIN_TZ = ZoneInfo("Europe/Berlin")


class GraphApiError(BusinessRuleError):
    """Ein Graph-API-Aufruf ist fehlgeschlagen (Netzwerk, 4xx/5xx)."""


def _headers(access_token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {access_token}", "Content-Type": "application/json"}


def _raise_for_status(response: httpx.Response, action: str) -> None:
    if response.status_code >= 300:
        detail = response.text
        with contextlib.suppress(ValueError):
            detail = response.json().get("error", {}).get("message", detail)
        raise GraphApiError(
            f"Graph-Aufruf ({action}) fehlgeschlagen [{response.status_code}]: {detail}"
        )


# --- Mail ------------------------------------------------------------------


def send_mail(
    access_token: str,
    *,
    to_address: str,
    to_name: str | None,
    subject: str,
    body_text: str,
    attachments: list[tuple[str, str, bytes]] | None = None,
) -> None:
    """POST /me/sendMail - legt die Mail automatisch in "Gesendete
    Elemente" ab (saveToSentItems, Default True), das bisherige IMAP-APPEND-
    Gefrickel entfaellt fuer Graph-Konten komplett. `attachments` als
    (filename, content_type, bytes)-Tupel."""
    message: dict[str, object] = {
        "subject": subject,
        "body": {"contentType": "Text", "content": body_text},
        "toRecipients": [{"emailAddress": {"address": to_address, "name": to_name or to_address}}],
    }
    if attachments:
        message["attachments"] = [
            {
                "@odata.type": "#microsoft.graph.fileAttachment",
                "name": filename,
                "contentType": content_type,
                "contentBytes": _b64(content),
            }
            for filename, content_type, content in attachments
        ]
    response = httpx.post(
        f"{_GRAPH_ROOT}/me/sendMail",
        headers=_headers(access_token),
        json={"message": message, "saveToSentItems": True},
        timeout=30,
    )
    _raise_for_status(response, "sendMail")


def _b64(content: bytes) -> str:
    import base64

    return base64.b64encode(content).decode("ascii")


@dataclass(frozen=True)
class GraphMessage:
    internet_message_id: str
    id: str
    from_name: str | None
    from_address: str | None
    subject: str | None
    body_text: str | None
    received_at: datetime
    is_draft: bool


@dataclass
class DeltaMailResult:
    messages: list[GraphMessage] = field(default_factory=list)
    delta_link: str | None = None


_MESSAGE_SELECT = "internetMessageId,id,from,subject,bodyPreview,body,receivedDateTime,isDraft"


def fetch_inbox_delta(
    access_token: str, *, delta_link: str | None, page_limit: int = 200
) -> DeltaMailResult:
    """Liest neue/geaenderte Nachrichten im Posteingang per Delta-Query -
    beim allerersten Aufruf (delta_link ist None) liefert Graph den
    kompletten aktuellen Bestand (durch top begrenzt, folgende Seiten ueber
    @odata.nextLink), danach nur noch Aenderungen seit dem zuletzt
    gespeicherten delta_link. Loeschungen wuerden hier als Eintraege mit
    "@removed" auftauchen - im Posteingang praktisch irrelevant (nicht
    ausgewertet, anders als beim Kalender-Sync)."""
    url = delta_link or (
        f"{_GRAPH_ROOT}/me/mailFolders/inbox/messages/delta"
        f"?$select={_MESSAGE_SELECT}&$top={page_limit}"
    )
    result = DeltaMailResult()
    while url:
        response = httpx.get(url, headers=_headers(access_token), timeout=30)
        _raise_for_status(response, "mail delta")
        body = response.json()
        for item in body.get("value", []):
            if "@removed" in item:
                continue
            from_field = (item.get("from") or {}).get("emailAddress") or {}
            result.messages.append(
                GraphMessage(
                    internet_message_id=(item.get("internetMessageId") or "").strip("<> "),
                    id=item["id"],
                    from_name=from_field.get("name"),
                    from_address=from_field.get("address"),
                    subject=item.get("subject"),
                    body_text=(item.get("body") or {}).get("content") or item.get("bodyPreview"),
                    received_at=_parse_graph_datetime(item.get("receivedDateTime")),
                    is_draft=bool(item.get("isDraft")),
                )
            )
            if len(result.messages) >= page_limit:
                break
        url = body.get("@odata.nextLink")
        if body.get("@odata.deltaLink"):
            result.delta_link = body["@odata.deltaLink"]
        if len(result.messages) >= page_limit:
            break
    return result


def _parse_graph_datetime(value: str | None) -> datetime:
    from datetime import UTC

    if not value:
        return datetime.now(UTC)
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _parse_graph_event_datetime(value: str | None, timezone_name: str | None) -> datetime | None:
    """Wie _parse_graph_datetime, aber speziell fuer Kalender-start/end: die
    Ziffern werden in der von Graph mitgelieferten Zeitzone (Default "UTC",
    siehe Kommentar bei _BERLIN_TZ) interpretiert und nach Europe/Berlin
    konvertiert, dann tzinfo wieder entfernt - so passen sie zur
    naive-Berlin-Ziffern-Konvention, die CalendarEvent.start_at/end_at
    ueberall sonst in der App hat."""
    if not value:
        return None
    if value.endswith("Z"):
        # Ein Z-Suffix ist bereits ein eindeutiger UTC-Zeitpunkt - die
        # mitgelieferte timeZone (i.d.R. "UTC") ist dann redundant.
        aware = datetime.fromisoformat(value.replace("Z", "+00:00"))
    else:
        naive = datetime.fromisoformat(value)
        aware = naive.replace(tzinfo=ZoneInfo(timezone_name or "UTC"))
    return aware.astimezone(_BERLIN_TZ).replace(tzinfo=None)


# --- Kalender ----------------------------------------------------------


@dataclass(frozen=True)
class GraphEvent:
    id: str
    subject: str
    body_text: str | None
    start_at: datetime
    end_at: datetime | None
    location: str | None
    last_modified_at: datetime


@dataclass
class DeltaCalendarResult:
    events: list[GraphEvent] = field(default_factory=list)
    removed_ids: list[str] = field(default_factory=list)
    delta_link: str | None = None


# Fenster fuer die ERSTE Delta-Anfrage einer neuen Synchronisation (nur beim
# allerersten Lauf ohne gespeicherten delta_link relevant - jede Folge-
# Anfrage nutzt den zurueckgelieferten @odata.nextLink/@odata.deltaLink
# unveraendert, der Zeitraum steckt darin bereits verschluesselt, siehe
# fetch_calendar_delta-Docstring). Grosszuegig bemessen, damit realistische
# CRM-Termine (Interviews/Quali-Calls Wochen im Voraus, Nachtraege fuer
# vergangene Termine) sicher im Fenster liegen.
_CALENDAR_DELTA_WINDOW_PAST_DAYS = 365
_CALENDAR_DELTA_WINDOW_FUTURE_DAYS = 730


def fetch_calendar_delta(
    access_token: str, *, delta_link: str | None, page_limit: int = 200
) -> DeltaCalendarResult:
    """Analog zu fetch_inbox_delta, aber fuer den Standardkalender - hier
    WERDEN Loeschungen ausgewertet (@removed-Marker), das ist die Basis fuer
    die Graph-->CRM-Loeschungserkennung in services/calendar_graph_sync.py.

    WICHTIG (Prod-Vorfall behoben): Kalender-Delta-Query existiert bei
    Microsoft Graph NUR auf `/me/calendarView/delta` (an ein Zeitfenster
    gebunden) - ein reiner `/me/events/delta` bzw. `/me/calendar/events/
    delta` ohne Zeitfenster ist laut Microsoft-Doku nur in der BETA-Version
    verfuegbar, in v1.0 (siehe _GRAPH_ROOT) nicht. Der vorherige Code nutzte
    genau diesen nicht existierenden v1.0-Endpoint - der Aufruf schlug fehl,
    die Exception wurde im Scheduled Job aber nur nach stdout geloggt (siehe
    scripts/run_graph_sync.py), nicht in einem fuer den Nutzer sichtbaren
    Feld (anders als MailAccount.sync_error beim Mail-Sync) - dadurch lief
    der Push CRM->Graph weiter (andere Endpoints, laeuft VOR diesem Aufruf
    in sync_account_calendar), der Pull Graph->CRM aber nie.
    `$select` ist bei calendarView/delta laut Microsoft-Doku zudem NICHT
    unterstuetzt - die Seitengroesse steuert stattdessen der
    `Prefer: odata.maxpagesize=...`-Header, das Zeitfenster nur die
    Start-URL der ERSTEN Anfrage (Folge-Links kodieren es bereits)."""
    if delta_link:
        url = delta_link
    else:
        now = datetime.now(UTC)
        window_start = now - timedelta(days=_CALENDAR_DELTA_WINDOW_PAST_DAYS)
        window_end = now + timedelta(days=_CALENDAR_DELTA_WINDOW_FUTURE_DAYS)
        url = (
            f"{_GRAPH_ROOT}/me/calendarView/delta"
            f"?startDateTime={window_start.strftime('%Y-%m-%dT%H:%M:%SZ')}"
            f"&endDateTime={window_end.strftime('%Y-%m-%dT%H:%M:%SZ')}"
        )
    headers = _headers(access_token)
    headers["Prefer"] = f"odata.maxpagesize={page_limit}"
    result = DeltaCalendarResult()
    while url:
        response = httpx.get(url, headers=headers, timeout=30)
        _raise_for_status(response, "calendar delta")
        body = response.json()
        for item in body.get("value", []):
            if "@removed" in item:
                result.removed_ids.append(item["id"])
                continue
            start = item.get("start") or {}
            end = item.get("end") or {}
            start_at = _parse_graph_event_datetime(start.get("dateTime"), start.get("timeZone"))
            if start_at is None:
                # Ohne Start-Zeit ist das Event fuer den CRM-Kalender nicht
                # verwertbar (start_at ist nicht nullable) - ueberspringen
                # statt mit einem falschen Ersatzwert zu speichern.
                continue
            result.events.append(
                GraphEvent(
                    id=item["id"],
                    subject=item.get("subject") or "",
                    body_text=(item.get("body") or {}).get("content"),
                    start_at=start_at,
                    end_at=_parse_graph_event_datetime(end.get("dateTime"), end.get("timeZone")),
                    location=(item.get("location") or {}).get("displayName"),
                    last_modified_at=_parse_graph_datetime(item.get("lastModifiedDateTime")),
                )
            )
        url = body.get("@odata.nextLink")
        if body.get("@odata.deltaLink"):
            result.delta_link = body["@odata.deltaLink"]
    return result


def _naive_isoformat(value: datetime) -> str:
    """CalendarEvent.start_at/end_at sind app-weit naive Europe/Berlin-
    Wanduhrzeit-Ziffern (siehe _BERLIN_TZ-Kommentar oben). ABER: Postgres'
    DateTime(timezone=True)-Spalten liefern beim Auslesen tz-aware Werte
    zurueck (anders als SQLite, das tzinfo auf dem Rundweg verwirft - siehe
    core/time.py::naive_utc()-Docstring) - typischerweise mit UTC-tzinfo,
    OBWOHL die gespeicherten Ziffern Berlin-Ortszeit bedeuten. Ein blankes
    .isoformat() auf so einem Wert haengt einen "+00:00"-Suffix an unsere
    Berlin-Ziffern, waehrend der Payload GLEICHZEITIG "timeZone": "Europe/
    Berlin" behauptet - dieser Widerspruch hat Graph dazu gebracht, beim
    Schreiben eine ZUSAETZLICHE Verschiebung einzubauen (Prod-Vorfall:
    Termine landeten in Outlook 2h weiter verschoben als im CRM). Deshalb
    hier immer zuerst tzinfo entfernen (NICHT konvertieren - die Ziffern
    sind bereits die gewollte Berlin-Ortszeit), dann erst isoformat()."""
    if value.tzinfo is not None:
        value = value.replace(tzinfo=None)
    return value.isoformat()


def _event_payload(
    *,
    title: str,
    body_text: str | None,
    start_at: datetime,
    end_at: datetime | None,
    location: str | None,
) -> dict[str, object]:
    effective_end = end_at or start_at
    return {
        "subject": title,
        "body": {"contentType": "Text", "content": body_text or ""},
        "start": {"dateTime": _naive_isoformat(start_at), "timeZone": "Europe/Berlin"},
        "end": {"dateTime": _naive_isoformat(effective_end), "timeZone": "Europe/Berlin"},
        "location": {"displayName": location} if location else None,
    }


def create_event(
    access_token: str,
    *,
    title: str,
    body_text: str | None,
    start_at: datetime,
    end_at: datetime | None,
    location: str | None,
) -> str:
    """Legt ein neues Event im Standardkalender an, gibt dessen Graph-ID
    zurueck (fuer CalendarEvent.external_graph_event_id)."""
    response = httpx.post(
        f"{_GRAPH_ROOT}/me/calendar/events",
        headers=_headers(access_token),
        json=_event_payload(
            title=title, body_text=body_text, start_at=start_at, end_at=end_at, location=location
        ),
        timeout=30,
    )
    _raise_for_status(response, "create event")
    graph_id: str = response.json()["id"]
    return graph_id


def update_event(
    access_token: str,
    *,
    graph_event_id: str,
    title: str,
    body_text: str | None,
    start_at: datetime,
    end_at: datetime | None,
    location: str | None,
) -> None:
    response = httpx.patch(
        f"{_GRAPH_ROOT}/me/calendar/events/{graph_event_id}",
        headers=_headers(access_token),
        json=_event_payload(
            title=title, body_text=body_text, start_at=start_at, end_at=end_at, location=location
        ),
        timeout=30,
    )
    _raise_for_status(response, "update event")


def delete_event(access_token: str, *, graph_event_id: str) -> None:
    response = httpx.delete(
        f"{_GRAPH_ROOT}/me/calendar/events/{graph_event_id}",
        headers=_headers(access_token),
        timeout=30,
    )
    # 404 = auf Graph-Seite bereits weg (z.B. dort schon manuell geloescht) -
    # aus Sicht des Aufrufers trotzdem ein erfolgreiches "ist jetzt weg".
    if response.status_code not in (204, 404):
        _raise_for_status(response, "delete event")


def get_event(access_token: str, *, graph_event_id: str) -> GraphEvent | None:
    """Liest ein einzelnes Event per ID (ausserhalb einer Delta-Query) -
    fuer gezielte Einzelfall-Diagnose/-Korrektur (siehe scripts/diagnose_
    graph_calendar_corruption_20260916.py und scripts/fix_calendar_
    incident_times_20260916.py). Nutzt bewusst dieselbe _parse_graph_event_
    datetime()-Logik wie fetch_calendar_delta(), damit ein hier gelesener
    start_at/end_at exakt so interpretiert wird wie beim normalen Pull -
    keine zweite, potenziell abweichende Parsing-Implementierung."""
    response = httpx.get(
        f"{_GRAPH_ROOT}/me/events/{graph_event_id}",
        headers=_headers(access_token),
        params={"$select": "id,subject,body,start,end,location,lastModifiedDateTime"},
        timeout=30,
    )
    if response.status_code == 404:
        return None
    _raise_for_status(response, "get event")
    item = response.json()
    start = item.get("start") or {}
    end = item.get("end") or {}
    start_at = _parse_graph_event_datetime(start.get("dateTime"), start.get("timeZone"))
    if start_at is None:
        return None
    return GraphEvent(
        id=item["id"],
        subject=item.get("subject") or "",
        body_text=(item.get("body") or {}).get("content"),
        start_at=start_at,
        end_at=_parse_graph_event_datetime(end.get("dateTime"), end.get("timeZone")),
        location=(item.get("location") or {}).get("displayName"),
        last_modified_at=_parse_graph_datetime(item.get("lastModifiedDateTime")),
    )


def get_event_raw(access_token: str, *, graph_event_id: str) -> dict[str, Any] | None:
    """Wie get_event(), aber gibt die volle Graph-JSON-Antwort zurueck statt
    sie in ein GraphEvent zu parsen - fuer Diagnosezwecke, bei denen Felder
    wie `type`/`seriesMasterId`/`recurrence` gebraucht werden, die GraphEvent
    nicht abbildet (die normale Sync-Pipeline braucht sie nicht). Siehe
    scripts/investigate_recurring_series_20260916.py."""
    response = httpx.get(
        f"{_GRAPH_ROOT}/me/events/{graph_event_id}",
        headers=_headers(access_token),
        params={
            "$select": "id,subject,type,seriesMasterId,recurrence,start,end,lastModifiedDateTime"
        },
        timeout=30,
    )
    if response.status_code == 404:
        return None
    _raise_for_status(response, "get event (raw)")
    result: dict[str, Any] = response.json()
    return result


def list_series_masters(access_token: str) -> list[dict[str, Any]]:
    """Listet alle wiederkehrenden Serien-Master im Standardkalender (GET
    /me/events?$filter=type eq 'seriesMaster') - Diagnosezweck: pruefen, ob
    eine Serie waehrend des Vorfallsfensters veraendert wurde. calendarView/
    delta (siehe fetch_calendar_delta) expandiert Serien in einzelne
    Vorkommen und liefert dabei KEINEN seriesMaster-Eintrag selbst - ein
    veraenderter Serien-Master faellt deshalb durchs Delta-Raster."""
    results: list[dict[str, Any]] = []
    url: str | None = f"{_GRAPH_ROOT}/me/events"
    params: dict[str, Any] | None = {
        "$filter": "type eq 'seriesMaster'",
        "$select": "id,subject,lastModifiedDateTime,recurrence",
        "$top": 200,
    }
    while url:
        response = httpx.get(url, headers=_headers(access_token), params=params, timeout=30)
        _raise_for_status(response, "list series masters")
        body = response.json()
        results.extend(body.get("value", []))
        url = body.get("@odata.nextLink")
        params = None  # nextLink enthaelt bereits alle Parameter, nicht erneut mitschicken.
    return results


def list_series_instances(
    access_token: str, *, series_master_id: str, start: datetime, end: datetime
) -> list[dict[str, Any]]:
    """Listet die konkreten Vorkommen (inkl. Exceptions) einer Serie in
    einem Zeitfenster - GET /me/events/{id}/instances."""
    response = httpx.get(
        f"{_GRAPH_ROOT}/me/events/{series_master_id}/instances",
        headers=_headers(access_token),
        params={
            "startDateTime": start.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "endDateTime": end.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "$select": "id,subject,type,start,end,lastModifiedDateTime",
        },
        timeout=30,
    )
    _raise_for_status(response, "list series instances")
    result: list[dict[str, Any]] = response.json().get("value", [])
    return result
