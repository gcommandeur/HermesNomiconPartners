"""Outlook-Termine ohne Betreff duerfen die Terminliste nicht abstuerzen lassen.

Live-Fehler 2026-10-05: ValidationError string_too_short auf CalendarEventRead.title -> 500.
"""

import uuid
from datetime import UTC, datetime

from cc_crm.schemas.calendar_event import CalendarEventRead
from cc_crm.services.calendar_graph_sync import NO_TITLE, _title_from_graph


def test_missing_or_blank_subject_gets_a_placeholder() -> None:
    assert _title_from_graph(None) == NO_TITLE
    assert _title_from_graph("") == NO_TITLE
    assert _title_from_graph("   ") == NO_TITLE


def test_subject_is_kept_and_cut_to_the_field_limit() -> None:
    assert _title_from_graph("  Interview  ") == "Interview"
    assert len(_title_from_graph("x" * 300)) == 240


def test_reading_an_old_event_with_an_empty_title_does_not_fail() -> None:
    now = datetime.now(UTC)
    event = CalendarEventRead.model_validate(
        {
            "id": uuid.uuid4(),
            "created_at": now,
            "updated_at": now,
            "title": "",
            "start_at": now,
            "owner_user_id": uuid.uuid4(),
            "created_by_user_id": uuid.uuid4(),
        }
    )
    assert event.title == ""
