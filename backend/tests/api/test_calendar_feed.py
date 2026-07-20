from fastapi.testclient import TestClient


def test_ics_feed_returns_valid_vcalendar_with_valarm(client: TestClient) -> None:
    me = client.get("/api/v1/auth/me").json()
    client.post(
        "/api/v1/calendar-events",
        json={
            "title": "Quali Call mit Erika Musterfrau",
            "start_at": "2026-08-05T14:00:00",
            "end_at": "2026-08-05T14:30:00",
            "reminder_minutes_before": 15,
        },
    )

    feed_token = me["calendar_feed_token"]
    response = client.get(f"/api/v1/calendar/feed/{feed_token}.ics")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/calendar")
    body = response.text
    assert body.startswith("BEGIN:VCALENDAR")
    assert body.rstrip().endswith("END:VCALENDAR")
    assert "BEGIN:VEVENT" in body
    assert "SUMMARY:Quali Call mit Erika Musterfrau" in body
    assert "BEGIN:VALARM" in body
    assert "TRIGGER:-PT15M" in body
    assert "TZID=Europe/Berlin" in body


def test_ics_feed_wrong_token_returns_404(client: TestClient) -> None:
    response = client.get("/api/v1/calendar/feed/this-token-does-not-exist.ics")
    assert response.status_code == 404


def test_ics_feed_missing_token_returns_404(client: TestClient) -> None:
    response = client.get("/api/v1/calendar/feed/.ics")
    assert response.status_code == 404


def test_ics_feed_only_shows_owners_own_events(client: TestClient) -> None:
    """Ein Feed zeigt nur die Termine des zugehoerigen Nutzers, auch wenn
    andere Termine in derselben DB existieren (kein Datenleck ueber den
    Feed hinweg)."""
    me = client.get("/api/v1/auth/me").json()
    client.post(
        "/api/v1/calendar-events",
        json={"title": "Sichtbarer Termin", "start_at": "2026-08-06T10:00:00"},
    )

    feed_token = me["calendar_feed_token"]
    response = client.get(f"/api/v1/calendar/feed/{feed_token}.ics")
    assert "Sichtbarer Termin" in response.text
