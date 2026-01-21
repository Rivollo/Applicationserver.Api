"""Repository layer for product database operations."""

import uuid
from typing import Optional

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.models import Product, ProductAsset, ProductAssetMapping, AssetStatic


class ProductRepository:
    """Repository for product database operations."""

    @staticmethod
    async def get_products_by_user_id(
        db: AsyncSession, user_id: uuid.UUID
    ) -> list[Product]:
        """Get all products for a user, ordered by most recent first."""
        result = await db.execute(
            select(Product)
            .where(
                Product.created_by == user_id,
                Product.deleted_at.is_(None),
            )
            .order_by(func.coalesce(Product.updated_date, Product.created_date).desc())
        )
        return list(result.scalars().all())

    @staticmethod
    async def get_primary_asset_for_product(
        db: AsyncSession, product_id: uuid.UUID
    ) -> Optional[tuple[str, str, int]]:
        """Get primary asset (asset_id = 1) for a product.
        
        Returns: Tuple of (image_url, asset_type_name, asset_type_id) or None
        """
        result = await db.execute(
            select(
                ProductAsset.image,
                AssetStatic.name.label("asset_name"),
                ProductAsset.asset_id,
            )
            .join(ProductAssetMapping, ProductAsset.id == ProductAssetMapping.product_asset_id)
            .join(AssetStatic, ProductAsset.asset_id == AssetStatic.id)
            .where(
                ProductAssetMapping.productid == str(product_id),
                ProductAsset.asset_id == 1,
                ProductAssetMapping.isactive.is_(True),
            )
            .order_by(ProductAssetMapping.created_date.desc())
            .limit(1)
        )
        row = result.first()
        if row:
            return (row.image, row.asset_name, row.asset_id)
        return None
