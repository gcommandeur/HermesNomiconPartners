from datetime import datetime


def naive_utc(value: datetime) -> datetime:
    """Normalize to a naive UTC wall-clock value.

    SQLite drops tzinfo on round-trip through DateTime(timezone=True) columns,
    so a freshly-inserted (aware) value and one re-read from the database
    (naive) are not directly comparable. Stripping tzinfo on both sides keeps
    comparisons correct on SQLite and Postgres alike.
    """
    return value.replace(tzinfo=None) if value.tzinfo is not None else value
