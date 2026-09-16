"""Tests fuer integrations/microsoft_graph/client.py auf reiner HTTP-Ebene
(httpx wird gemockt, kein echter Netzwerkzugriff) - insbesondere
fetch_calendar_delta, das den bereits behobenen Prod-Vorfall verursacht hat
(Auftrag "Kalender-Sync Outlook -> CRM funktioniert nicht").

Root Cause (per Microsoft-Graph-Doku bestaetigt, siehe learn.microsoft.com/
graph/delta-query-events): Delta-Query fuer Kalender-Termine existiert in
v1.0 NUR auf `/me/calendarView/delta` (an ein Start-/End-Zeitfenster
gebunden) - ein endlos-offener `/me/events/delta` bzw. der zuvor hier
verwendete, nicht existierende `/me/calendar/events/delta` ist laut
Microsoft-Doku nur in der BETA-Version verfuegbar. Ausserdem ist `$select`
bei calendarView/delta explizit NICHT unterstuetzt. Der alte Code nutzte
beides falsch - der Aufruf schlug fehl, wurde aber im Scheduled Job nur
nach stdout geloggt (siehe scripts/run_graph_sync.py), nicht in einem fuer
den Nutzer sichtbaren Feld. Push (CRM->Graph, andere Endpoints, laeuft
VOR diesem Aufruf) blieb davon unberuehrt - genau das gemeldete
Bug-Symptom "Push funktioniert, Pull nicht, kein sichtbarer Fehler".

Diese Tests haetten den Bug gefangen, waeren aber vorher nicht geschrieben
worden, weil die hoeherliegenden calendar_graph_sync-Tests fetch_calendar_
delta komplett wegmocken - sie pruefen deshalb die tatsaechlich aufgerufene
URL/Header/Parameter, nicht nur die Verarbeitung eines fertigen Ergebnisses."""

from __future__ import annotations

from datetime import UTC, datetime

import httpx
import pytest

from cc_crm.integrations.microsoft_graph.client import (
    GraphApiError,
    fetch_calendar_delta,
)


class _FakeResponse:
    def __init__(self, status_code: int, json_body: dict) -> None:
        self.status_code = status_code
        self._json_body = json_body
        self.text = str(json_body)

    def json(self) -> dict:
        return self._json_body


def test_initial_request_uses_calendarview_delta_not_events_delta(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Der eigentliche Bug: v1.0 kennt kein `/events/delta` ohne Zeitfenster
    (nur in beta) - der Aufruf MUSS auf /me/calendarView/delta gehen, mit
    startDateTime/endDateTime, und OHNE $select (von Microsoft fuer
    calendarView/delta explizit als nicht unterstuetzt dokumentiert)."""
    captured: dict[str, object] = {}

    def fake_get(url: str, *, headers: dict[str, str], timeout: float) -> _FakeResponse:
        captured["url"] = url
        captured["headers"] = headers
        return _FakeResponse(
            200, {"value": [], "@odata.deltaLink": "https://graph.example/delta-2"}
        )

    monkeypatch.setattr(httpx, "get", fake_get)

    fetch_calendar_delta("access-1", delta_link=None)

    url = captured["url"]
    assert isinstance(url, str)
    assert "/me/calendarView/delta" in url
    assert "/me/calendar/events/delta" not in url
    assert "/me/events/delta" not in url
    assert "startDateTime=" in url
    assert "endDateTime=" in url
    assert "$select" not in url
    headers = captured["headers"]
    assert isinstance(headers, dict)
    assert "odata.maxpagesize" in headers.get("Prefer", "")


def test_subsequent_request_uses_the_stored_delta_link_verbatim(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Ein gespeicherter delta_link (von einem frueheren Lauf) wird
    unveraendert weiterverwendet - kein erneutes Anhaengen von Zeitfenster
    oder $select, das Token kodiert beides bereits (siehe Microsoft-Doku)."""
    captured_urls: list[str] = []
    stored_link = "https://graph.microsoft.com/v1.0/me/calendarView/delta?$deltatoken=abc123"

    def fake_get(url: str, *, headers: dict[str, str], timeout: float) -> _FakeResponse:
        captured_urls.append(url)
        return _FakeResponse(200, {"value": [], "@odata.deltaLink": stored_link})

    monkeypatch.setattr(httpx, "get", fake_get)

    fetch_calendar_delta("access-1", delta_link=stored_link)

    assert captured_urls == [stored_link]


def test_a_newly_created_outlook_event_is_returned(monkeypatch: pytest.MonkeyPatch) -> None:
    """Genau der gemeldete Fall: ein frisch in Outlook angelegtes Event
    (keine @removed-Markierung, kein vorheriger Bezug) muss im Ergebnis
    landen."""

    def fake_get(url: str, *, headers: dict[str, str], timeout: float) -> _FakeResponse:
        return _FakeResponse(
            200,
            {
                "value": [
                    {
                        "id": "graph-evt-outlook-1",
                        "subject": "SYNC-TEST Outlook->CRM",
                        "body": {"contentType": "text", "content": "Testtermin"},
                        "start": {"dateTime": "2026-09-16T14:00:00.0000000Z", "timeZone": "UTC"},
                        "end": {"dateTime": "2026-09-16T14:30:00.0000000Z", "timeZone": "UTC"},
                        "lastModifiedDateTime": "2026-09-16T10:05:00.1234567Z",
                    }
                ],
                "@odata.deltaLink": "https://graph.example/delta-next",
            },
        )

    monkeypatch.setattr(httpx, "get", fake_get)

    result = fetch_calendar_delta("access-1", delta_link=None)

    assert len(result.events) == 1
    event = result.events[0]
    assert event.id == "graph-evt-outlook-1"
    assert event.subject == "SYNC-TEST Outlook->CRM"
    assert event.last_modified_at == datetime(2026, 9, 16, 10, 5, 0, 123456, tzinfo=UTC)
    assert result.delta_link == "https://graph.example/delta-next"
    assert result.removed_ids == []


def test_removed_marker_is_reported_as_a_deletion(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_get(url: str, *, headers: dict[str, str], timeout: float) -> _FakeResponse:
        return _FakeResponse(
            200,
            {
                "value": [{"id": "graph-evt-gone", "@removed": {"reason": "deleted"}}],
                "@odata.deltaLink": "https://graph.example/delta-next",
            },
        )

    monkeypatch.setattr(httpx, "get", fake_get)

    result = fetch_calendar_delta("access-1", delta_link=None)

    assert result.removed_ids == ["graph-evt-gone"]
    assert result.events == []


def test_error_response_raises_graph_api_error(monkeypatch: pytest.MonkeyPatch) -> None:
    """Genau der Fehlerpfad, der beim alten (falschen) Endpoint aufgetreten
    waere - stellt sicher, dass ein 4xx/5xx weiterhin klar als
    GraphApiError durchgereicht wird, statt still verschluckt zu werden."""

    def fake_get(url: str, *, headers: dict[str, str], timeout: float) -> _FakeResponse:
        return _FakeResponse(400, {"error": {"message": "Invalid query parameter"}})

    monkeypatch.setattr(httpx, "get", fake_get)

    with pytest.raises(GraphApiError, match="Invalid query parameter"):
        fetch_calendar_delta("access-1", delta_link=None)
