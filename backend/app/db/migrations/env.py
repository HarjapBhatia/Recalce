"""
app/db/migrations/env.py
-------------------------
Alembic environment configuration.

Reads the database URL from our app settings (which loads .env) and
imports all ORM models via app.db.base so autogenerate can detect
every table in the project.
"""

from logging.config import fileConfig

from sqlalchemy import engine_from_config, pool

from alembic import context

from app.core.config import settings
from app.db.base import Base  # noqa: F401 -- triggers model registration

# -- Alembic Config object ---------------------------------------------------
# Provides access to values within the .ini file.
config = context.config

# Override the sqlalchemy.url from alembic.ini with the value from .env.
# This avoids hardcoding database credentials in a tracked config file.
config.set_main_option("sqlalchemy.url", settings.DATABASE_URL)

# Set up Python logging from the config file.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Point Alembic at our models' metadata so autogenerate works.
target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """
    Run migrations in 'offline' mode.

    Configures the context with just a URL (no live Engine needed).
    Calls to context.execute() emit SQL strings to the script output.
    """
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """
    Run migrations in 'online' mode.

    Creates an Engine and associates a connection with the context so
    migrations execute against the live database.
    """
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
