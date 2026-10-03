"""Zeitzonen-neutrale Vergleiche fuer Tests, die unter SQLite UND Postgres laufen.

SQLite gibt Zeitstempel ohne Zeitzone zurueck ("2026-08-10T14:00:00"), Postgres
mit ("2026-08-10T14:00:00Z" bzw. aware datetime). Beides meint denselben
Zeitpunkt; Tests sollen den Zeitpunkt pruefen, nicht die Darstellung."""

from datetime import UTC, datetime


def utc_naive(value: str | datetime) -> datetime:
    """Zeitpunkt als naive UTC-Zeit (Offset/Zeitzone wird umgerechnet und entfernt)."""
    if isinstance(value, str):
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    else:
        parsed = value
    if parsed.tzinfo is not None:
        parsed = parsed.astimezone(UTC).replace(tzinfo=None)
    return parsed
