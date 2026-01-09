"""Dimension schemas for product measurements.

This module contains Pydantic schemas for dimension-related API operations.
Follows the same patterns as subscriptions.py schemas.
"""

from typing import List, Optional

from pydantic import BaseModel, Field


# === Dimension Position Schemas ===


class DimensionPosition(BaseModel):
    """3D position for dimension hotspot."""

    x: float
    y: float
    z: float


class DimensionHotspot(BaseModel):
    """Start / End hotspot for a dimension."""

    type: str = Field(..., description="Hotspot type: 'start' or 'end'")
    title: str
    position: DimensionPosition


class DimensionItem(BaseModel):
    """Single dimension with measurement data and hotspots."""

    name: str = Field(..., description="Dimension name, e.g. 'Seat Width', 'Back Height'")
    value: float
    unit: Optional[str] = Field("cm", description="Measurement unit")
    hotspots: List[DimensionHotspot]


# === Response Schemas ===


class DimensionSaveResponse(BaseModel):
    """Response after saving dimensions."""

    product_id: str
    message: str


class DimensionHotspotData(BaseModel):
    """Hotspot data in dimension response."""

    id: str
    title: str
    position: DimensionPosition


class DimensionData(BaseModel):
    """Single dimension data for API response."""

    value: float
    unit: str
    hotspots: List[DimensionHotspotData]


class DimensionsResponse(BaseModel):
    """Dimensions data structure for product assets response.

    The dimensions are keyed by dimension type (e.g., 'width', 'height').
    """

    dimension_name: str
    # Additional dimension types are added dynamically


# === List-based Response Schemas (for GET /dimensions) ===


class DimensionHotspotResponse(BaseModel):
    """Hotspot in dimension response with type indicator."""

    id: str
    type: str = Field(..., description="Hotspot type: 'start' or 'end'")
    title: str
    position: DimensionPosition


class DimensionItemResponse(BaseModel):
    """Single dimension in GET response."""

    name: str
    value: float
    unit: str
    hotspots: List[DimensionHotspotResponse]


class DimensionDeleteResponse(BaseModel):
    """Response after deleting dimensions."""

    product_id: str
    message: str
