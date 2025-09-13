from pydantic import BaseModel, Field, EmailStr
from typing import Optional, List, Any


class ApiEnvelope(BaseModel):
	success: bool
	data: Optional[Any] = None
	error: Optional[dict] = None


class LoginRequest(BaseModel):
	email: EmailStr


class LoginResponse(BaseModel):
	token: str


class UserResponse(BaseModel):
	id: str
	email: EmailStr
