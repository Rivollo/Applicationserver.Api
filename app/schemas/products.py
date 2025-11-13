"""Product schemas matching OpenAPI spec."""

from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, Field


# === Core Product Schemas ===


class ProductBase(BaseModel):
    """Base product fields."""

    name: str = Field(..., min_length=1, max_length=200)
    description: Optional[str] = Field(None, max_length=2000)
    brand: Optional[str] = Field(None, max_length=100)
    accent_color: Optional[str] = Field(None, pattern="^#[0-9A-Fa-f]{6}$")
    accent_overlay: Optional[str] = Field(None, pattern="^#[0-9A-Fa-f]{6}$")
    tags: Optional[list[str]] = Field(None, max_items=20)


class ProductCreate(ProductBase):
    """Product creation request."""

    pass


class ProductUpdate(BaseModel):
    """Product update request (all fields optional)."""

    name: Optional[str] = Field(None, min_length=1, max_length=200)
    description: Optional[str] = Field(None, max_length=2000)
    brand: Optional[str] = Field(None, max_length=100)
    accent_color: Optional[str] = Field(None, pattern="^#[0-9A-Fa-f]{6}$")
    accent_overlay: Optional[str] = Field(None, pattern="^#[0-9A-Fa-f]{6}$")
    tags: Optional[list[str]] = Field(None, max_items=20)


class ConfiguratorSettings(BaseModel):
    """3D product configurator settings."""

    materials: Optional[list[dict[str, Any]]] = None
    variants: Optional[list[dict[str, Any]]] = None
    hotspots: Optional[list[dict[str, Any]]] = None
    links: Optional[list[dict[str, Any]]] = None
    settings: Optional[dict[str, Any]] = None
    notes: Optional[str] = None


class ProductResponse(ProductBase):
    """Product response model."""

    id: str
    status: str
    ready_metric: Optional[str] = None
    processing_progress: Optional[int] = None
    failure_reason: Optional[str] = None
    created_at: datetime
    updated_at: Optional[datetime] = None
    configurator: Optional[ConfiguratorSettings] = None

    class Config:
        from_attributes = True


class ProductListResponse(BaseModel):
    """Paginated product list response."""

    items: list[ProductResponse]
    meta: dict[str, Any]


class PublishProductRequest(BaseModel):
    """Publish/unpublish request."""

    publish: bool


class PublishProductResponse(BaseModel):
    """Response after publishing/unpublishing."""

    published: bool
    published_at: Optional[datetime] = None


class ProductImageItem(BaseModel):
    """Image item in product assets response."""

    url: str
    type: str


class ProductAssetsData(BaseModel):
    """Product assets data."""

    id: str
    name: str
    status: str
    meshurl: Optional[str] = None
    images: list[ProductImageItem] = Field(default_factory=list)


class ProductAssetsResponse(BaseModel):
    """Response containing product assets."""

    data: ProductAssetsData


class ProductStatusData(BaseModel):
    """Product status data when not ready."""

    id: str
    name: str
    status: str
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class ProductStatusResponse(BaseModel):
    """Response containing product status."""

    data: ProductStatusData


# === Hotspot Schemas ===


class HotspotPosition(BaseModel):
    """3D position for hotspot."""

    x: float = Field(..., ge=-1.0, le=1.0)
    y: float = Field(..., ge=-1.0, le=1.0)
    z: float = Field(..., ge=-1.0, le=1.0)


class HotspotCreate(BaseModel):
    """Create hotspot request."""

    title: str
    description: str
    position: HotspotPosition
    text_font: Optional[str] = None
    text_color: Optional[str] = None
    bg_color: Optional[str] = None
    action_type: str = "none"
    action_payload: dict[str, Any] = Field(default_factory=dict)


class HotspotResponse(BaseModel):
    """Hotspot response model."""

    id: str
    title: str
    description: str
    position: HotspotPosition
    text_font: Optional[str] = None
    text_color: Optional[str] = None
    bg_color: Optional[str] = None
    action_type: str
    action_payload: dict[str, Any]
    order_index: int
    created_at: datetime

    class Config:
        from_attributes = True
