from __future__ import annotations

from typing import AsyncGenerator, Optional

from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import settings

_engine: Optional[AsyncEngine] = None
_SessionLocal: Optional[async_sessionmaker[AsyncSession]] = None


def _ensure_async_url(url: str) -> str:
	"""Ensure the SQLAlchemy URL uses the asyncpg driver.

	Handles common provider formats like:
	- postgresql://...
	- postgres://...
	- postgresql+psycopg://... (or +psycopg2)

	Returns the URL unchanged if it's already asyncpg.
	"""
	# Already async
	if url.startswith("postgresql+asyncpg://"):
		return url

	# Normalize short scheme used by some providers (e.g. "postgres://")
	if url.startswith("postgres://"):
		return url.replace("postgres://", "postgresql+asyncpg://", 1)

	# Upgrade plain postgresql to asyncpg
	if url.startswith("postgresql://"):
		return url.replace("postgresql://", "postgresql+asyncpg://", 1)

	# Migrate psycopg/psycopg2 URLs to asyncpg for async engine
	if url.startswith("postgresql+psycopg2://"):
		return url.replace("postgresql+psycopg2://", "postgresql+asyncpg://", 1)
	if url.startswith("postgresql+psycopg://"):
		return url.replace("postgresql+psycopg://", "postgresql+asyncpg://", 1)

	return url


def init_engine_and_session() -> None:
	global _engine, _SessionLocal
	if _engine is not None:
		return
	if not settings.DATABASE_URL:
		raise RuntimeError("DATABASE_URL is not configured. Set it in the environment or .env file.")
	database_url = _ensure_async_url(settings.DATABASE_URL)
	_engine = create_async_engine(database_url, pool_pre_ping=True, future=True)
	_SessionLocal = async_sessionmaker(bind=_engine, expire_on_commit=False)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
	if _SessionLocal is None:
		init_engine_and_session()
	assert _SessionLocal is not None
	async with _SessionLocal() as session:
		yield session
