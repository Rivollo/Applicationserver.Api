from datetime import datetime, timedelta
from typing import Optional
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import jwt, JWTError
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.db import get_db


bearer_scheme = HTTPBearer(auto_error=False)


class AuthTokenData:
	def __init__(self, sub: str):
		self.sub = sub


def create_access_token(subject: str, expires_delta: Optional[timedelta] = None) -> str:
	if expires_delta is None:
		expires_delta = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRES_MINUTES)
	exp = datetime.utcnow() + expires_delta
	to_encode = {"sub": subject, "exp": exp}
	return jwt.encode(to_encode, settings.JWT_SECRET, algorithm=settings.JWT_ALGORITHM)


def get_current_user_id(
	credentials: Optional[HTTPAuthorizationCredentials] = Depends(bearer_scheme),
	_: Session = Depends(get_db),
) -> str:
	if credentials is None or not credentials.scheme.lower() == "bearer":
		raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")
	try:
		payload = jwt.decode(credentials.credentials, settings.JWT_SECRET, algorithms=[settings.JWT_ALGORITHM])
		sub: str = payload.get("sub")
		if sub is None:
			raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")
		return sub
	except JWTError:
		raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")
