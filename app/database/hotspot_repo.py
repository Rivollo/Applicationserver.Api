"""Hotspot repository for database operations."""

import uuid
from typing import Optional

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.models import Hotspot, Product


class HotspotRepository:
    """Database access layer for hotspot-related operations."""

    # ---------- Read ----------

    @staticmethod
    async def get_product_by_id(
        db: AsyncSession,
        product_id: uuid.UUID,
    ) -> Optional[Product]:
        return await db.get(Product, product_id)

    @staticmethod
    async def get_hotspot_by_id(
        db: AsyncSession,
        hotspot_id: uuid.UUID,
    ) -> Optional[Hotspot]:
        return await db.get(Hotspot, hotspot_id)

    @staticmethod
    async def get_hotspots_for_product(
        db: AsyncSession,
        product_id: uuid.UUID,
    ) -> list[Hotspot]:
        result = await db.execute(
            select(Hotspot)
            .where(Hotspot.product_id == product_id)
            .order_by(Hotspot.order_index.asc())
        )
        return list(result.scalars().all())

    @staticmethod
    async def get_next_order_index(
        db: AsyncSession,
        product_id: uuid.UUID,
    ) -> int:
        result = await db.execute(
            select(func.max(Hotspot.order_index))
            .where(Hotspot.product_id == product_id)
        )
        max_order = result.scalar()
        return 0 if max_order is None else max_order + 1

    # ---------- Write ----------

    @staticmethod
    async def add_hotspot(
        db: AsyncSession,
        hotspot: Hotspot,
    ) -> None:
        db.add(hotspot)

    @staticmethod
    async def delete_hotspot(
        db: AsyncSession,
        hotspot: Hotspot,
    ) -> None:
        await db.delete(hotspot)


hotspot_repository = HotspotRepository()
