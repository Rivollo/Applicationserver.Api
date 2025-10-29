"""Dashboard schemas matching OpenAPI spec."""

from typing import Any, Optional

from pydantic import BaseModel, Field


class ResumeCard(BaseModel):
    """Resume card for quick access."""

    product_id: str = Field(..., alias="productId")
    product_name: str = Field(..., alias="productName")
    status: str
    thumbnail_url: Optional[str] = Field(None, alias="thumbnailUrl")
    progress: Optional[int] = Field(None, ge=0, le=100)

    class Config:
        populate_by_name = True


class InsightCard(BaseModel):
    """Insight card with analytics."""

    type: str = Field(..., description="Type: views, engagement, topProduct")
    title: str
    value: str
    change: Optional[str] = None
    icon: Optional[str] = None


class DashboardOverviewResponse(BaseModel):
    """Dashboard overview response."""

    resume: list[ResumeCard]
    insights: list[InsightCard]
