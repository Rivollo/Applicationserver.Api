"""Support contact schemas."""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class SupportCreateRequest(BaseModel):
    """Request to create a support contact entry."""

    fullname: str = Field(..., min_length=1, max_length=255, description="Full name of the user")
    comment: Optional[str] = Field(None, max_length=5000, description="Comment or message from the user")
    userid: str = Field(..., description="User ID (UUID) of the user submitting the support request")


class SupportResponse(BaseModel):
    """Support contact response model."""

    id: int
    fullname: str
    comment: Optional[str] = None
    isactive: bool
    created_by: Optional[str] = None
    created_date: datetime
    updated_by: Optional[str] = None
    updated_date: Optional[datetime] = None

    class Config:
        from_attributes = True

