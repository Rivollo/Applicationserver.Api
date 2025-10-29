from __future__ import annotations

from typing import AsyncGenerator, Optional

from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import settings

_engine: Optional[AsyncEngine] = None
_SessionLocal: Optional[async_sessionmaker[AsyncSession]] = None


def _ensure_async_url(url: str) -> str:
	if url.startswith("postgresql+asyncpg://"):
		return url
	if url.startswith("postgresql://"):
		return url.replace("postgresql://", "postgresql+asyncpg://", 1)
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
