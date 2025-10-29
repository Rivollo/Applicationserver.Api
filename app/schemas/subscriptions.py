"""Subscription and plan schemas matching OpenAPI spec."""

from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, Field


class QuotaUsage(BaseModel):
    """Quota usage information."""

    included: int = Field(..., ge=0)
    purchased: int = Field(default=0, ge=0)
    used: int = Field(..., ge=0)


class QuotaInfo(BaseModel):
    """Quota information for a resource."""

    used: int = Field(..., ge=0)
    limit: Optional[int] = Field(None, description="null means unlimited")


class TrialInfo(BaseModel):
    """Trial period information."""

    active: bool
    days_remaining: int = Field(..., ge=0, le=7, alias="daysRemaining")
    started_at: Optional[datetime] = Field(None, alias="startedAt")

    class Config:
        populate_by_name = True


class SubscriptionMe(BaseModel):
    """Current user's subscription information."""

    plan: str = Field(..., description="Plan code: free, pro, enterprise")
    trial: TrialInfo
    quotas: dict[str, Any]


class PlanFeature(BaseModel):
    """Plan feature description."""

    label: str
    available: bool


class Plan(BaseModel):
    """Subscription plan details."""

    name: str
    price_inr: int = Field(..., ge=0, alias="priceINR")
    description: str = Field(..., max_length=500)
    features: list[PlanFeature]
    featured: bool = False

    class Config:
        populate_by_name = True


class PlanList(BaseModel):
    """List of available plans."""

    plans: list[Plan]
