"""Hotspot repository for database operations."""

import uuid
from typing import Optional

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.models import Hotspot, Product


class HotspotRepository:
    """Repository for hotspot database operations."""

    @staticmethod
    async def get_hotspots_for_product(
        db: AsyncSession, product_id: uuid.UUID
    ) -> list[Hotspot]:
        """
        Fetch all hotspots for a product ordered by order_index.

        Args:
            db: Database session
            product_id: UUID of the product

        Returns:
            List of Hotspot objects ordered by order_index
        """
        result = await db.execute(
            select(Hotspot)
            .where(Hotspot.product_id == product_id)
            .order_by(Hotspot.order_index.asc())
        )
        return list(result.scalars().all())

    @staticmethod
    async def get_next_order_index(db: AsyncSession, product_id: uuid.UUID) -> int:
        """
        Get the next available order_index for a product.

        Args:
            db: Database session
            product_id: UUID of the product

        Returns:
            Next available order_index (max + 1, or 0 if no hotspots exist)
        """
        result = await db.execute(
            select(func.max(Hotspot.order_index)).where(
                Hotspot.product_id == product_id
            )
        )
        max_order = result.scalar()
        # Use explicit None check since 0 is a valid max_order value
        return 0 if max_order is None else max_order + 1

    @staticmethod
    async def create_hotspot(db: AsyncSession, hotspot: Hotspot) -> Hotspot:
        """
        Insert a new hotspot record and commit the transaction.

        Args:
            db: Database session
            hotspot: Hotspot object to insert

        Returns:
            The created Hotspot object with generated ID
        """
        db.add(hotspot)
        await db.commit()
        await db.refresh(hotspot)
        return hotspot

    @staticmethod
    async def update_hotspot(db: AsyncSession, hotspot: Hotspot) -> Hotspot:
        """
        Update an existing hotspot record and commit the transaction.

        Args:
            db: Database session
            hotspot: Hotspot object with updated fields

        Returns:
            The updated Hotspot object
        """
        await db.commit()
        await db.refresh(hotspot)
        return hotspot

    @staticmethod
    async def get_product_by_id(
        db: AsyncSession, product_id: uuid.UUID
    ) -> Optional[Product]:
        """
        Fetch a product by ID.

        Args:
            db: Database session
            product_id: UUID of the product

        Returns:
            Product object or None if not found
        """
        return await db.get(Product, product_id)

    @staticmethod
    async def get_hotspot_by_id(
        db: AsyncSession, hotspot_id: uuid.UUID
    ) -> Optional[Hotspot]:
        """
        Fetch a hotspot by ID.

        Args:
            db: Database session
            hotspot_id: UUID of the hotspot

        Returns:
            Hotspot object or None if not found
        """
        return await db.get(Hotspot, hotspot_id)

    @staticmethod
    async def delete_hotspot(db: AsyncSession, hotspot: Hotspot) -> None:
        """
        Delete a hotspot record and commit the transaction.

        Args:
            db: Database session
            hotspot: Hotspot object to delete
        """
        await db.delete(hotspot)
        await db.commit()


hotspot_repository = HotspotRepository()
