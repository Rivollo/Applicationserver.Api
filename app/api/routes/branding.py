"""Organization branding routes."""

import uuid
from typing import Optional

import json
from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select

from app.api.deps import CurrentUser, DB
from app.models.models import Organization, OrgMember
from app.services.organization_service import OrganizationService
from app.schemas.branding import BrandingResponse, BrandingUpdate
from app.utils.envelopes import api_success

router = APIRouter(tags=["branding"])


async def _get_user_org_id(db: DB, user_id: uuid.UUID) -> Optional[uuid.UUID]:
    """Get or create the user's primary organization ID."""
    return await OrganizationService.get_or_create_org_id(db, user_id)


@router.get("/branding", response_model=dict)
async def get_branding(
    current_user: CurrentUser,
    db: DB,
):
    """Get organization branding settings."""
    org_id = await _get_user_org_id(db, current_user.id)

    if not org_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Organization not found")

    result = await db.execute(
        select(Organization).where(
            Organization.id == org_id,
            Organization.deleted_at.is_(None),
        )
    )
    org = result.scalar_one_or_none()

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
    org_id = await _get_user_org_id(db, current_user.id)

    if not org_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Organization not found")

    result = await db.execute(
        select(Organization).where(
            Organization.id == org_id,
            Organization.deleted_at.is_(None),
        )
    )
    org = result.scalar_one_or_none()

    if not org:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Organization not found",
        )

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
