"""Einladungen per Outlook: Teilnehmer, Teams-Link, nie interne Notizen."""

from __future__ import annotations

from collections.abc import Generator
from datetime import UTC, datetime
from typing import Any

import pytest
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from cc_crm.core.config import get_settings
from cc_crm.integrations.microsoft_graph.client import DeltaCalendarResult, GraphEvent
from cc_crm.models.calendar_event import CalendarEvent
from cc_crm.models.enums import MailAccountOAuthStatus, MailAccountProvider
from cc_crm.models.mail import MailAccount
from cc_crm.models.recruiting import AuditLog
from cc_crm.models.user import User
from cc_crm.services import calendar_graph_sync

JOIN_URL = "https://teams.microsoft.com/l/meetup-join/abc"


class FakeGraph:
    def __init__(self) -> None:
        self.created: list[dict[str, Any]] = []
        self.updated: list[dict[str, Any]] = []


@pytest.fixture(autouse=True)
def _key(monkeypatch: pytest.MonkeyPatch) -> Generator[None, None, None]:
    get_settings.cache_clear()
    monkeypatch.setenv("CC_CRM_MAIL_CREDENTIALS_ENCRYPTION_KEY", Fernet.generate_key().decode())
    yield
    get_settings.cache_clear()


@pytest.fixture
def graph(monkeypatch: pytest.MonkeyPatch) -> FakeGraph:
    fake = FakeGraph()

    def create_event(access_token: str, **kwargs: Any) -> str:
        fake.created.append(kwargs)
        return f"graph-{len(fake.created)}"

    def update_event(access_token: str, **kwargs: Any) -> None:
        fake.updated.append(kwargs)

    monkeypatch.setattr(calendar_graph_sync, "create_event", create_event)
    monkeypatch.setattr(calendar_graph_sync, "update_event", update_event)
    monkeypatch.setattr(calendar_graph_sync, "fetch_join_url", lambda token, **kw: JOIN_URL)
    monkeypatch.setattr(calendar_graph_sync, "get_valid_access_token", lambda s, a: "token")
    return fake


def _connect_outlook(session_factory: sessionmaker[Session]) -> None:
    """Der Standard-Testnutzer (conftest) bekommt ein verbundenes Postfach."""
    with session_factory() as session:
        user = session.scalars(select(User)).first()
        assert user is not None
        session.add(
            MailAccount(
                address="recruiter@example.com",
                label="Recruiter",
                provider=MailAccountProvider.MICROSOFT_GRAPH,
                oauth_status=MailAccountOAuthStatus.CONNECTED,
                oauth_connected_by_user_id=user.id,
            )
        )
        session.commit()


def _event_body(**overrides: Any) -> dict[str, Any]:
    return {
        "title": "Kennenlernen",
        "start_at": "2026-11-10T10:00:00",
        "end_at": "2026-11-10T10:30:00",
        "notes": "INTERN: Gehaltsvorstellung zu hoch",
        "attendee_email": "kandidat@example.com",
        "attendee_name": "Karla Kandidatin",
        "invite_message": "Hallo Karla, hier der Link.",
        "online_meeting": True,
        **overrides,
    }


def test_invite_requires_a_connected_outlook(client: TestClient, graph: FakeGraph) -> None:
    response = client.post("/api/v1/calendar-events", json=_event_body())
    assert response.status_code >= 400
    assert "Microsoft" in response.text
    assert graph.created == []


def test_invite_goes_out_immediately_with_teams_link_and_never_with_internal_notes(
    client: TestClient, session_factory: sessionmaker[Session], graph: FakeGraph
) -> None:
    _connect_outlook(session_factory)
    response = client.post("/api/v1/calendar-events", json=_event_body())
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["online_meeting_url"] == JOIN_URL
    assert body["attendee_email"] == "kandidat@example.com"

    sent = graph.created[0]
    assert sent["attendees"] == [("kandidat@example.com", "Karla Kandidatin")]
    assert sent["online_meeting"] is True
    assert sent["body_text"] == "Hallo Karla, hier der Link."
    assert "INTERN" not in str(sent)

    with session_factory() as session:
        actions = [row.action for row in session.scalars(select(AuditLog))]
        assert "invite_sent" in actions


def test_invite_without_own_text_uses_a_neutral_default_not_the_notes(
    client: TestClient, session_factory: sessionmaker[Session], graph: FakeGraph
) -> None:
    _connect_outlook(session_factory)
    response = client.post(
        "/api/v1/calendar-events", json=_event_body(invite_message=None, online_meeting=False)
    )
    assert response.status_code == 201, response.text
    assert "INTERN" not in graph.created[0]["body_text"]
    assert graph.created[0]["online_meeting"] is False


def test_event_without_attendee_still_syncs_its_notes_like_before(
    client: TestClient, session_factory: sessionmaker[Session], graph: FakeGraph
) -> None:
    _connect_outlook(session_factory)
    response = client.post(
        "/api/v1/calendar-events", json=_event_body(attendee_email=None, online_meeting=False)
    )
    assert response.status_code == 201
    # Ohne Teilnehmer wird nicht sofort gepusht (Zeitplan-Lauf) - der Push dort
    # nimmt die Notizen wie bisher in den eigenen Kalender.
    assert graph.created == []
    with session_factory() as session:
        event = session.scalars(select(CalendarEvent)).one()
        calendar_graph_sync._push_one(session, "token", event)
    assert graph.created[0]["body_text"] == "INTERN: Gehaltsvorstellung zu hoch"
    assert graph.created[0]["attendees"] is None


def test_teams_link_needs_an_attendee(client: TestClient, graph: FakeGraph) -> None:
    response = client.post(
        "/api/v1/calendar-events", json=_event_body(attendee_email=None, online_meeting=True)
    )
    assert response.status_code >= 400


