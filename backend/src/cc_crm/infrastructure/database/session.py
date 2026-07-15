from collections.abc import Generator

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker

from cc_crm.core.config import get_settings


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
    return create_engine(
        database_url,
        echo=echo,
        pool_pre_ping=True,
        connect_args=connect_args,
    )


settings = get_settings()
engine = build_engine(settings.resolved_database_url, echo=settings.sql_echo)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def get_db_session() -> Generator[Session, None, None]:
    with SessionLocal() as session:
        yield session
