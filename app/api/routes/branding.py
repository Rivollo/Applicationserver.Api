"""Organization branding routes."""

import uuid
from typing import Optional

import json
from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select

from app.api.deps import CurrentUser, DB
from app.models.models import Organization
from app.schemas.branding import BrandingResponse, BrandingUpdate
from app.utils.envelopes import api_success

router = APIRouter(tags=["branding"])


 # Org-free branding


@router.get("/branding", response_model=dict)
async def get_branding(
    current_user: CurrentUser,
    db: DB,
):
    """Get organization branding settings."""
    # Use first org as global, create default if missing
    result = await db.execute(select(Organization).limit(1))
    org = result.scalar_one_or_none()
    if not org:
        org = Organization(name="Default", slug="default")
        db.add(org)
        await db.commit()
        await db.refresh(org)

    if not org:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Organization not found",
        )

    try:
        branding = json.loads(org.branding) if org.branding else {}
    except Exception:
        branding = {}

    response_data = BrandingResponse(
        logoUrl=branding.get("logo_url"),
        primaryColor=branding.get("primary_color", "#2563EB"),
        secondaryColor=branding.get("secondary_color"),
        companyName=branding.get("company_name") or org.name,
        tagline=branding.get("tagline"),
    )

    return api_success(response_data.model_dump())


@router.patch("/branding", response_model=dict)
async def update_branding(
    payload: BrandingUpdate,
    current_user: CurrentUser,
    db: DB,
):
    """Update organization branding (Pro/Enterprise only)."""
    result = await db.execute(select(Organization).limit(1))
    org = result.scalar_one_or_none()
    if not org:
        org = Organization(name="Default", slug="default")
        db.add(org)
        await db.commit()
        await db.refresh(org)

    # Update branding
    try:
        branding = json.loads(org.branding) if org.branding else {}
    except Exception:
        branding = {}

    if payload.logo_url is not None:
        branding["logo_url"] = payload.logo_url
    if payload.primary_color is not None:
        branding["primary_color"] = payload.primary_color
    if payload.secondary_color is not None:
        branding["secondary_color"] = payload.secondary_color
    if payload.company_name is not None:
        branding["company_name"] = payload.company_name
    if payload.tagline is not None:
        branding["tagline"] = payload.tagline

    org.branding = json.dumps(branding)

    await db.commit()
    await db.refresh(org)

    response_data = BrandingResponse(
        logoUrl=branding.get("logo_url"),
        primaryColor=branding.get("primary_color", "#2563EB"),
        secondaryColor=branding.get("secondary_color"),
        companyName=branding.get("company_name") or org.name,
        tagline=branding.get("tagline"),
    )

    return api_success(response_data.model_dump())
