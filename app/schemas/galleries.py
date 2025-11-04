"""Gallery schemas matching OpenAPI spec."""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class GalleryBase(BaseModel):
    """Base gallery fields."""

    name: str = Field(..., min_length=1, max_length=200)
    description: Optional[str] = Field(None, max_length=2000)
    thumbnail_color: Optional[str] = Field(None, pattern="^#[0-9A-Fa-f]{6}$", alias="thumbnailColor")
    thumbnail_overlay: Optional[str] = Field(None, pattern="^#[0-9A-Fa-f]{6}$", alias="thumbnailOverlay")
    tags: Optional[list[str]] = Field(None, max_items=20)

    class Config:
        populate_by_name = True


class GalleryCreate(GalleryBase):
    """Gallery creation request."""

    pass


class GalleryUpdate(BaseModel):
    """Gallery update request (all fields optional)."""

    name: Optional[str] = Field(None, min_length=1, max_length=200)
    description: Optional[str] = Field(None, max_length=2000)
    thumbnail_color: Optional[str] = Field(None, pattern="^#[0-9A-Fa-f]{6}$", alias="thumbnailColor")
    thumbnail_overlay: Optional[str] = Field(None, pattern="^#[0-9A-Fa-f]{6}$", alias="thumbnailOverlay")
    tags: Optional[list[str]] = Field(None, max_items=20)

    class Config:
        populate_by_name = True


class GalleryResponse(GalleryBase):
    """Gallery response model."""

    id: str
    product_count: int = Field(..., alias="productCount")
    asset_count: int = Field(..., alias="assetCount")
    status: str
    created_at: datetime = Field(..., alias="createdAt")
    updated_at: Optional[datetime] = Field(None, alias="updatedAt")

    class Config:
        from_attributes = True
        populate_by_name = True


class GalleryListResponse(BaseModel):
    """Paginated gallery list response."""

    items: list[GalleryResponse]
    meta: dict
