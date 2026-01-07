"""Hotspot service for business logic operations."""

import json
import uuid
from typing import Optional

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.database.hotspot_repo import hotspot_repository
from app.models.models import Hotspot, HotspotActionType, HotspotType
from app.schemas.products import HotspotCreate, HotspotPosition, HotspotResponse
from app.schemas.hotspots import HotspotUpdate


class HotspotService:
    """Business logic for hotspot operations."""

    DIMENSION_HOTSPOT_TYPE = "dimension"

    # ---------- Public APIs ----------

    @staticmethod
    async def get_product_hotspots(
        db: AsyncSession,
        product_id: uuid.UUID,
        user_id: uuid.UUID,
    ) -> list[HotspotResponse]:
        await HotspotService._ensure_product_exists(db, product_id)
        hotspots = await hotspot_repository.get_hotspots_for_product(db, product_id)
        return [HotspotService._to_response(h) for h in hotspots]

    @staticmethod
    async def create_hotspot(
        db: AsyncSession,
        product_id: uuid.UUID,
        user_id: uuid.UUID,
        payload: HotspotCreate,
    ) -> HotspotResponse:
        await HotspotService._ensure_product_exists(db, product_id)
        await HotspotService._validate_create_payload(db, payload)

        order_index = await hotspot_repository.get_next_order_index(db, product_id)
        action_type = HotspotService._parse_action_type(payload.action_type)

        hotspot = Hotspot(
            product_id=product_id,
            label=payload.title,
            description=payload.description,
            pos_x=payload.position.x,
            pos_y=payload.position.y,
            pos_z=payload.position.z,
            text_font=payload.text_font,
            text_color=payload.text_color,
            bg_color=payload.bg_color,
            action_type=action_type,
            action_payload=json.dumps(payload.action_payload) if payload.action_payload else None,
            order_index=order_index,
            hotspot_type_id=payload.hotspot_type,
            created_by=user_id,
        )

        hotspot.set_position_to_geometry(
            payload.position.x,
            payload.position.y,
            payload.position.z,
        )

        await hotspot_repository.add_hotspot(db, hotspot)
        await db.commit()
        await db.refresh(hotspot)

        return HotspotService._to_response(hotspot)

    @staticmethod
    async def update_hotspot(
        db: AsyncSession,
        hotspot_id: uuid.UUID,
        user_id: uuid.UUID,
        payload: HotspotUpdate,
    ) -> HotspotResponse:
        hotspot = await HotspotService._get_hotspot_or_404(db, hotspot_id)

        if payload.hotspot_type is not None:
            if await HotspotService._is_dimension_hotspot_type(db, payload.hotspot_type):
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Dimension hotspots must be managed via dimensions API",
                )
            hotspot.hotspot_type_id = payload.hotspot_type

        if payload.title is not None:
            hotspot.label = payload.title

        if payload.description is not None:
            hotspot.description = payload.description

        if payload.position is not None:
            HotspotService._validate_position(payload.position)
            hotspot.pos_x = payload.position.x
            hotspot.pos_y = payload.position.y
            hotspot.pos_z = payload.position.z
            hotspot.set_position_to_geometry(
                payload.position.x,
                payload.position.y,
                payload.position.z,
            )

        if payload.text_font is not None:
            hotspot.text_font = payload.text_font

        if payload.text_color is not None:
            hotspot.text_color = payload.text_color

        if payload.bg_color is not None:
            hotspot.bg_color = payload.bg_color

        if payload.action_type is not None:
            hotspot.action_type = HotspotService._parse_action_type(payload.action_type)

        if payload.action_payload is not None:
            hotspot.action_payload = json.dumps(payload.action_payload)

        hotspot.updated_by = user_id

        await db.commit()
        await db.refresh(hotspot)

        return HotspotService._to_response(hotspot)

    @staticmethod
    async def delete_hotspot(
        db: AsyncSession,
        hotspot_id: uuid.UUID,
        user_id: uuid.UUID,
    ) -> None:
        hotspot = await HotspotService._get_hotspot_or_404(db, hotspot_id)
        await hotspot_repository.delete_hotspot(db, hotspot)
        await db.commit()

    # ---------- Helpers ----------

    @staticmethod
    def _parse_action_type(value: Optional[str]) -> HotspotActionType:
        try:
            return HotspotActionType(value)
        except Exception:
            return HotspotActionType.NONE

    @staticmethod
    async def _is_dimension_hotspot_type(
        db: AsyncSession,
        hotspot_type_id: int,
    ) -> bool:
        result = await db.execute(
            select(HotspotType.name).where(HotspotType.id == hotspot_type_id)
        )
        name = result.scalar_one_or_none()
        return name is not None and name.lower() == HotspotService.DIMENSION_HOTSPOT_TYPE

    @staticmethod
    def _validate_position(position: HotspotPosition) -> None:
        for coord, value in [("x", position.x), ("y", position.y), ("z", position.z)]:
            if not (-1.0 <= value <= 1.0):
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Position {coord} must be between -1 and 1",
                )

    @staticmethod
    async def _validate_create_payload(
        db: AsyncSession,
        payload: HotspotCreate,
    ) -> None:
        if await HotspotService._is_dimension_hotspot_type(db, payload.hotspot_type):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Dimension hotspots must be managed via dimensions API",
            )
        HotspotService._validate_position(payload.position)

    @staticmethod
    async def _ensure_product_exists(
        db: AsyncSession,
        product_id: uuid.UUID,
    ) -> None:
        if not await hotspot_repository.get_product_by_id(db, product_id):
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Product not found",
            )

    @staticmethod
    async def _get_hotspot_or_404(
        db: AsyncSession,
        hotspot_id: uuid.UUID,
    ) -> Hotspot:
        hotspot = await hotspot_repository.get_hotspot_by_id(db, hotspot_id)
        if not hotspot:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Hotspot not found",
            )
        return hotspot

    @staticmethod
    def _to_response(h: Hotspot) -> HotspotResponse:
        return HotspotResponse(
            id=str(h.id),
            title=h.label,
            description=h.description,
            position=HotspotPosition(x=h.pos_x, y=h.pos_y, z=h.pos_z),
            text_font=h.text_font,
            text_color=h.text_color,
            bg_color=h.bg_color,
            action_type=h.action_type.value if h.action_type else "none",
            action_payload=json.loads(h.action_payload) if h.action_payload else {},
            hotspot_type=h.hotspot_type_id,
            order_index=h.order_index,
            created_at=h.created_at,
        )


hotspot_service = HotspotService()
