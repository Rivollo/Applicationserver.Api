"""
Product link schemas for API operations.
"""

from typing import Optional, List

from pydantic import BaseModel, Field, HttpUrl


# ---------- Link Type Response ----------

class ProductLinkTypeResponse(BaseModel):
    """Response schema for product link types."""

    id: int
    name: str
    description: Optional[str] = None


# ---------- Create / Update Schemas ----------

class ProductLinkCreate(BaseModel):
    """Schema for creating a product link."""

    name: str = Field(
        ...,
        min_length=1,
        max_length=200,
        description="Display name for the link"
    )
    link: HttpUrl = Field(
        ...,
        description="Valid URL for the product link"
    )
    description: Optional[str] = Field(
        None,
        max_length=500,
        description="Optional description for the link"
    )
    link_type: Optional[int] = Field(
        None,
        description="ID from tbl_product_link_type"
    )

    class Config:
        extra = "forbid"


class ProductLinkUpdate(BaseModel):
    """Schema for updating a product link."""

    name: Optional[str] = Field(
        None,
        min_length=1,
        max_length=200
    )
    link: Optional[HttpUrl] = None
    description: Optional[str] = Field(
        None,
        max_length=500
    )
    link_type: Optional[int] = None

    class Config:
        extra = "forbid"


# ---------- Response Schema ----------

class ProductLinkResponse(BaseModel):
    """Response schema for product links."""

    id: int
    name: str
    link: str
    description: Optional[str] = None
    link_type_id: Optional[int] = None
    link_type_name: Optional[str] = None


# ---------- Bulk Create Schema (CRITICAL) ----------

class BulkProductLinkCreate(BaseModel):
    """Schema for bulk creating product links."""

    links: List[ProductLinkCreate] = Field(
        ...,
        min_items=1,
        description="List of links to create (at least one required)"
    )

    class Config:
        extra = "forbid"
