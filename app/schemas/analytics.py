"""Analytics schemas matching OpenAPI spec."""

from datetime import date
from typing import Any, Optional

from pydantic import BaseModel, Field


class AnalyticsSummary(BaseModel):
    """Analytics summary metrics."""

    views: int = Field(..., ge=0)
    engaged: int = Field(..., ge=0, alias="engagedViews")
    adds_from_3d: int = Field(..., ge=0, alias="addsFrom3D")

    class Config:
        populate_by_name = True


class TimeSeriesPoint(BaseModel):
    """A single data point in time series."""

    date: date
    value: int = Field(..., ge=0)


class AnalyticsTimeSeries(BaseModel):
    """Time series analytics data."""

    label: str
    data: list[TimeSeriesPoint]


class AnalyticsOverviewResponse(BaseModel):
    """Analytics overview response."""

    summary: AnalyticsSummary
    time_series: list[AnalyticsTimeSeries] = Field(..., alias="timeSeries")
    top_products: list[dict[str, Any]] = Field(default_factory=list, alias="topProducts")

    class Config:
        populate_by_name = True
