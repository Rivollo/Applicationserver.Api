"""Product link schemas for API operations.
"""

from typing import Optional

from pydantic import BaseModel, Field


class ProductLinkTypeResponse(BaseModel):
    """Response schema for product link types."""

    id: int
    name: str
    description: Optional[str] = None


class ProductLinkCreate(BaseModel):
    """Schema for creating a product link."""

    name: str = Field(..., description="Display name for the link")
    link: str = Field(..., description="URL or link value")
    description: Optional[str] = None
    link_type: Optional[int] = Field(None, description="ID from tbl_product_link_type")


class ProductLinkUpdate(BaseModel):
    """Schema for updating a product link."""

    name: Optional[str] = None
    link: Optional[str] = None
    description: Optional[str] = None
    link_type: Optional[int] = None


class ProductLinkResponse(BaseModel):
    """Response schema for product links."""

    id: int
    name: str
    link: str
    description: Optional[str] = None
    link_type_id: Optional[int] = None
    link_type_name: Optional[str] = None


class BulkProductLinkCreate(BaseModel):
    """Schema for bulk creating product links."""

    links: list[ProductLinkCreate] = Field(
        default_factory=list,
        description="List of links to create"
    )
