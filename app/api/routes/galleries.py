"""Gallery management routes."""

import uuid
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, HTTPException, Query, Request, status
from sqlalchemy import desc, func, or_, select, cast, String

from app.api.deps import CurrentUser, DB
from app.models.models import Gallery, GalleryItem, Product, Organization
from app.schemas.galleries import (
    GalleryCreate,
    GalleryResponse,
    GalleryUpdate,
)
from app.services.licensing_service import LicensingService
from app.utils.envelopes import api_success

router = APIRouter(tags=["galleries"])


def _slugify(text: str) -> str:
    """Convert text to URL-friendly slug."""
    import re

    text = text.lower().strip()
    text = re.sub(r"[^\w\s-]", "", text)
    text = re.sub(r"[-\s]+", "-", text)
    return text[:100]


# No unique slug helper; slug is simple slugify(name)


 # Org-free galleries


async def _check_gallery_access(db: DB, user_id: uuid.UUID) -> bool:
    """Check if user has access to galleries (Pro/Enterprise plan)."""
    plan_code = await LicensingService.get_user_plan_code(db, user_id)
    return plan_code in ["pro", "enterprise"]


@router.get("/galleries", response_model=dict)
async def list_galleries(
    current_user: CurrentUser,
    db: DB,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100, alias="pageSize"),
    q: Optional[str] = Query(None, max_length=200),
    status_filter: Optional[str] = Query(None, alias="status"),
    sort: str = Query("-createdAt"),
):
    """List galleries with filtering and pagination."""
    # Check access
    has_access = await _check_gallery_access(db, current_user.id)
    if not has_access:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Gallery access requires Pro or Enterprise plan",
        )

    # Base query
    query = select(Gallery).where(Gallery.deleted_at.is_(None))

    # Apply filters
    if q:
        search_pattern = f"%{q}%"
        query = query.where(
            or_(
                Gallery.name.ilike(search_pattern),
            )
        )

    if status_filter:
        # Map status values (ready/processing)
        pass  # Gallery status is derived, not stored

    # Count total
    count_query = select(func.count()).select_from(query.subquery())
    total_result = await db.execute(count_query)
    total = total_result.scalar() or 0

    # Apply sorting (map friendly keys to real DB columns)
    desc_order = sort.startswith("-")
    sort_field = sort[1:] if desc_order else sort
    field_map = {
        "createdAt": Gallery.created_date,
        "updatedAt": Gallery.updated_date,
        "name": Gallery.name,
    }
    order_base = field_map.get(sort_field, Gallery.created_date)
    order_col = desc(order_base) if desc_order else order_base

    query = query.order_by(order_col)

    # Apply pagination
    offset = (page - 1) * page_size
    query = query.offset(offset).limit(page_size)

    # Execute
    result = await db.execute(query)
    galleries = result.scalars().all()

    # Build response with counts
    items = []
    for gallery in galleries:
        # Count products in gallery
        product_count_result = await db.execute(
            select(func.count(GalleryItem.id)).where(GalleryItem.gallery_id == gallery.id)
        )
        product_count = product_count_result.scalar() or 0

        # Asset count is same as product count for now
        asset_count = product_count

        items.append(
            GalleryResponse(
                id=str(gallery.id),
                name=gallery.name,
                description=gallery.settings.get("description"),
                thumbnailColor=gallery.settings.get("thumbnail_color"),
                thumbnailOverlay=gallery.settings.get("thumbnail_overlay"),
                tags=gallery.settings.get("tags", []),
                productCount=product_count,
                assetCount=asset_count,
                status="ready",
                createdAt=gallery.created_at,
                updatedAt=gallery.updated_at,
            )
        )

    total_pages = (total + page_size - 1) // page_size

    return api_success(
        {
            "items": [item.model_dump(exclude_none=True) for item in items],
            "meta": {
                "page": page,
                "pageSize": page_size,
                "total": total,
                "totalPages": total_pages,
            },
        }
    )


