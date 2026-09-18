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
    create_event,
    fetch_calendar_delta,
    get_event,
    get_event_raw,
    list_series_instances,
    list_series_masters,
    update_event,
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
    # 14:00 UTC ist im September (CEST, UTC+2) 16:00 Berliner Ortszeit - genau
    # der Prod-Vorfall "Termine 2h zurueck", siehe test_calendar_event_times_
    # are_converted_from_utc_to_berlin_wall_clock unten fuer den direkten Test.
    assert event.start_at == datetime(2026, 9, 16, 16, 0, 0)
    assert event.end_at == datetime(2026, 9, 16, 16, 30, 0)
    assert event.last_modified_at == datetime(2026, 9, 16, 10, 5, 0, 123456, tzinfo=UTC)
    assert result.delta_link == "https://graph.example/delta-next"
    assert result.removed_ids == []


def test_calendar_event_times_are_converted_from_utc_to_berlin_wall_clock(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Der eigentliche Prod-Bug ("Termine sind 2h zurueck"): Graph liefert
    start/end ohne Offset in der mitgelieferten timeZone (Default "UTC", da
    kein `Prefer: outlook.timezone=...` gesetzt wird) - die rohen Ziffern
    duerfen NICHT 1:1 als CalendarEvent.start_at/end_at (= Berlin-Wanduhrzeit
    ueberall sonst in der App) uebernommen werden, sondern muessen erst nach
    Europe/Berlin konvertiert werden."""

    def fake_get(url: str, *, headers: dict[str, str], timeout: float) -> _FakeResponse:
        return _FakeResponse(
            200,
            {
                "value": [
                    {
                        "id": "graph-evt-tz-1",
                        "subject": "Kundentermin",
                        "body": {"contentType": "text", "content": None},
                        # Kein Z-Suffix, timeZone explizit "UTC" - das reale
                        # Graph-Format ohne Prefer-Header.
                        "start": {"dateTime": "2026-09-16T14:00:00.0000000", "timeZone": "UTC"},
                        "end": {"dateTime": "2026-09-16T14:30:00.0000000", "timeZone": "UTC"},
                        "lastModifiedDateTime": "2026-09-16T10:05:00.0000000Z",
                    }
                ],
                "@odata.deltaLink": "https://graph.example/delta-next",
            },
        )

    monkeypatch.setattr(httpx, "get", fake_get)

    result = fetch_calendar_delta("access-1", delta_link=None)

    event = result.events[0]
    # CEST (UTC+2) im September - 14:00 UTC muss als 16:00 Berlin ankommen,
    # nicht als 14:00 (das waere der Bug).
    assert event.start_at == datetime(2026, 9, 16, 16, 0, 0)
    assert event.end_at == datetime(2026, 9, 16, 16, 30, 0)


def test_calendar_event_times_respect_non_utc_graph_timezone(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Falls Graph doch mal eine andere Zeitzone als UTC mitliefert (z.B. weil
    der Postfach-Nutzer eine abweichende Zeitzone eingestellt hat), muss die
    Konvertierung ueber DIESE Zeitzone laufen, nicht blind UTC annehmen."""

    def fake_get(url: str, *, headers: dict[str, str], timeout: float) -> _FakeResponse:
        return _FakeResponse(
            200,
            {
                "value": [
                    {
                        "id": "graph-evt-tz-2",
                        "subject": "Termin",
                        "body": {"contentType": "text", "content": None},
                        # Bereits in Berlin-Ortszeit - darf NICHT nochmal
                        # verschoben werden.
                        "start": {
                            "dateTime": "2026-09-16T16:00:00.0000000",
                            "timeZone": "Europe/Berlin",
                        },
                        "end": {
                            "dateTime": "2026-09-16T16:30:00.0000000",
                            "timeZone": "Europe/Berlin",
                        },
                        "lastModifiedDateTime": "2026-09-16T10:05:00.0000000Z",
                    }
                ],
                "@odata.deltaLink": "https://graph.example/delta-next",
            },
        )

    monkeypatch.setattr(httpx, "get", fake_get)

    result = fetch_calendar_delta("access-1", delta_link=None)

    event = result.events[0]
    assert event.start_at == datetime(2026, 9, 16, 16, 0, 0)
    assert event.end_at == datetime(2026, 9, 16, 16, 30, 0)


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


class TestEventPayloadTimezoneHandling:
    """Zweiter, eigenstaendiger Prod-Bug (zusaetzlich zum Phantom-Push):
    CalendarEvent.start_at/end_at sind app-weit naive Europe/Berlin-Ziffern,
    aber Postgres' DateTime(timezone=True)-Spalten liefern beim Auslesen
    tz-aware Werte zurueck (anders als SQLite - siehe core/time.py::
    naive_utc()-Docstring). _event_payload() rief bisher blind .isoformat()
    auf, was bei einem aware Wert einen "+00:00"-Suffix an die (eigentlich
    schon Berlin-gemeinten) Ziffern haengt, waehrend GLEICHZEITIG "timeZone":
    "Europe/Berlin" mitgeschickt wird - dieser Widerspruch hat Graph zu einer
    ZUSAETZLICHEN 2h-Verschiebung beim Schreiben veranlasst (Termine landeten
    in Outlook 2h weiter verschoben als im CRM gespeichert)."""

    def test_create_event_strips_tzinfo_before_sending_to_graph(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        captured: dict[str, object] = {}

        def fake_post(url: str, *, headers: dict[str, str], json: dict, timeout: float):
            captured["json"] = json
            return _FakeResponse(201, {"id": "graph-evt-new"})

        monkeypatch.setattr(httpx, "post", fake_post)

        # tz-aware, wie es aus einer Postgres-DateTime(timezone=True)-Spalte
        # zurueckkommt - die Ziffern (14:00) sind bereits die gewollte
        # Berlin-Ortszeit, tzinfo=UTC ist hier nur ein Artefakt des DB-
        # Rundwegs, keine echte UTC-Aussage.
        aware_start = datetime(2026, 9, 16, 14, 0, tzinfo=UTC)
        aware_end = datetime(2026, 9, 16, 14, 30, tzinfo=UTC)

        graph_id = create_event(
            "access-1",
            title="Kundentermin",
            body_text=None,
            start_at=aware_start,
            end_at=aware_end,
            location=None,
        )

        assert graph_id == "graph-evt-new"
        payload = captured["json"]
        assert payload["start"]["dateTime"] == "2026-09-16T14:00:00"
        assert payload["end"]["dateTime"] == "2026-09-16T14:30:00"
        assert payload["start"]["timeZone"] == "Europe/Berlin"
        # Kein Offset-Suffix - genau das hat die zusaetzliche Verschiebung
        # verursacht.
        assert "+" not in payload["start"]["dateTime"]
        assert "+" not in payload["end"]["dateTime"]

    def test_update_event_strips_tzinfo_before_sending_to_graph(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        captured: dict[str, object] = {}

        def fake_patch(url: str, *, headers: dict[str, str], json: dict, timeout: float):
            captured["json"] = json
            return _FakeResponse(200, {})

        monkeypatch.setattr(httpx, "patch", fake_patch)

        update_event(
            "access-1",
            graph_event_id="graph-evt-1",
            title="Kundentermin",
            body_text=None,
            start_at=datetime(2026, 9, 16, 14, 0, tzinfo=UTC),
            end_at=None,
            location=None,
        )

        payload = captured["json"]
        assert payload["start"]["dateTime"] == "2026-09-16T14:00:00"
        assert payload["end"]["dateTime"] == "2026-09-16T14:00:00"

    def test_create_event_leaves_naive_datetimes_unchanged(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Der Normalfall (naive Eingabe, z.B. aus SQLite oder einem frisch
        im Python-Prozess erzeugten Wert) darf sich durch die Absicherung
        nicht aendern."""
        captured: dict[str, object] = {}

        def fake_post(url: str, *, headers: dict[str, str], json: dict, timeout: float):
            captured["json"] = json
            return _FakeResponse(201, {"id": "graph-evt-new"})

        monkeypatch.setattr(httpx, "post", fake_post)

        create_event(
            "access-1",
            title="Kundentermin",
            body_text=None,
            start_at=datetime(2026, 9, 16, 14, 0),
            end_at=None,
            location=None,
        )

        assert captured["json"]["start"]["dateTime"] == "2026-09-16T14:00:00"


class TestGetEvent:
    def test_returns_event_parsed_via_the_same_logic_as_delta_query(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        def fake_get(url: str, *, headers: dict[str, str], params: dict, timeout: float):
            assert url.endswith("/me/events/graph-evt-single")
            return _FakeResponse(
                200,
                {
                    "id": "graph-evt-single",
                    "subject": "Kundentermin",
                    "body": {"contentType": "text", "content": "Notizen"},
                    "start": {"dateTime": "2026-08-29T05:00:00.0000000", "timeZone": "UTC"},
                    "end": {"dateTime": "2026-08-29T05:30:00.0000000", "timeZone": "UTC"},
                    "lastModifiedDateTime": "2026-09-16T15:54:34.0947520Z",
                },
            )

        monkeypatch.setattr(httpx, "get", fake_get)

        event = get_event("access-1", graph_event_id="graph-evt-single")

        assert event is not None
        assert event.id == "graph-evt-single"
        assert event.subject == "Kundentermin"
        # UTC 05:00 im August (noch CEST) -> 07:00 Berlin.
        assert event.start_at == datetime(2026, 8, 29, 7, 0, 0)
        assert event.end_at == datetime(2026, 8, 29, 7, 30, 0)

    def test_returns_none_for_unknown_event(self, monkeypatch: pytest.MonkeyPatch) -> None:
        def fake_get(url: str, *, headers: dict[str, str], params: dict, timeout: float):
            return _FakeResponse(404, {"error": {"message": "not found"}})

        monkeypatch.setattr(httpx, "get", fake_get)

        assert get_event("access-1", graph_event_id="graph-evt-gone") is None


class TestRecurringSeriesDiagnostics:
    """Fuer die Population-B-Untersuchung (Vorfall vom 2026-09-16): pruefen,
    ob wiederkehrende Serien vom Vorfall veraendert wurden - calendarView/
    delta (fetch_calendar_delta) expandiert Serien in Vorkommen und liefert
    dabei keinen seriesMaster-Eintrag, ein veraenderter Master faellt also
    durchs normale Delta-Raster."""

    def test_get_event_raw_returns_series_fields(self, monkeypatch: pytest.MonkeyPatch) -> None:
        def fake_get(url: str, *, headers: dict[str, str], params: dict, timeout: float):
            assert url.endswith("/me/events/graph-evt-occ")
            return _FakeResponse(
                200,
                {
                    "id": "graph-evt-occ",
                    "subject": "",
                    "type": "occurrence",
                    "seriesMasterId": "graph-series-1",
                    "lastModifiedDateTime": "2026-09-16T15:54:34.0947520Z",
                },
            )

        monkeypatch.setattr(httpx, "get", fake_get)

        result = get_event_raw("access-1", graph_event_id="graph-evt-occ")

        assert result is not None
        assert result["type"] == "occurrence"
        assert result["seriesMasterId"] == "graph-series-1"

    def test_list_series_masters_filters_by_type_and_follows_next_link(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        calls: list[dict] = []

        def fake_get(url: str, *, headers: dict[str, str], params: dict | None, timeout: float):
            calls.append({"url": url, "params": params})
            if len(calls) == 1:
                assert params["$filter"] == "type eq 'seriesMaster'"
                return _FakeResponse(
                    200,
                    {
                        "value": [{"id": "series-1", "subject": "CV OUTs"}],
                        "@odata.nextLink": "https://graph.example/next-page",
                    },
                )
            return _FakeResponse(200, {"value": [{"id": "series-2", "subject": "Follow Ups"}]})

        monkeypatch.setattr(httpx, "get", fake_get)

        results = list_series_masters("access-1")

        assert [r["id"] for r in results] == ["series-1", "series-2"]
        assert len(calls) == 2
        # Der zweite Aufruf nutzt die nextLink-URL direkt, ohne die
        # $filter-Parameter erneut anzuhaengen (die stecken schon in der
        # URL selbst).
        assert calls[1]["url"] == "https://graph.example/next-page"
        assert calls[1]["params"] is None

    def test_list_series_instances_passes_time_window(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        captured: dict[str, object] = {}

        def fake_get(url: str, *, headers: dict[str, str], params: dict, timeout: float):
            captured["url"] = url
            captured["params"] = params
            return _FakeResponse(
                200, {"value": [{"id": "occ-1", "type": "exception", "subject": "CV OUTs"}]}
            )

        monkeypatch.setattr(httpx, "get", fake_get)

        results = list_series_instances(
            "access-1",
            series_master_id="series-1",
            start=datetime(2026, 9, 1),
            end=datetime(2026, 9, 30),
        )

        assert results[0]["type"] == "exception"
        assert captured["url"].endswith("/me/events/series-1/instances")
        assert captured["params"]["startDateTime"] == "2026-09-01T00:00:00Z"
        assert captured["params"]["endDateTime"] == "2026-09-30T00:00:00Z"
