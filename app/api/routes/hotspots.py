"""Hotspot management routes."""

import uuid
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.api.deps import CurrentUser, DB, get_current_user
from app.schemas.hotspots import HotspotUpsertRequest
from app.schemas.products import HotspotCreate, HotspotResponse
from app.services.hotspot_service import hotspot_service
from app.utils.envelopes import api_success

router = APIRouter(tags=["hotspots"], dependencies=[Depends(get_current_user)])


@router.get("/products/{product_id}/hotspots", response_model=dict)
async def list_product_hotspots(
    product_id: str,
    current_user: CurrentUser,
    db: DB,
):
    """
    List all hotspots for a product.

    Returns hotspots ordered by order_index in ascending order.
    """
    # Parse product ID
    try:
        prod_uuid = uuid.UUID(product_id)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid productId format. Expected UUID string.",
        )

    try:
        # Delegate to service
        hotspots = await hotspot_service.get_product_hotspots(
            db=db, product_id=prod_uuid, user_id=current_user.id
        )

        return api_success([h.model_dump() for h in hotspots])
    except HTTPException:
        raise
    except Exception as e:
        import logging
        import traceback
        logger = logging.getLogger(__name__)
        logger.error(f"Error listing hotspots: {str(e)}\n{traceback.format_exc()}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to list hotspots: {str(e)}",
        )


@router.post(
    "/hotspots",
    response_model=dict,
    status_code=status.HTTP_201_CREATED,
)
async def upsert_hotspot(
    payload: HotspotUpsertRequest,
    current_user: CurrentUser,
    db: DB,
):
    """
    Create or update a hotspot using request body IDs.

    **Create mode** (hotspot_id not provided in body):
    - Creates a new hotspot for the product.
    - Order index is auto-generated based on existing hotspots.

    **Update mode** (hotspot_id provided in body):
    - Updates the existing hotspot with the given ID.
    - Hotspot must exist and belong to the specified product.

    Position values (x, y, z) must be between -1 and 1.
    Dimension hotspots cannot be created or updated via this endpoint.
    """
    try:
        if payload.hotspot_id is not None:
            # Update existing hotspot
            hotspot = await hotspot_service.update_hotspot(
                db=db,
                product_id=payload.product_id,
                hotspot_id=payload.hotspot_id,
                user_id=current_user.id,
                payload=payload,
            )
        else:
            # Create new hotspot
            hotspot = await hotspot_service.create_hotspot(
                db=db,
                product_id=payload.product_id,
                user_id=current_user.id,
                payload=payload,
            )

        return api_success(hotspot.model_dump())
    except HTTPException:
        raise
    except Exception as e:
        import logging
        import traceback
        logger = logging.getLogger(__name__)
        action = "updating" if payload.hotspot_id else "creating"
        logger.error(f"Error {action} hotspot: {str(e)}\n{traceback.format_exc()}")
        try:
            await db.rollback()
        except Exception:
            pass
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to {'update' if payload.hotspot_id else 'create'} hotspot: {str(e)}",
        )


@router.delete(
    "/products/{product_id}/hotspots/{hotspot_id}",
    response_model=dict,
    status_code=status.HTTP_200_OK,
)
async def delete_product_hotspot(
    product_id: str,
    hotspot_id: str,
    current_user: CurrentUser,
    db: DB,
):
    """
    Delete a hotspot from a product.

    The hotspot must exist and belong to the specified product.
    """
    # Parse product ID
    try:
        prod_uuid = uuid.UUID(product_id)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid productId format. Expected UUID string.",
        )

    # Parse hotspot ID
    try:
        hotspot_uuid = uuid.UUID(hotspot_id)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid hotspotId format. Expected UUID string.",
        )

    try:
        # Delegate to service
        await hotspot_service.delete_hotspot(
            db=db,
            product_id=prod_uuid,
            hotspot_id=hotspot_uuid,
            user_id=current_user.id,
        )

        return api_success({"message": "Hotspot deleted successfully"})
    except HTTPException:
        raise
    except Exception as e:
        import logging
        import traceback
        logger = logging.getLogger(__name__)
        logger.error(f"Error deleting hotspot: {str(e)}\n{traceback.format_exc()}")
        try:
            await db.rollback()
        except Exception:
            pass
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to delete hotspot: {str(e)}",
        )
