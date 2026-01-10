"""Dimension management routes.
"""

import uuid

from fastapi import APIRouter, Depends, HTTPException, Request, status

from app.api.deps import CurrentUser, DB, get_current_user
from app.schemas.dimensions import DimensionItem
from app.services.activity_service import ActivityService
from app.services.dimension_service import DimensionService
from app.utils.envelopes import api_success

router = APIRouter(tags=["dimensions"], dependencies=[Depends(get_current_user)])


@router.post("/products/{product_id}/dimensions", response_model=dict)
async def save_product_dimensions(
    product_id: str,
    payload: list[DimensionItem],
    current_user: CurrentUser,
    request: Request,
    db: DB,
):
    """
    Save product dimensions using a pure list-based input.

    This endpoint replaces all existing dimensions for the product
    with the provided dimension data.

    Each dimension must have exactly 2 hotspots: one 'start' and one 'end'.
    """
    # Validate product ID format
    try:
        prod_uuid = uuid.UUID(product_id)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid productId",
        )

    # Delegate to service layer
    try:
        result = await DimensionService.save_product_dimensions(
            db=db,
            product_id=prod_uuid,
            dimensions=payload,
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

    # Log activity
    await ActivityService.log_product_action(
        db=db,
        action="product.dimensions_updated",
        user_id=current_user.id,
        product_id=prod_uuid,
        request=request,
    )

    await db.commit()

    return api_success(result)


@router.get("/products/{product_id}/dimensions", response_model=dict)
async def get_product_dimensions(
    product_id: str,
    current_user: CurrentUser,
    db: DB,
):
    """
    Get all dimensions for a product.

    Returns dimensions in list-based format with hotspots including
    type='start' or type='end' indicators.
    """
    # Validate product ID format
    try:
        prod_uuid = uuid.UUID(product_id)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid productId",
        )

    # Delegate to service layer
    try:
        dimensions = await DimensionService.get_dimensions_list(
            db=db,
            product_id=prod_uuid,
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

    return api_success(dimensions)


@router.put("/products/{product_id}/dimensions", response_model=dict)
async def replace_product_dimensions(
    product_id: str,
    payload: list[DimensionItem],
    current_user: CurrentUser,
    request: Request,
    db: DB,
):
    """
    Replace all dimensions for a product (same behavior as POST).

    This endpoint replaces all existing dimensions for the product
    with the provided dimension data.

    Each dimension must have exactly 2 hotspots: one 'start' and one 'end'.
    """
    # Validate product ID format
    try:
        prod_uuid = uuid.UUID(product_id)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid productId",
        )

    # Delegate to service layer (reuse same logic as POST)
    try:
        result = await DimensionService.save_product_dimensions(
            db=db,
            product_id=prod_uuid,
            dimensions=payload,
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

    # Log activity
    await ActivityService.log_product_action(
        db=db,
        action="product.dimensions_updated",
        user_id=current_user.id,
        product_id=prod_uuid,
        request=request,
    )

    await db.commit()

    return api_success(result)


@router.delete("/products/{product_id}/dimensions", response_model=dict)
async def delete_product_dimensions(
    product_id: str,
    current_user: CurrentUser,
    request: Request,
    db: DB,
):
    """
    Delete all dimensions for a product.

    This deletes:
    - Product dimensions
    - Dimension groups
    - Dimension-created hotspots (identified by 'Dimension marker:' description)

    Normal (non-dimension) hotspots are preserved.
    """
    # Validate product ID format
    try:
        prod_uuid = uuid.UUID(product_id)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid productId",
        )

    # Delegate to service layer
    try:
        result = await DimensionService.delete_dimensions(
            db=db,
            product_id=prod_uuid,
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

    # Log activity
    await ActivityService.log_product_action(
        db=db,
        action="product.dimensions_deleted",
        user_id=current_user.id,
        product_id=prod_uuid,
        request=request,
    )

    await db.commit()

    return api_success(result)
