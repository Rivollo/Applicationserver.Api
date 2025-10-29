"""Global search routes."""

import uuid
from typing import Optional

from fastapi import APIRouter, Query
from sqlalchemy import or_, select

from app.api.deps import CurrentUser, DB
from app.models.models import Gallery, OrgMember, Product
from app.utils.envelopes import api_success

router = APIRouter(tags=["search"])


async def _get_user_org_id(db: DB, user_id: uuid.UUID) -> Optional[uuid.UUID]:
    """Get the user's primary organization ID."""
    result = await db.execute(
        select(OrgMember.org_id).where(OrgMember.user_id == user_id).limit(1)
    )
    return result.scalar_one_or_none()


@router.get("/search", response_model=dict)
async def global_search(
    current_user: CurrentUser,
    db: DB,
    q: str = Query(..., min_length=1, max_length=200),
    type_filter: Optional[str] = Query(None, alias="type"),
    limit: int = Query(10, ge=1, le=50),
):
    """Global search across products and galleries."""
    org_id = await _get_user_org_id(db, current_user.id)

    results = []

    if not org_id:
        return api_success({"results": [], "total": 0})

    search_pattern = f"%{q}%"

    # Search products (unless type filter excludes them)
    if not type_filter or type_filter == "products":
        product_query = (
            select(Product)
            .where(
                Product.org_id == org_id,
                Product.deleted_at.is_(None),
                or_(
                    Product.name.ilike(search_pattern),
                    Product.product_metadata["description"].astext.ilike(search_pattern),
                    Product.product_metadata["brand"].astext.ilike(search_pattern),
                ),
            )
            .limit(limit)
        )

        product_result = await db.execute(product_query)
        products = product_result.scalars().all()

        for product in products:
            results.append(
                {
                    "type": "product",
                    "id": f"prod-{str(product.id)[:8]}",
                    "name": product.name,
                    "description": product.product_metadata.get("description"),
                    "status": product.status.value,
                    "url": f"/products/{str(product.id)[:8]}",
                }
            )

    # Search galleries (unless type filter excludes them)
    if not type_filter or type_filter == "galleries":
        gallery_query = (
            select(Gallery)
            .where(
                Gallery.org_id == org_id,
                Gallery.deleted_at.is_(None),
                Gallery.name.ilike(search_pattern),
            )
            .limit(limit)
        )

        gallery_result = await db.execute(gallery_query)
        galleries = gallery_result.scalars().all()

        for gallery in galleries:
            results.append(
                {
                    "type": "gallery",
                    "id": f"gallery-{str(gallery.id)[:8]}",
                    "name": gallery.name,
                    "description": gallery.settings.get("description"),
                    "status": "ready",
                    "url": f"/galleries/{str(gallery.id)[:8]}",
                }
            )

    # Limit total results
    results = results[:limit]

    return api_success(
        {
            "results": results,
            "total": len(results),
            "query": q,
        }
    )
