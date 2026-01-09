"""Hotspot routes."""

import uuid
import logging
import traceback

from fastapi import APIRouter, Depends, HTTPException, status

from app.api.deps import CurrentUser, DB, get_current_user
from app.schemas.products import HotspotCreate
from app.schemas.hotspots import HotspotUpdate
from app.services.hotspot_service import hotspot_service
from app.utils.envelopes import api_success

logger = logging.getLogger(__name__)

router = APIRouter(
    tags=["hotspots"],
    dependencies=[Depends(get_current_user)],
)

# ---------- List all hotspot ----------

@router.get("/products/{product_id}/hotspots", response_model=dict)
async def list_product_hotspots(
    product_id: str,
    current_user: CurrentUser,
    db: DB,
):
    try:
        prod_uuid = uuid.UUID(product_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid productId format")

    hotspots = await hotspot_service.get_product_hotspots(
        db=db,
        product_id=prod_uuid,
        user_id=current_user.id,
    )
    return api_success([h.model_dump() for h in hotspots])


# ---------- Create hotspot ----------

@router.post(
    "/products/{product_id}/hotspots",
    response_model=dict,
    status_code=status.HTTP_201_CREATED,
)
async def create_hotspot(
    product_id: str,
    payload: HotspotCreate,
    current_user: CurrentUser,
    db: DB,
):
    try:
        prod_uuid = uuid.UUID(product_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid productId format")

    hotspot = await hotspot_service.create_hotspot(
        db=db,
        product_id=prod_uuid,
        user_id=current_user.id,
        payload=payload,
    )
    return api_success(hotspot.model_dump())


# ---------- Update hotspot ----------

@router.patch("/hotspots/{hotspot_id}", response_model=dict)
async def update_hotspot(
    hotspot_id: str,
    payload: HotspotUpdate,
    current_user: CurrentUser,
    db: DB,
):
    try:
        hotspot_uuid = uuid.UUID(hotspot_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid hotspotId format")

    hotspot = await hotspot_service.update_hotspot(
        db=db,
        hotspot_id=hotspot_uuid,
        user_id=current_user.id,
        payload=payload,
    )
    return api_success(hotspot.model_dump())


# ---------- Delete hotspot ----------

@router.delete(
    "/hotspots/{hotspot_id}",
    response_model=dict,
    status_code=status.HTTP_200_OK,
)
async def delete_hotspot(
    hotspot_id: str,
    current_user: CurrentUser,
    db: DB,
):
    try:
        hotspot_uuid = uuid.UUID(hotspot_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid hotspotId format")

    await hotspot_service.delete_hotspot(
        db=db,
        hotspot_id=hotspot_uuid,
        user_id=current_user.id,
    )
    return api_success({"message": "Hotspot deleted successfully"})
