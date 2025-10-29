from __future__ import annotations

import asyncio
from logging.config import fileConfig
from typing import Dict, Any

from alembic import context
from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config

from app.core.config import settings
from app.models import Base

config = context.config


def _get_database_url() -> str:
	url = settings.DATABASE_URL
	if not url:
		raise RuntimeError("DATABASE_URL is not configured; cannot run migrations.")
	if url.startswith("postgresql+asyncpg://"):
		return url.replace("postgresql+asyncpg://", "postgresql+psycopg://", 1)
	if url.startswith("postgresql://"):
		return url.replace("postgresql://", "postgresql+psycopg://", 1)
	return url


if config.config_file_name is not None:
	fileConfig(config.config_file_name)

target_metadata = Base.metadata

config.set_main_option("sqlalchemy.url", _get_database_url())


def run_migrations_offline() -> None:
	context.configure(
		url=config.get_main_option("sqlalchemy.url"),
		target_metadata=target_metadata,
		literal_binds=True,
		dialect_opts={"paramstyle": "named"},
	)

	with context.begin_transaction():
		context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
	context.configure(connection=connection, target_metadata=target_metadata)

	with context.begin_transaction():
		context.run_migrations()


async def run_migrations_online() -> None:
	configuration: Dict[str, Any] = config.get_section(config.config_ini_section, {})
	configuration["sqlalchemy.url"] = config.get_main_option("sqlalchemy.url")

	connectable = async_engine_from_config(
		configuration,
		prefix="sqlalchemy.",
		poolclass=pool.NullPool,
	)

	async with connectable.connect() as connection:
		await connection.run_sync(do_run_migrations)

	await connectable.dispose()


if context.is_offline_mode():
	run_migrations_offline()
else:
	asyncio.run(run_migrations_online())
