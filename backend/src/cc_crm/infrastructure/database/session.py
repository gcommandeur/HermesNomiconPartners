from collections.abc import Generator

from sqlalchemy import Engine, create_engine, event
from sqlalchemy.orm import Session, sessionmaker

from cc_crm.core.config import get_settings


def register_sqlite_unicode_lower(engine: Engine) -> None:
    """SQLites eingebautes lower() ist ASCII-only (lower('MÜLLER') bleibt
    'MÜLLER') - unsere dialektuebergreifende Suche verlaesst sich aber auf
    LOWER()-Vergleiche (ilike() kompiliert auf SQLite zu lower(x) LIKE
    lower(y)), damit sie auf SQLite (lokale Entwicklung) genauso funktioniert
    wie auf Postgres (natives ILIKE). Ohne diesen Fix wuerde z.B. die Suche
    nach "öztürk" einen gespeicherten Namen "Öztürk" auf SQLite nicht finden.
    Python's str.lower() beherrscht Unicode korrekt und wird hier als eigene
    SQL-Funktion registriert, die SQLite's eingebautes lower() ueberschreibt -
    pro Verbindung, da SQLite Funktionen nicht global sondern je Connection
    registriert werden. Kein Effekt auf Postgres (dort greift native ILIKE)."""
    if not engine.dialect.name.startswith("sqlite"):
        return

    @event.listens_for(engine, "connect")
    def _register_unicode_lower(dbapi_connection: object, _connection_record: object) -> None:
        dbapi_connection.create_function(  # type: ignore[attr-defined]
            "lower", 1, lambda value: value.lower() if value is not None else None
        )


def build_engine(database_url: str, *, echo: bool = False) -> Engine:
    # A misconfigured/unreachable Postgres host (e.g. falling back to the
    # default DATABASE_URL because .env wasn't found) would otherwise hang
    # for minutes per request on the OS-level TCP timeout instead of failing
    # fast - cap it at 5s so the error surfaces immediately.
    connect_args: dict[str, object] = (
        {"check_same_thread": False}
        if database_url.startswith("sqlite")
        else {"connect_timeout": 5}
    )
    engine = create_engine(
        database_url,
        echo=echo,
        pool_pre_ping=True,
        connect_args=connect_args,
    )
    register_sqlite_unicode_lower(engine)
    return engine


settings = get_settings()
engine = build_engine(settings.resolved_database_url, echo=settings.sql_echo)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def get_db_session() -> Generator[Session, None, None]:
    with SessionLocal() as session:
        yield session
