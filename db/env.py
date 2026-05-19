"""Alembic migration environment for the `aero_provenance` database.

The connection string is read from the AERO_PROVENANCE_DSN environment
variable (never from alembic.ini) — it carries a password. Migrations are
raw SQL (`op.execute`), so there is no ORM `target_metadata`.
"""

from __future__ import annotations

import os
from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Raw-SQL migrations — no SQLAlchemy model metadata to autogenerate against.
target_metadata = None


def _dsn() -> str:
    """The `aero_provenance` DSN from the environment, or fail loud."""
    dsn = os.environ.get("AERO_PROVENANCE_DSN")
    if not dsn:
        raise RuntimeError(
            "AERO_PROVENANCE_DSN is not set — alembic needs the aero_provenance "
            "connection string (postgresql://...). See ADR-004."
        )
    return dsn


def run_migrations_offline() -> None:
    """Emit migration SQL without a live DB connection (`alembic upgrade --sql`)."""
    context.configure(
        url=_dsn(),
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations against a live connection."""
    section = config.get_section(config.config_ini_section) or {}
    section["sqlalchemy.url"] = _dsn()
    connectable = engine_from_config(section, prefix="sqlalchemy.", poolclass=pool.NullPool)
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
