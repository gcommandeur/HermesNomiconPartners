import logging

from alembic.config import Config

from alembic import command
from cc_crm.core.config import _BACKEND_ROOT

logger = logging.getLogger(__name__)


def ensure_database_at_head() -> None:
    """Run `alembic upgrade head` on process startup so the app can never
    serve requests against a half-migrated or stale-schema database - the
    same class of "silently works against the wrong state" bug already fixed
    for .env/DB-path resolution in core/config.py, just for the schema
    instead of the file path."""
    config = Config(str(_BACKEND_ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(_BACKEND_ROOT / "alembic"))
    config.attributes["configure_logger"] = False  # App-Logging nicht ueberschreiben
    try:
        command.upgrade(config, "head")
    except Exception:
        logger.exception("Automatic 'alembic upgrade head' on startup failed")
        raise


def script_head() -> str | None:
    """Neuester Migrationsstand laut Code (None, wenn es mehrere Heads gibt)."""
    from alembic.script import ScriptDirectory

    config = Config(str(_BACKEND_ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(_BACKEND_ROOT / "alembic"))
    heads = ScriptDirectory.from_config(config).get_heads()
    return heads[0] if len(heads) == 1 else None
