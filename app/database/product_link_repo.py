"""
Repository layer for product link database operations.
Uses raw SQL with SQLAlchemy for full query control.
"""

import logging
import uuid
from typing import Optional

from fastapi import HTTPException
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


class ProductLinkRepository:
    """Repository for product link database operations."""

    # ---------- Link Types ----------

    @staticmethod
    async def get_all_link_types(db: AsyncSession) -> list[dict]:
        """Get all active link types."""
        try:
            logger.info("Request for get_all_link_types")
            
            sql = text("""
                SELECT id, name, description 
                FROM tbl_product_link_type 
                WHERE isactive = true 
                ORDER BY name
            """)
            
            result = await db.execute(sql)
            rows = result.fetchall()
            
            link_types = [
                {
                    "id": row[0],
                    "name": row[1],
                    "description": row[2]
                }
                for row in rows
            ]
            
            logger.info(f"Response for get_all_link_types: {len(link_types)} types found")
            return link_types
            
        except Exception as e:
            error_message = f"An error occurred: {str(e)}"
            logger.error("A system failure occurred @get_all_link_types", exc_info=True)
            raise HTTPException(status_code=500, detail="Internal server error in get_all_link_types: " + error_message)

    @staticmethod
    async def get_link_type_by_id(db: AsyncSession, link_type_id: int) -> Optional[dict]:
        """Get a link type by ID."""
        try:
            logger.info(f"Request for get_link_type_by_id: {link_type_id}")
            
            sql = text("""
                SELECT id, name, description, isactive 
                FROM tbl_product_link_type 
                WHERE id = :link_type_id
            """)
            
            result = await db.execute(sql, {"link_type_id": link_type_id})
            row = result.fetchone()
            
            if row:
                link_type = {
                    "id": row[0],
                    "name": row[1],
                    "description": row[2],
                    "isactive": row[3]
                }
                logger.info(f"Response for get_link_type_by_id: {link_type}")
                return link_type
            else:
                logger.info(f"Response for get_link_type_by_id: None")
                return None
                
        except Exception as e:
            error_message = f"An error occurred: {str(e)}"
            logger.error("A system failure occurred @get_link_type_by_id", exc_info=True)
            raise HTTPException(status_code=500, detail="Internal server error in get_link_type_by_id: " + error_message)

    # ---------- Product Links ----------

    @staticmethod
    async def get_links_by_product(db: AsyncSession, product_id: uuid.UUID) -> list[dict]:
        """Get all active links for a product."""
        try:
            logger.info(f"Request for get_links_by_product: {product_id}")
            
            sql = text("""
                SELECT 
                    pl.id, 
                    pl.name, 
                    pl.link, 
                    pl.description, 
                    pl.link_type,
                    plt.name as link_type_name,
                    pl.created_date
                FROM tbl_product_links pl
                LEFT JOIN tbl_product_link_type plt ON pl.link_type = plt.id
                WHERE pl.productid = :product_id 
                AND pl.isactive = true
                ORDER BY pl.created_date DESC
            """)
            
            result = await db.execute(sql, {"product_id": str(product_id)})
            rows = result.fetchall()
            
            links = [
                {
                    "id": row[0],
                    "name": row[1],
                    "link": row[2],
                    "description": row[3],
                    "link_type": row[4],
                    "link_type_name": row[5],
                    "created_date": row[6]
                }
                for row in rows
            ]
            
            logger.info(f"Response for get_links_by_product: {len(links)} links found")
            return links
            
        except Exception as e:
            error_message = f"An error occurred: {str(e)}"
            logger.error("A system failure occurred @get_links_by_product", exc_info=True)
            raise HTTPException(status_code=500, detail="Internal server error in get_links_by_product: " + error_message)

    @staticmethod
    async def get_link_by_id(db: AsyncSession, link_id: int) -> Optional[dict]:
        """Get a link by ID."""
        try:
            logger.info(f"Request for get_link_by_id: {link_id}")
            
            sql = text("""
                SELECT id, productid, name, link, description, link_type, isactive 
                FROM tbl_product_links 
                WHERE id = :link_id
            """)
            
            result = await db.execute(sql, {"link_id": link_id})
            row = result.fetchone()
            
            if row:
                link = {
                    "id": row[0],
                    "productid": row[1],
                    "name": row[2],
                    "link": row[3],
                    "description": row[4],
                    "link_type": row[5],
                    "isactive": row[6]
                }
                logger.info(f"Response for get_link_by_id: link found")
                return link
            else:
                logger.info(f"Response for get_link_by_id: None")
                return None
                
        except Exception as e:
            error_message = f"An error occurred: {str(e)}"
            logger.error("A system failure occurred @get_link_by_id", exc_info=True)
            raise HTTPException(status_code=500, detail="Internal server error in get_link_by_id: " + error_message)

    @staticmethod
    async def create_link(
        db: AsyncSession,
        product_id: uuid.UUID,
        name: str,
        link: str,
        description: Optional[str],
        link_type: Optional[int],
        created_by: uuid.UUID,
    ) -> dict:
        """Create a new product link."""
        try:
            logger.info(f"Request for create_link: product_id={product_id}, name={name}")
            
            sql = text("""
                INSERT INTO tbl_product_links 
                (productid, name, link, description, link_type, isactive, created_by, updated_by, updated_date)
                VALUES (:productid, :name, :link, :description, :link_type, true, :created_by, :updated_by, CURRENT_TIMESTAMP)
                RETURNING id, productid, name, link, description, link_type, created_date
            """)
            
            result = await db.execute(sql, {
                "productid": str(product_id),
                "name": name,
                "link": link,
                "description": description,
                "link_type": link_type,
                "created_by": created_by,
                "updated_by": None
            })
            
            row = result.fetchone()
            
            product_link = {
                "id": row[0],
                "productid": row[1],
                "name": row[2],
                "link": row[3],
                "description": row[4],
                "link_type": row[5],
                "created_date": row[6]
            }
            
            logger.info(f"Response for create_link: link created with ID {product_link['id']}")
            return product_link
            
        except Exception as e:
            error_message = f"An error occurred: {str(e)}"
            logger.error("A system failure occurred @create_link", exc_info=True)
            raise HTTPException(status_code=500, detail="Internal server error in create_link: " + error_message)

    @staticmethod
    async def update_link(
        db: AsyncSession,
        link_id: int,
        name: Optional[str],
        link_url: Optional[str],
        description: Optional[str],
        link_type: Optional[int],
        updated_by: uuid.UUID,
    ) -> dict:
        """Update an existing product link."""
        try:
            logger.info(f"Request for update_link: link_id={link_id}")
            
            # Build dynamic update query based on provided fields
            update_fields = []
            params = {"link_id": link_id, "updated_by": updated_by}
            
            if name is not None:
                update_fields.append("name = :name")
                params["name"] = name
            if link_url is not None:
                update_fields.append("link = :link")
                params["link"] = link_url
            if description is not None:
                update_fields.append("description = :description")
                params["description"] = description
            if link_type is not None:
                update_fields.append("link_type = :link_type")
                params["link_type"] = link_type
            
            update_fields.append("updated_by = :updated_by")
            update_fields.append("updated_date = CURRENT_TIMESTAMP")
            
            sql = text(f"""
                UPDATE tbl_product_links 
                SET {', '.join(update_fields)}
                WHERE id = :link_id
                RETURNING id, productid, name, link, description, link_type
            """)
            
            result = await db.execute(sql, params)
            row = result.fetchone()
            
            updated_link = {
                "id": row[0],
                "productid": row[1],
                "name": row[2],
                "link": row[3],
                "description": row[4],
                "link_type": row[5]
            }
            
            logger.info(f"Response for update_link: link {link_id} updated successfully")
            return updated_link
            
        except Exception as e:
            error_message = f"An error occurred: {str(e)}"
            logger.error("A system failure occurred @update_link", exc_info=True)
            raise HTTPException(status_code=500, detail="Internal server error in update_link: " + error_message)

    @staticmethod
    async def soft_delete_link(
        db: AsyncSession,
        link_id: int,
        deleted_by: uuid.UUID,
    ) -> None:
        """Soft delete a link (set isactive=false)."""
        try:
            logger.info(f"Request for soft_delete_link: link_id={link_id}")
            
            sql = text("""
                UPDATE tbl_product_links 
                SET isactive = false, 
                    updated_by = :deleted_by,
                    updated_date = CURRENT_TIMESTAMP
                WHERE id = :link_id
            """)
            
            await db.execute(sql, {"link_id": link_id, "deleted_by": deleted_by})
            
            logger.info(f"Response for soft_delete_link: link {link_id} deleted successfully")
            
        except Exception as e:
            error_message = f"An error occurred: {str(e)}"
            logger.error("A system failure occurred @soft_delete_link", exc_info=True)
            raise HTTPException(status_code=500, detail="Internal server error in soft_delete_link: " + error_message)