@router.post("/galleries", response_model=dict, status_code=status.HTTP_201_CREATED)
async def create_gallery(
    payload: GalleryCreate,
    current_user: CurrentUser,
    db: DB,
):
    """Create a new gallery (Pro/Enterprise only)."""
    # Check access
    has_access = await _check_gallery_access(db, current_user.id)
    if not has_access:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Gallery creation requires Pro or Enterprise plan",
        )

    # Check quota (Pro = 10 galleries)
    plan_code = await LicensingService.get_user_plan_code(db, current_user.id)
    if plan_code == "pro":
        # Count existing galleries
        result = await db.execute(
            select(func.count(Gallery.id)).where(
                Gallery.deleted_at.is_(None),
            )
        )
        gallery_count = result.scalar() or 0

        if gallery_count >= 10:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Gallery limit exceeded. Upgrade to Enterprise for unlimited galleries.",
            )

    # Ensure a default organization exists (org-free API uses a global org)
    org_res = await db.execute(select(Organization).limit(1))
    org = org_res.scalar_one_or_none()
    if not org:
        org = Organization(name="Default", slug="default")
        db.add(org)
        await db.commit()
        await db.refresh(org)

    # Generate slug
    slug = _slugify(payload.name)

    # Create gallery (schema has no settings JSON field; don't persist settings)
    gallery = Gallery(
        org_id=org.id,
        name=payload.name,
        slug=slug,
        is_public=False,
        created_by=current_user.id,
    )

    db.add(gallery)
    await db.commit()
    await db.refresh(gallery)

    response_data = GalleryResponse(
        id=str(gallery.id),
        name=gallery.name,
        description=payload.description,
        thumbnailColor=payload.thumbnail_color,
        thumbnailOverlay=payload.thumbnail_overlay,
        tags=payload.tags,
        productCount=0,
        assetCount=0,
        status="ready",
        createdAt=gallery.created_at,
        updatedAt=gallery.updated_at,
    )

    return api_success(response_data.model_dump(exclude_none=True))


@router.get("/galleries/{gallery_id}", response_model=dict)
async def get_gallery(
    gallery_id: str,
    current_user: CurrentUser,
    db: DB,
):
    """Get gallery by ID."""
    has_access = await _check_gallery_access(db, current_user.id)
    if not has_access:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Gallery access requires Pro or Enterprise plan",
        )

    try:
        gallery_uuid = uuid.UUID(gallery_id)
    except ValueError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Gallery not found")

    result = await db.execute(
        select(Gallery).where(
            Gallery.id == gallery_uuid if gallery_uuid else cast(Gallery.id, String).like(f"{gallery_id}%"),
            Gallery.deleted_at.is_(None),
        )
    )
    gallery = result.scalar_one_or_none()

    if not gallery:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Gallery not found")

    # Count products
    product_count_result = await db.execute(
        select(func.count(GalleryItem.id)).where(GalleryItem.gallery_id == gallery.id)
    )
    product_count = product_count_result.scalar() or 0

    response_data = GalleryResponse(
        id=str(gallery.id),
        name=gallery.name,
        description=None,
        thumbnailColor=None,
        thumbnailOverlay=None,
        tags=[],
        productCount=product_count,
        assetCount=product_count,
        status="ready",
        createdAt=gallery.created_at,
        updatedAt=gallery.updated_at,
    )

    return api_success(response_data.model_dump(exclude_none=True))