def test_changing_the_event_updates_the_invitation_and_attendee_cannot_be_removed(
    client: TestClient, session_factory: sessionmaker[Session], graph: FakeGraph
) -> None:
    _connect_outlook(session_factory)
    created = client.post("/api/v1/calendar-events", json=_event_body()).json()

    moved = client.patch(
        f"/api/v1/calendar-events/{created['id']}",
        json={"start_at": "2026-11-11T09:00:00", "end_at": "2026-11-11T09:30:00"},
    )
    assert moved.status_code == 200, moved.text
    assert len(graph.updated) == 1
    assert graph.updated[0]["attendees"] == [("kandidat@example.com", "Karla Kandidatin")]
    assert "INTERN" not in str(graph.updated[0])

    removed = client.patch(
        f"/api/v1/calendar-events/{created['id']}", json={"attendee_email": None}
    )
    assert removed.status_code >= 400


def test_pull_does_not_overwrite_internal_notes_and_records_the_answer(
    client: TestClient,
    session_factory: sessionmaker[Session],
    graph: FakeGraph,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _connect_outlook(session_factory)
    created = client.post("/api/v1/calendar-events", json=_event_body()).json()

    outlook_event = GraphEvent(
        id="graph-1",
        subject="Kennenlernen",
        body_text="Hallo Karla, hier der Link.",
        start_at=datetime(2026, 11, 10, 10, 0, tzinfo=UTC),
        end_at=datetime(2026, 11, 10, 10, 30, tzinfo=UTC),
        location="Microsoft Teams-Besprechung",
        last_modified_at=datetime(2099, 1, 1, tzinfo=UTC),
        attendee_response="accepted",
        online_meeting_url=JOIN_URL,
        has_attendees=True,
    )
    monkeypatch.setattr(
        calendar_graph_sync,
        "fetch_calendar_delta",
        lambda token, *, delta_link, page_limit=200: DeltaCalendarResult(
            events=[outlook_event], delta_link="d1"
        ),
    )
    with session_factory() as session:
        account = session.scalars(select(MailAccount)).one()
        calendar_graph_sync._pull_graph_changes(session, "token", account)

    refreshed = client.get(f"/api/v1/calendar-events/{created['id']}").json()
    assert refreshed["attendee_response"] == "accepted"
    assert refreshed["notes"] == "INTERN: Gehaltsvorstellung zu hoch"
    assert refreshed["location"] != "Microsoft Teams-Besprechung"


def test_interview_can_invite_the_candidate_with_teams_link(
    client: TestClient, session_factory: sessionmaker[Session], graph: FakeGraph
) -> None:
    _connect_outlook(session_factory)
    submission = _interview_submission(client, email="karla@example.com")
    response = client.post(
        f"/api/v1/submissions/{submission['id']}/interviews",
        json={
            "scheduled_at": "2026-11-12T14:00:00",
            "interview_type": "video",
            "notes": "INTERN: nicht erwaehnen",
            "invite_candidate": True,
            "teams_meeting": True,
        },
    )
    assert response.status_code == 201, response.text
    sent = graph.created[0]
    assert sent["attendees"][0][0] == "karla@example.com"
    assert sent["online_meeting"] is True
    assert "INTERN" not in sent["body_text"]
    assert "Vorstellungsgespraech" in sent["body_text"]

    # Verschieben informiert den Kandidaten ueber die aktualisierte Einladung.
    interview_id = response.json()["id"]
    moved = client.patch(
        f"/api/v1/submissions/{submission['id']}/interviews/{interview_id}",
        json={"scheduled_at": "2026-11-13T15:00:00"},
    )
    assert moved.status_code == 200
    assert len(graph.updated) == 1


def test_interview_invite_is_refused_without_candidate_email_or_outlook(
    client: TestClient, session_factory: sessionmaker[Session], graph: FakeGraph
) -> None:
    no_mail = _interview_submission(client, email=None)
    _connect_outlook(session_factory)
    payload = {
        "scheduled_at": "2026-11-12T14:00:00",
        "interview_type": "video",
        "invite_candidate": True,
    }
    refused = client.post(f"/api/v1/submissions/{no_mail['id']}/interviews", json=payload)
    assert refused.status_code >= 400
    assert client.get(f"/api/v1/submissions/{no_mail['id']}/interviews").json() == []

    teams_only = client.post(
        f"/api/v1/submissions/{no_mail['id']}/interviews",
        json={**payload, "invite_candidate": False, "teams_meeting": True},
    )
    assert teams_only.status_code >= 400
    assert graph.created == []


def test_interview_invite_without_connected_outlook_is_refused(
    client: TestClient, graph: FakeGraph
) -> None:
    submission = _interview_submission(client, email="karla@example.com")
    response = client.post(
        f"/api/v1/submissions/{submission['id']}/interviews",
        json={
            "scheduled_at": "2026-11-12T14:00:00",
            "interview_type": "video",
            "invite_candidate": True,
        },
    )
    assert response.status_code >= 400
    assert "Microsoft" in response.text


def _interview_submission(client: TestClient, *, email: str | None) -> dict[str, Any]:
    candidate = client.post(
        "/api/v1/candidates",
        json={"first_name": "Karla", "last_name": "Kandidatin", "email": email},
    ).json()
    company = client.post("/api/v1/clients", json={"name": "Kanzlei Z", "status": "active"}).json()
    submission = client.post(
        "/api/v1/submissions",
        json={"candidate_id": candidate["id"], "client_company_id": company["id"]},
    ).json()
    for target in ("cv_in", "cv_out", "interview"):
        response = client.patch(
            f"/api/v1/submissions/{submission['id']}/transition", json={"status": target}
        )
        assert response.status_code == 200, response.text
    return submission
