from fastapi import APIRouter, Depends, Header
from sqlalchemy.orm import Session
from typing import Optional

from app.api.deps import create_access_token
from app.core.db import get_db
from app.models.models import User
from app.schemas.auth import LoginRequest, LoginResponse
from app.utils.envelopes import api_success

router = APIRouter(tags=["auth"])


@router.post("/auth/login")
def login(payload: LoginRequest, db: Session = Depends(get_db)):
	# Upsert minimal user by email
	user = db.query(User).filter(User.email == payload.email).one_or_none()
	if user is None:
		user = User(email=payload.email)
		db.add(user)
		db.commit()
		db.refresh(user)
	token = create_access_token(subject=str(user.id))
	return api_success(LoginResponse(token=token).model_dump())
