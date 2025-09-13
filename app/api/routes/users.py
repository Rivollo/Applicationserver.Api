from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user_id
from app.core.db import get_db
from app.models.models import User
from app.schemas.auth import UserResponse
from app.utils.envelopes import api_success

router = APIRouter(tags=["users"])


@router.get("/users/me")
def get_me(user_id: str = Depends(get_current_user_id), db: Session = Depends(get_db)):
	user = db.query(User).filter(User.id == user_id).one_or_none()
	if user is None:
		raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Unauthorized")
	return api_success(UserResponse(id=str(user.id), email=user.email).model_dump())
