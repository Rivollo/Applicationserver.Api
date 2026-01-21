"""Product service for handling product creation with image storage."""

import uuid
from typing import BinaryIO, Optional

import logging
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.models.models import Product, ProductAsset, ProductAssetMapping, ProductStatus
from app.services.storage import storage_service
from app.integrations.service_bus_publisher import ServiceBusPublisher


class ProductService:
    """Service for product operations."""

    @staticmethod
    def _slugify(text: str) -> str:
        """Convert text to URL-friendly slug."""
        import re

        text = text.lower().strip()
        text = re.sub(r"[^\w\s-]", "", text)
        text = re.sub(r"[-\s]+", "-", text)
        return text[:100]

    @staticmethod
    async def _generate_unique_slug(
        db: AsyncSession, base_slug: str, exclude_id: Optional[uuid.UUID] = None
    ) -> str:
        """Generate a unique slug for a product."""
        pattern = f"{base_slug}%"
        res = await db.execute(
            select(Product.slug, Product.id).where(Product.slug.like(pattern))
        )
        rows = res.all()
        existing = {slug for slug, pid in rows if exclude_id is None or pid != exclude_id}
        if base_slug not in existing:
            return base_slug
        i = 2
        while True:
            cand = f"{base_slug}-{i}"
            if cand not in existing:
                return cand
            i += 1

    @staticmethod
    async def create_product_with_image(
        db: AsyncSession,
        user_id: uuid.UUID,
        name: str,
        asset_id: int,
        target_format: str,
        mesh_asset_id: int,
        image_stream: BinaryIO,
        image_filename: str,
        image_content_type: Optional[str] = None,
        image_size_bytes: Optional[int] = None,
    ) -> tuple[Product, str, Optional[str]]:
        """Create a product and publish processing request to Service Bus."""

        logger = logging.getLogger(__name__)

        # -------------------------------
        # 1. Create product (DB)
        # -------------------------------
        base_slug = ProductService._slugify(name)
        slug = await ProductService._generate_unique_slug(db, base_slug)

        product = Product(
            name=name,
            slug=slug,
            status=ProductStatus.DRAFT,
            created_by=user_id,
        )

        db.add(product)
        await db.flush()

        product_id = str(product.id)
        user_id_str = str(user_id)

        # -------------------------------
        # 2. Upload original image
        # -------------------------------
        blob_url = f"https://placeholder.dev/{user_id_str}/{product_id}/{image_filename}"
        try:
            image_stream.seek(0)
            _, blob_url = storage_service.upload_product_image(
                user_id=user_id_str,
                product_id=product_id,
                filename=image_filename,
                content_type=image_content_type,
                stream=image_stream,
            )
            logger.info("Image uploaded: %s", blob_url)
        except Exception as e:
            logger.error("Image upload failed, using placeholder: %s", e)

        # -------------------------------
        # 3. Create ProductAsset + Mapping
        # -------------------------------
        try:
            product_asset = ProductAsset(
                asset_id=asset_id,
                image=blob_url,
                size_bytes=image_size_bytes,
                created_by=user_id,
            )
            db.add(product_asset)
            await db.flush()
            await db.refresh(product_asset)

            product_asset_mapping = ProductAssetMapping(
                name=name,
                productid=product.id,
                product_asset_id=product_asset.id,
                isactive=True,
                created_by=user_id,
            )
            db.add(product_asset_mapping)
        except Exception as e:
            logger.exception("Failed to create asset records")
            raise RuntimeError("Failed to create asset entries") from e

        # -------------------------------
        # 4. HANDOFF TO SERVICE BUS
        # -------------------------------
        payload = {
            "product_id": str(product.id),
            "user_id": str(user_id),
            "blob_url": blob_url,
            "target_format": target_format,
            "asset_id": asset_id,
            "mesh_asset_id": mesh_asset_id,
            "name": name,
        }

        logger.info("Publishing message to Service Bus: %s", payload)
        published = await ServiceBusPublisher.publish(payload)

        # -------------------------------
        # 5. Update status & commit
        # -------------------------------
        # Set status based on whether Service Bus publish succeeded
        if published:
            product.status = ProductStatus.PROCESSING
            logger.info("Product %s queued for background processing", product.id)
        else:
            product.status = ProductStatus.DRAFT
            logger.warning(
                "Product %s created but background processing not queued. "
                "Manual processing may be required.",
                product.id
            )
        await db.commit()

        try:
            await db.refresh(product)
        except Exception:
            pass

        return product, blob_url, None


product_service = ProductService()
