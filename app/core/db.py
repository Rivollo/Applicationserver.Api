from typing import Generator, Optional
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session

from app.core.config import settings

_engine = None
_SessionLocal: Optional[sessionmaker] = None


def init_engine_and_session() -> None:
	global _engine, _SessionLocal
	if _engine is not None:
		return
	if not settings.DATABASE_URL:
		raise RuntimeError("DATABASE_URL is not configured. Set it in the environment or .env file.")
	_engine = create_engine(settings.DATABASE_URL, pool_pre_ping=True, future=True)
	_SessionLocal = sessionmaker(bind=_engine, autocommit=False, autoflush=False, future=True)


def get_db() -> Generator[Session, None, None]:
	if _SessionLocal is None:
		init_engine_and_session()
	assert _SessionLocal is not None
	db = _SessionLocal()
	try:
		yield db
	finally:
		db.close()
