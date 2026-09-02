"""Alembic-Anbindung an die App.

Die Verbindungsdaten kommen aus der .env ueber app.config, nicht aus der
alembic.ini. So gibt es nur eine Stelle, an der die Datenbank konfiguriert ist.
"""

from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

from app.config import Config
from app.extensions import Basis

# Alle Modelle einmal importieren, damit die Tabellen in den Metadaten stehen.
from app import models  # noqa: F401

config = context.config
config.set_main_option(
    "sqlalchemy.url", Config.SQLALCHEMY_DATABASE_URI.replace("%", "%%")
)

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Basis.metadata


def run_migrations_offline() -> None:
    context.configure(
        url=config.get_main_option("sqlalchemy.url"),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    motor = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with motor.connect() as verbindung:
        context.configure(
            connection=verbindung,
            target_metadata=target_metadata,
            compare_type=True,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
