"""Hotspot service for business logic operations."""

import json
import uuid
from typing import Optional

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.hotspot_repo import hotspot_repository
from app.models.models import Hotspot, HotspotActionType, HotspotType
from app.schemas.products import HotspotCreate, HotspotPosition, HotspotResponse


class HotspotService:
    """Service for hotspot business logic operations."""

    # Dimension hotspot type name to block
    DIMENSION_HOTSPOT_TYPE = "dimension"

    @staticmethod
    async def get_product_hotspots(
        db: AsyncSession, product_id: uuid.UUID, user_id: uuid.UUID
    ) -> list[HotspotResponse]:
        """
        Get all hotspots for a product.

        Args:
            db: Database session
            product_id: UUID of the product
            user_id: UUID of the requesting user

        Returns:
            List of HotspotResponse objects

        Raises:
            HTTPException: If product not found
        """
        # Validate product exists
        product = await hotspot_repository.get_product_by_id(db, product_id)
        if not product:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Product not found",
            )

        # Fetch hotspots via repository
        hotspots = await hotspot_repository.get_hotspots_for_product(db, product_id)

        # Convert to response format
        return [
            HotspotResponse(
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
            for h in hotspots
        ]

    @staticmethod
    async def _is_dimension_hotspot_type(
        db: AsyncSession, hotspot_type_id: Optional[int]
    ) -> bool:
        """
        Check if the given hotspot_type_id corresponds to a dimension hotspot type.

        Args:
            db: Database session
            hotspot_type_id: ID of the hotspot type

        Returns:
            True if this is a dimension hotspot type, False otherwise
        """
        if hotspot_type_id is None:
            return False

        from sqlalchemy import select

        result = await db.execute(
            select(HotspotType.name).where(HotspotType.id == hotspot_type_id)
        )
        name = result.scalar_one_or_none()
        return name is not None and name.lower() == HotspotService.DIMENSION_HOTSPOT_TYPE

    @staticmethod
    def _validate_position(position: HotspotPosition) -> None:
        """
        Validate hotspot position values are between -1 and 1.

        Args:
            position: HotspotPosition object

        Raises:
            HTTPException: If any position value is out of range
        """
        for coord_name, value in [("x", position.x), ("y", position.y), ("z", position.z)]:
            if not (-1.0 <= value <= 1.0):
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Position {coord_name} must be between -1 and 1. Got: {value}",
                )

    @staticmethod
    async def create_hotspot(
        db: AsyncSession,
        product_id: uuid.UUID,
        user_id: uuid.UUID,
        payload: HotspotCreate,
    ) -> HotspotResponse:
        """
        Create a new hotspot for a product.

        Args:
            db: Database session
            product_id: UUID of the product
            user_id: UUID of the user creating the hotspot
            payload: HotspotCreate object with hotspot data

        Returns:
            HotspotResponse object with created hotspot data

        Raises:
            HTTPException: If product not found, dimension hotspot type, or invalid position
        """
        # Validate product exists
        product = await hotspot_repository.get_product_by_id(db, product_id)
        if not product:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Product not found",
            )

        # Block creation of dimension hotspots
        if await HotspotService._is_dimension_hotspot_type(db, payload.hotspot_type):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Creation of dimension hotspots is not allowed via this API. Use the dimensions endpoint instead.",
            )

        # Validate position values
        HotspotService._validate_position(payload.position)

        # Auto-generate order_index
        order_index = await hotspot_repository.get_next_order_index(db, product_id)

        # Parse action type
        try:
            action_type = HotspotActionType(payload.action_type)
        except ValueError:
            action_type = HotspotActionType.NONE

        # Create hotspot entity
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

        # Set PostGIS geometry
        hotspot.set_position_to_geometry(
            payload.position.x, payload.position.y, payload.position.z
        )

        # Save via repository (includes commit)
        created_hotspot = await hotspot_repository.create_hotspot(db, hotspot)

        return HotspotResponse(
            id=str(created_hotspot.id),
            title=created_hotspot.label,
            description=created_hotspot.description,
            position=HotspotPosition(
                x=created_hotspot.pos_x,
                y=created_hotspot.pos_y,
                z=created_hotspot.pos_z,
            ),
            text_font=created_hotspot.text_font,
            text_color=created_hotspot.text_color,
            bg_color=created_hotspot.bg_color,
            action_type=created_hotspot.action_type.value if created_hotspot.action_type else "none",
            action_payload=json.loads(created_hotspot.action_payload) if created_hotspot.action_payload else {},
            hotspot_type=created_hotspot.hotspot_type_id,
            order_index=created_hotspot.order_index,
            created_at=created_hotspot.created_at,
        )

    @staticmethod
    async def update_hotspot(
        db: AsyncSession,
        product_id: uuid.UUID,
        hotspot_id: uuid.UUID,
        user_id: uuid.UUID,
        payload: HotspotCreate,
    ) -> HotspotResponse:
        """
        Update an existing hotspot.

        Args:
            db: Database session
            product_id: UUID of the product (for validation)
            hotspot_id: UUID of the hotspot to update
            user_id: UUID of the user performing the update
            payload: HotspotCreate object with updated hotspot data

        Returns:
            HotspotResponse object with updated hotspot data

        Raises:
            HTTPException: If hotspot not found, doesn't belong to product,
                          dimension hotspot type, or invalid position
        """
        # Validate hotspot exists
        hotspot = await hotspot_repository.get_hotspot_by_id(db, hotspot_id)
        if not hotspot:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Hotspot not found",
            )

        # Validate hotspot belongs to this product
        if hotspot.product_id != product_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Hotspot does not belong to this product",
            )

        # Block updating to dimension hotspot type
        if await HotspotService._is_dimension_hotspot_type(db, payload.hotspot_type):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cannot set hotspot type to dimension via this API. Use the dimensions endpoint instead.",
            )

        # Validate position values
        HotspotService._validate_position(payload.position)

        # Parse action type
        try:
            action_type = HotspotActionType(payload.action_type)
        except ValueError:
            action_type = HotspotActionType.NONE

        # Update hotspot fields
        hotspot.label = payload.title
        hotspot.description = payload.description
        hotspot.pos_x = payload.position.x
        hotspot.pos_y = payload.position.y
        hotspot.pos_z = payload.position.z
        hotspot.text_font = payload.text_font
        hotspot.text_color = payload.text_color
        hotspot.bg_color = payload.bg_color
        hotspot.action_type = action_type
        hotspot.action_payload = json.dumps(payload.action_payload) if payload.action_payload else None
        hotspot.hotspot_type_id = payload.hotspot_type
        hotspot.updated_by = user_id

        # Update PostGIS geometry
        hotspot.set_position_to_geometry(
            payload.position.x, payload.position.y, payload.position.z
        )

        # Save via repository (includes commit)
        updated_hotspot = await hotspot_repository.update_hotspot(db, hotspot)

        return HotspotResponse(
            id=str(updated_hotspot.id),
            title=updated_hotspot.label,
            description=updated_hotspot.description,
            position=HotspotPosition(
                x=updated_hotspot.pos_x,
                y=updated_hotspot.pos_y,
                z=updated_hotspot.pos_z,
            ),
            text_font=updated_hotspot.text_font,
            text_color=updated_hotspot.text_color,
            bg_color=updated_hotspot.bg_color,
            action_type=updated_hotspot.action_type.value if updated_hotspot.action_type else "none",
            action_payload=json.loads(updated_hotspot.action_payload) if updated_hotspot.action_payload else {},
            hotspot_type=updated_hotspot.hotspot_type_id,
            order_index=updated_hotspot.order_index,
            created_at=updated_hotspot.created_at,
        )

    @staticmethod
    async def delete_hotspot(
        db: AsyncSession,
        product_id: uuid.UUID,
        hotspot_id: uuid.UUID,
        user_id: uuid.UUID,
    ) -> None:
        """
        Delete a hotspot from a product.

        Args:
            db: Database session
            product_id: UUID of the product
            hotspot_id: UUID of the hotspot to delete
            user_id: UUID of the user performing the deletion

        Raises:
            HTTPException: If product or hotspot not found, or hotspot doesn't belong to product
        """
        # Validate product exists
        product = await hotspot_repository.get_product_by_id(db, product_id)
        if not product:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Product not found",
            )

        # Validate hotspot exists
        hotspot = await hotspot_repository.get_hotspot_by_id(db, hotspot_id)
        if not hotspot:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Hotspot not found",
            )

        # Validate hotspot belongs to this product
        if hotspot.product_id != product_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Hotspot does not belong to this product",
            )

        # Delete via repository (includes commit)
        await hotspot_repository.delete_hotspot(db, hotspot)


hotspot_service = HotspotService()