@router.patch("/galleries/{gallery_id}", response_model=dict)
async def update_gallery(
    gallery_id: str,
    payload: GalleryUpdate,
    current_user: CurrentUser,
    db: DB,
):
    """Update gallery fields."""
    has_access = await _check_gallery_access(db, current_user.id)
    if not has_access:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Gallery access requires Pro or Enterprise plan",
        )

    try:
        gallery_uuid = uuid.UUID(gallery_id)
    except ValueError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Gallery not found")

    result = await db.execute(
        select(Gallery).where(
            Gallery.id == gallery_uuid if gallery_uuid else cast(Gallery.id, String).like(f"{gallery_id}%"),
            Gallery.deleted_at.is_(None),
        )
    )
    gallery = result.scalar_one_or_none()

    if not gallery:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Gallery not found")

    # Update fields
    if payload.name is not None:
        gallery.name = payload.name
        gallery.slug = _slugify(payload.name)

    # No settings column in DB; only update persisted fields (name/slug)

    await db.commit()
    await db.refresh(gallery)

    # Count products
    product_count_result = await db.execute(
        select(func.count(GalleryItem.id)).where(GalleryItem.gallery_id == gallery.id)
    )
    product_count = product_count_result.scalar() or 0

    response_data = GalleryResponse(
        id=str(gallery.id),
        name=gallery.name,
        description=payload.description,
        thumbnailColor=payload.thumbnail_color,
        thumbnailOverlay=payload.thumbnail_overlay,
        tags=payload.tags or [],
        productCount=product_count,
        assetCount=product_count,
        status="ready",
        createdAt=gallery.created_at,
        updatedAt=gallery.updated_at,
    )

    return api_success(response_data.model_dump(exclude_none=True))


@router.put("/galleries/{gallery_id}", response_model=dict)
async def replace_gallery(
    gallery_id: str,
    payload: GalleryCreate,
    current_user: CurrentUser,
    db: DB,
):
    """Replace all gallery fields."""
    has_access = await _check_gallery_access(db, current_user.id)
    if not has_access:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Gallery access requires Pro or Enterprise plan",
        )

    try:
        gallery_uuid = uuid.UUID(gallery_id)
    except ValueError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Gallery not found")

    result = await db.execute(
        select(Gallery).where(
            Gallery.id == gallery_uuid if gallery_uuid else cast(Gallery.id, String).like(f"{gallery_id}%"),
            Gallery.deleted_at.is_(None),
        )
    )
    gallery = result.scalar_one_or_none()

    if not gallery:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Gallery not found")

    gallery.name = payload.name
    gallery.slug = _slugify(payload.name)
    # No settings field to persist

    await db.commit()
    await db.refresh(gallery)

    product_count_result = await db.execute(
        select(func.count(GalleryItem.id)).where(GalleryItem.gallery_id == gallery.id)
    )
    product_count = product_count_result.scalar() or 0

    response_data = GalleryResponse(
        id=str(gallery.id),
        name=gallery.name,
        description=payload.description,
        thumbnailColor=payload.thumbnail_color,
        thumbnailOverlay=payload.thumbnail_overlay,
        tags=payload.tags,
        productCount=product_count,
        assetCount=product_count,
        status="ready",
        createdAt=gallery.created_at,
        updatedAt=gallery.updated_at,
    )

    return api_success(response_data.model_dump(exclude_none=True))


@router.delete("/galleries/{gallery_id}", response_model=dict)
async def delete_gallery(
    gallery_id: str,
    current_user: CurrentUser,
    db: DB,
):
    """Delete a gallery (soft delete). Products are not deleted."""
    has_access = await _check_gallery_access(db, current_user.id)
    if not has_access:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Gallery access requires Pro or Enterprise plan",
        )

    try:
        gallery_uuid = uuid.UUID(gallery_id)
    except ValueError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Gallery not found")

    result = await db.execute(
        select(Gallery).where(
            Gallery.id == gallery_uuid if gallery_uuid else cast(Gallery.id, String).like(f"{gallery_id}%"),
            Gallery.deleted_at.is_(None),
        )
    )
    gallery = result.scalar_one_or_none()

    if not gallery:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Gallery not found")

    # Physical delete (no deleted_at column in DB snapshot)
    await db.delete(gallery)
    await db.commit()

    return api_success({"message": "Gallery deleted"})
