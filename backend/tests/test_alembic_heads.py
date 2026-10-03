"""Die Migrationskette darf nur EINEN Head haben - zwei parallele Sitzungen
(Laptop und Cloud) koennen sonst unbemerkt je eine Migration an denselben Vorgaenger
haengen, und `alembic upgrade head` bricht beim Deploy ab."""

from alembic.config import Config
from alembic.script import ScriptDirectory

from cc_crm.core.config import _BACKEND_ROOT


def test_exactly_one_alembic_head() -> None:
    config = Config(str(_BACKEND_ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(_BACKEND_ROOT / "alembic"))
    heads = ScriptDirectory.from_config(config).get_heads()
    assert len(heads) == 1, f"Mehrere Alembic-Heads: {heads} - Migrationen zusammenfuehren (merge)."
