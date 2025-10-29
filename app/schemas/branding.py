"""Branding schemas matching OpenAPI spec."""

from typing import Optional

from pydantic import BaseModel, Field


class BrandingResponse(BaseModel):
    """Organization branding response."""

    logo_url: Optional[str] = Field(None, alias="logoUrl")
    primary_color: str = Field(default="#2563EB", pattern="^#[0-9A-Fa-f]{6}$", alias="primaryColor")
    secondary_color: Optional[str] = Field(None, pattern="^#[0-9A-Fa-f]{6}$", alias="secondaryColor")
    company_name: Optional[str] = Field(None, max_length=200, alias="companyName")
    tagline: Optional[str] = Field(None, max_length=500)

    class Config:
        populate_by_name = True


class BrandingUpdate(BaseModel):
    """Branding update request (all fields optional)."""

    logo_url: Optional[str] = Field(None, alias="logoUrl")
    primary_color: Optional[str] = Field(None, pattern="^#[0-9A-Fa-f]{6}$", alias="primaryColor")
    secondary_color: Optional[str] = Field(None, pattern="^#[0-9A-Fa-f]{6}$", alias="secondaryColor")
    company_name: Optional[str] = Field(None, max_length=200, alias="companyName")
    tagline: Optional[str] = Field(None, max_length=500)

    class Config:
        populate_by_name = True
