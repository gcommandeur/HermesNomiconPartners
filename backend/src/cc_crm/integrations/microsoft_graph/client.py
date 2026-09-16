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

import httpx

from cc_crm.core.errors import BusinessRuleError

_GRAPH_ROOT = "https://graph.microsoft.com/v1.0"


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
            result.events.append(
                GraphEvent(
                    id=item["id"],
                    subject=item.get("subject") or "",
                    body_text=(item.get("body") or {}).get("content"),
                    start_at=_parse_graph_datetime(start.get("dateTime")),
                    end_at=_parse_graph_datetime(end.get("dateTime"))
                    if end.get("dateTime")
                    else None,
                    location=(item.get("location") or {}).get("displayName"),
                    last_modified_at=_parse_graph_datetime(item.get("lastModifiedDateTime")),
                )
            )
        url = body.get("@odata.nextLink")
        if body.get("@odata.deltaLink"):
            result.delta_link = body["@odata.deltaLink"]
    return result


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
        "start": {"dateTime": start_at.isoformat(), "timeZone": "Europe/Berlin"},
        "end": {"dateTime": effective_end.isoformat(), "timeZone": "Europe/Berlin"},
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
