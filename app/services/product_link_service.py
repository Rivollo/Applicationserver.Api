"""Service layer for product link business logic.
"""

import uuid
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.database.product_link_repo import ProductLinkRepository
from app.models.models import Product


class ProductLinkService:
    """Service for product link business logic."""

    @staticmethod
    async def get_link_types(db: AsyncSession) -> list[dict[str, Any]]:
        """Get all active link types."""
        link_types = await ProductLinkRepository.get_all_link_types(db)
        return [
            {
                "id": lt.id,
                "name": lt.name,
                "description": lt.description,
            }
            for lt in link_types
        ]

    @staticmethod
    async def create_product_link(
        db: AsyncSession,
        product_id: uuid.UUID,
        name: str,
        link: str,
        description: str | None,
        link_type: int | None,
        user_id: uuid.UUID,
    ) -> dict[str, Any]:
        """Create a product link."""
        # Validate product exists
        product = await db.get(Product, product_id)
        if not product:
            raise ValueError("Product not found")

        # Validate link_type if provided
        if link_type is not None:
            lt = await ProductLinkRepository.get_link_type_by_id(db, link_type)
            if not lt or not lt.isactive:
                raise ValueError("Invalid link type")

        # Create link
        product_link = await ProductLinkRepository.create_link(
            db=db,
            product_id=product_id,
            name=name,
            link=link,
            description=description,
            link_type=link_type,
            created_by=user_id,
        )

        # Get link type name if exists
        link_type_name = None
        if link_type:
            lt = await ProductLinkRepository.get_link_type_by_id(db, link_type)
            link_type_name = lt.name if lt else None

        return {
            "id": product_link.id,
            "name": product_link.name,
            "link": product_link.link,
            "description": product_link.description,
            "link_type_id": product_link.link_type,
            "link_type_name": link_type_name,
        }

    @staticmethod
    async def get_product_links(
        db: AsyncSession, product_id: uuid.UUID
    ) -> list[dict[str, Any]]:
        """Get all active links for a product.
        
        Handles old data where link or link_type may be NULL.
        """
        # Validate product exists
        product = await db.get(Product, product_id)
        if not product:
            raise ValueError("Product not found")

        links = await ProductLinkRepository.get_links_by_product(db, product_id)
        result = []

        for link in links:
            # CRITICAL: handle None rows (old data / joins)
            if not link:
                continue
            # Defensive NULL handling for old data
            link_type_name = None
            if link.link_type:
                lt = await ProductLinkRepository.get_link_type_by_id(db, link.link_type)
                link_type_name = lt.name if lt else None

            result.append({
                "id": link.id,
                "name": link.name or "",
                "link": link.link or "",
                "description": link.description,
                "link_type_id": link.link_type,
                "link_type_name": link_type_name,
            })

        return result

    @staticmethod
    async def update_link(
        db: AsyncSession,
        link_id: int,
        name: str | None,
        link_url: str | None,
        description: str | None,
        link_type: int | None,
        user_id: uuid.UUID,
    ) -> dict[str, Any]:
        """Update a product link."""
        # Get link
        link = await ProductLinkRepository.get_link_by_id(db, link_id)
        if not link or not link.isactive:
            raise ValueError("Link not found")

        # Validate link_type if provided
        if link_type is not None:
            lt = await ProductLinkRepository.get_link_type_by_id(db, link_type)
            if not lt or not lt.isactive:
                raise ValueError("Invalid link type")

        # Update link
        updated_link = await ProductLinkRepository.update_link(
            db=db,
            link=link,
            name=name,
            link_url=link_url,
            description=description,
            link_type=link_type,
            updated_by=user_id,
        )

        # Get link type name
        link_type_name = None
        if updated_link.link_type:
            lt = await ProductLinkRepository.get_link_type_by_id(db, updated_link.link_type)
            link_type_name = lt.name if lt else None

        return {
            "id": updated_link.id,
            "name": updated_link.name,
            "link": updated_link.link,
            "description": updated_link.description,
            "link_type_id": updated_link.link_type,
            "link_type_name": link_type_name,
        }

    @staticmethod
    async def delete_link(
        db: AsyncSession, link_id: int, user_id: uuid.UUID
    ) -> dict[str, Any]:
        """Soft delete a product link."""
        link = await ProductLinkRepository.get_link_by_id(db, link_id)
        if not link or not link.isactive:
            raise ValueError("Link not found")

        await ProductLinkRepository.soft_delete_link(db, link, user_id)

        return {
            "id": link_id,
            "message": "Link deleted successfully",
        }

    @staticmethod
    async def create_product_links(
        db: AsyncSession,
        product_id: uuid.UUID,
        links_data: list[dict[str, Any]],
        user_id: uuid.UUID,
    ) -> list[dict[str, Any]]:
        """
        Create product links for a product.

        Does NOT delete or replace existing links - only adds new ones.
        """
        # Validate product exists once
        product = await db.get(Product, product_id)
        if not product:
            raise ValueError("Product not found")

        # Return empty array if no links provided
        if not links_data:
            return []

        result: list[dict[str, Any]] = []

        for link_data in links_data:
            name = link_data.get("name")
            link_url = link_data.get("link")
            description = link_data.get("description")
            link_type = link_data.get("link_type")

            # Validate link_type if provided
            if link_type is not None:
                lt = await ProductLinkRepository.get_link_type_by_id(db, link_type)
                if not lt or not lt.isactive:
                    raise ValueError(f"Invalid link type: {link_type}")

            # Create link
            product_link = await ProductLinkRepository.create_link(
                db=db,
                product_id=product_id,
                name=name,
                link=link_url,
                description=description,
                link_type=link_type,
                created_by=user_id,
            )

            # Get link type name if exists
            link_type_name = None
            if link_type:
                lt = await ProductLinkRepository.get_link_type_by_id(db, link_type)
                link_type_name = lt.name if lt else None

            result.append({
                "id": product_link.id,
                "name": product_link.name or "",
                "link": product_link.link or "",
                "description": product_link.description,
                "link_type_id": product_link.link_type,
                "link_type_name": link_type_name,
            })

        return result
