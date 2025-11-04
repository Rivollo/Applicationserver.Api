"""Global search routes."""

import uuid
from typing import Optional

from fastapi import APIRouter, Query
from sqlalchemy import or_, select

from app.api.deps import CurrentUser, DB
from app.models.models import Gallery, Product
from app.utils.envelopes import api_success

router = APIRouter(tags=["search"])


 # Org-free search


@router.get("/search", response_model=dict)
async def global_search(
    current_user: CurrentUser,
    db: DB,
    q: str = Query(..., min_length=1, max_length=200),
    type_filter: Optional[str] = Query(None, alias="type"),
    limit: int = Query(10, ge=1, le=50),
):
    """Global search across products and galleries."""
    results = []

    search_pattern = f"%{q}%"

    # Search products (unless type filter excludes them)
    if not type_filter or type_filter == "products":
        product_query = (
            select(Product)
            .where(
                Product.deleted_at.is_(None),
                Product.name.ilike(search_pattern),
            )
            .limit(limit)
        )

        product_result = await db.execute(product_query)
        products = product_result.scalars().all()

        for product in products:
            results.append(
                {
                    "type": "product",
                    "id": str(product.id),
                    "name": product.name,
                    "description": None,
                    "status": product.status.value,
                    "url": f"/products/{str(product.id)}",
                }
            )

    # Search galleries (unless type filter excludes them)
    if not type_filter or type_filter == "galleries":
        gallery_query = (
            select(Gallery)
            .where(
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
                    "id": str(gallery.id),
                    "name": gallery.name,
                    "description": None,
                    "status": "ready",
                    "url": f"/galleries/{str(gallery.id)}",
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
