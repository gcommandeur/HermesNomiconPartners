from logging.config import fileConfig

from sqlalchemy import engine_from_config, pool

from alembic import context
from cc_crm.core.config import get_settings
from cc_crm.models import Base

config = context.config

# Beim programmatischen Aufruf aus der App (core/migrations.py) NICHT das
# Logging neu konfigurieren: fileConfig() ersetzt sonst die Handler der App
# (JSON-Logs, core/observability.py) und schaltet vorhandene Logger ab.
if config.config_file_name is not None and config.attributes.get("configure_logger", True):
    fileConfig(config.config_file_name, disable_existing_loggers=False)

config.set_main_option("sqlalchemy.url", get_settings().resolved_database_url)
target_metadata = Base.metadata


def include_object(
    obj: object, name: str | None, type_: str, reflected: bool, compare_to: object
) -> bool:
    """Die Trigram-Indizes (ix_trgm_*, Migration 7c1e651c4844) gibt es nur unter
    Postgres und per Roh-SQL - sie stehen bewusst nicht in den Modellen. Ohne
    diesen Filter meldet `alembic check` sie als "zu entfernen"."""
    return not (
        type_ == "index" and reflected and name is not None and name.startswith("ix_trgm_")
    )


def run_migrations_offline() -> None:
    context.configure(
        url=config.get_main_option("sqlalchemy.url"),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
        include_object=include_object,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
            include_object=include_object,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
