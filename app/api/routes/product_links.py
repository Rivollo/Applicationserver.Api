"""Product link management routes.
"""

import uuid

from fastapi import APIRouter, Depends, HTTPException, status

from app.api.deps import CurrentUser, DB, get_current_user
from app.schemas.product_links import BulkProductLinkCreate, ProductLinkCreate, ProductLinkUpdate
from app.services.product_link_service import ProductLinkService
from app.utils.envelopes import api_success

router = APIRouter(tags=["product-links"], dependencies=[Depends(get_current_user)])


@router.get("/product-link-types", response_model=dict)
async def get_link_types(
    current_user: CurrentUser,
    db: DB,
):
    """Get all active product link types for dropdown."""
    link_types = await ProductLinkService.get_link_types(db)
    return api_success(link_types)



@router.post("/products/{product_id}/links", response_model=dict)
async def create_product_links(
    product_id: str,
    payload: BulkProductLinkCreate,
    current_user: CurrentUser,
    db: DB,
):
    """
    Create product links for a product.

    Does NOT delete or replace existing links - only adds new ones.
    If the links list is empty, returns success with an empty array.
    """
    try:
        prod_uuid = uuid.UUID(product_id)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid productId",
        )

    try:
        # Convert Pydantic models to dicts
        links_data = [link.model_dump() for link in payload.links]
        result = await ProductLinkService.create_product_links(
            db=db,
            product_id=prod_uuid,
            links_data=links_data,
            user_id=current_user.id,
        )
    except ValueError as e:
        if "Product not found" in str(e):
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=str(e),
            )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )

    await db.commit()
    return api_success(result)


@router.get("/products/{product_id}/links", response_model=dict)
async def get_product_links(
    product_id: str,
    current_user: CurrentUser,
    db: DB,
):
    """Get all active links for a product."""
    try:
        prod_uuid = uuid.UUID(product_id)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid productId",
        )

    try:
        links = await ProductLinkService.get_product_links(db, prod_uuid)
    except ValueError as e:
        if "Product not found" in str(e):
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=str(e),
            )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )

    return api_success(links)


@router.patch("/links/{link_id}", response_model=dict)
async def update_link(
    link_id: int,
    payload: ProductLinkUpdate,
    current_user: CurrentUser,
    db: DB,
):
    """Update a product link."""
    try:
        result = await ProductLinkService.update_link(
            db=db,
            link_id=link_id,
            name=payload.name,
            link_url=payload.link,
            description=payload.description,
            link_type=payload.link_type,
            user_id=current_user.id,
        )
    except ValueError as e:
        if "not found" in str(e).lower():
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=str(e),
            )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )

    await db.commit()
    return api_success(result)


@router.delete("/links/{link_id}", response_model=dict)
async def delete_link(
    link_id: int,
    current_user: CurrentUser,
    db: DB,
):
    """Soft delete a product link."""
    try:
        result = await ProductLinkService.delete_link(
            db=db,
            link_id=link_id,
            user_id=current_user.id,
        )
    except ValueError as e:
        if "not found" in str(e).lower():
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=str(e),
            )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )

    await db.commit()
    return api_success(result)
