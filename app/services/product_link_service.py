"""Product link service layer."""

import logging
import uuid
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.database.product_link_repo import ProductLinkRepository

logger = logging.getLogger(__name__)


class ProductLinkService:
    """Service for product link operations."""

    @staticmethod
    async def get_link_types(db: AsyncSession) -> list[dict[str, Any]]:
        """Get all active product link types."""
        try:
            logger.info("Processing get_link_types in service")
            link_types = await ProductLinkRepository.get_all_link_types(db)
            logger.info("get_link_types in service processed successfully")
            return link_types
        except Exception as e:
            logger.error("An error occurred in get_link_types service", exc_info=True)
            raise e

    @staticmethod
    async def get_product_links(
        db: AsyncSession, product_id: uuid.UUID
    ) -> list[dict[str, Any]]:
        """Get all active links for a product."""
        try:
            logger.info(f"Processing get_product_links in service for product {product_id}")
            links = await ProductLinkRepository.get_links_by_product(db, product_id)
            
            # Format response
            result = [
                {
                    "id": link["id"],
                    "name": link["name"] or "",
                    "link": link["link"] or "",
                    "description": link["description"],
                    "link_type_id": link["link_type"],
                    "link_type_name": link["link_type_name"],
                }
                for link in links
            ]
            
            logger.info("get_product_links in service processed successfully")
            return result
        except Exception as e:
            logger.error("An error occurred in get_product_links service", exc_info=True)
            raise e

    @staticmethod
    async def create_product_links(
        db: AsyncSession,
        product_id: uuid.UUID,
        links_data: list[dict[str, Any]],
        user_id: uuid.UUID,
    ) -> list[dict[str, Any]]:
        """Create product links for a product."""
        try:
            logger.info(f"Processing create_product_links in service for product {product_id}")
            
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
                    if not lt or not lt.get("isactive"):
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
                    link_type_name = lt.get("name") if lt else None

                result.append({
                    "id": product_link["id"],
                    "name": product_link["name"] or "",
                    "link": product_link["link"] or "",
                    "description": product_link["description"],
                    "link_type_id": product_link["link_type"],
                    "link_type_name": link_type_name,
                })

            await db.commit()
            logger.info("create_product_links in service processed successfully")
            return result
        except Exception as e:
            await db.rollback()
            logger.error("An error occurred in create_product_links service", exc_info=True)
            raise e

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
        try:
            logger.info(f"Processing update_link in service for link {link_id}")
            
            link = await ProductLinkRepository.get_link_by_id(db, link_id)
            if not link or not link.get("isactive"):
                raise ValueError("Link not found")

            # Validate link_type if provided
            if link_type is not None:
                lt = await ProductLinkRepository.get_link_type_by_id(db, link_type)
                if not lt or not lt.get("isactive"):
                    raise ValueError("Invalid link type")

            updated_link = await ProductLinkRepository.update_link(
                db=db,
                link_id=link_id,
                name=name,
                link_url=link_url,
                description=description,
                link_type=link_type,
                updated_by=user_id,
            )

            await db.commit()

            # Get link type name if exists
            link_type_name = None
            if updated_link.get("link_type"):
                lt = await ProductLinkRepository.get_link_type_by_id(db, updated_link["link_type"])
                link_type_name = lt.get("name") if lt else None

            logger.info("update_link in service processed successfully")
            return {
                "id": updated_link["id"],
                "name": updated_link["name"],
                "link": updated_link["link"],
                "description": updated_link["description"],
                "link_type_id": updated_link["link_type"],
                "link_type_name": link_type_name,
            }
        except Exception as e:
            await db.rollback()
            logger.error("An error occurred in update_link service", exc_info=True)
            raise e

    @staticmethod
    async def delete_link(
        db: AsyncSession,
        link_id: int,
        user_id: uuid.UUID,
    ) -> dict[str, Any]:
        """Soft delete a product link."""
        try:
            logger.info(f"Processing delete_link in service for link {link_id}")
            
            link = await ProductLinkRepository.get_link_by_id(db, link_id)
            if not link or not link.get("isactive"):
                raise ValueError("Link not found")

            await ProductLinkRepository.soft_delete_link(db, link_id, user_id)
            await db.commit()

            logger.info("delete_link in service processed successfully")
            return {"message": "Link deleted successfully"}
        except Exception as e:
            await db.rollback()
            logger.error("An error occurred in delete_link service", exc_info=True)
            raise e
