"""Alembic environment.

This project does not use an ORM for identity/tenancy tables (see
04-STACK-AND-SERVICES.md: "Alembic with explicitly managed SQL migrations --
no duplicate ORM ownership of identity tables"). Migrations are plain SQL
executed via `op.execute(...)`. SQLAlchemy is used here only as Alembic's
connection/transaction driver (psycopg3 dialect), never as an ORM layer.
"""
import sys
from logging.config import fileConfig
from pathlib import Path

from alembic import context
from sqlalchemy import create_engine

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.config import settings  # noqa: E402

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = None


def get_sqlalchemy_url() -> str:
    url = settings().database_url
    if not url:
        raise RuntimeError("DATABASE_URL is required to run migrations.")
    # Force the psycopg3 dialect regardless of how the URL was written.
    if url.startswith("postgresql://"):
        url = url.replace("postgresql://", "postgresql+psycopg://", 1)
    elif url.startswith("postgres://"):
        url = url.replace("postgres://", "postgresql+psycopg://", 1)
    return url


def run_migrations_offline() -> None:
    context.configure(
        url=get_sqlalchemy_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = create_engine(get_sqlalchemy_url(), pool_pre_ping=True)
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
