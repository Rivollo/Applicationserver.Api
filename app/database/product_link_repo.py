"""
Repository layer for product link database operations.

"""

import uuid
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.models import ProductLink, ProductLinkType


class ProductLinkRepository:
    """Repository for product link database operations."""

    # ---------- Link Types ----------

    @staticmethod
    async def get_all_link_types(db: AsyncSession) -> list[ProductLinkType]:
        """Get all active link types."""
        result = await db.execute(
            select(ProductLinkType)
            .where(ProductLinkType.isactive.is_(True))
            .order_by(ProductLinkType.name)
        )
        return list(result.scalars().all())

    @staticmethod
    async def get_link_type_by_id(
        db: AsyncSession, link_type_id: int
    ) -> Optional[ProductLinkType]:
        """Get a link type by ID."""
        return await db.get(ProductLinkType, link_type_id)

    # ---------- Product Links ----------

    @staticmethod
    async def get_links_by_product(
        db: AsyncSession, product_id: uuid.UUID
    ) -> list[ProductLink]:
        """Get all active links for a product."""
        result = await db.execute(
            select(ProductLink)
            .where(
                ProductLink.productid == str(product_id),
                ProductLink.isactive.is_(True),
            )
            .order_by(ProductLink.created_date.desc())
        )
        return list(result.scalars().all())

    @staticmethod
    async def get_link_by_id(
        db: AsyncSession, link_id: int
    ) -> Optional[ProductLink]:
        """Get a link by ID."""
        return await db.get(ProductLink, link_id)

    @staticmethod
    async def create_link(
        db: AsyncSession,
        product_id: uuid.UUID,
        name: str,
        link: str,
        description: Optional[str],
        link_type: Optional[int],
        created_by: uuid.UUID,
    ) -> ProductLink:
        """Create a new product link."""
        product_link = ProductLink(
            productid=str(product_id),
            name=name,
            link=link,
            description=description,
            link_type=link_type,
            created_by=created_by,
            isactive=True,
        )
        db.add(product_link)
        await db.flush()  # ensures ID is generated
        return product_link

    @staticmethod
    async def update_link(
        db: AsyncSession,
        link: ProductLink,
        name: Optional[str],
        link_url: Optional[str],
        description: Optional[str],
        link_type: Optional[int],
        updated_by: uuid.UUID,
    ) -> ProductLink:
        """Update an existing product link."""
        if name is not None:
            link.name = name
        if link_url is not None:
            link.link = link_url
        if description is not None:
            link.description = description
        if link_type is not None:
            link.link_type = link_type

        link.updated_by = updated_by
        await db.flush()
        return link

    @staticmethod
    async def soft_delete_link(
        db: AsyncSession,
        link: ProductLink,
        deleted_by: uuid.UUID,
    ) -> None:
        """Soft delete a link (set isactive=false)."""
        link.isactive = False
        link.updated_by = deleted_by
        await db.flush()
