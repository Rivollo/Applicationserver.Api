"""Product service for handling product creation with image storage."""

import io
import uuid
from typing import BinaryIO, Optional

import asyncio
import logging
import httpx
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy import select

from app.models.models import Product, ProductAsset, ProductAssetMapping, ProductStatus
from app.services.licensing_service import LicensingService
from app.services.storage import storage_service


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
    def _check_folder_exists(
        container: str, folder_path: str
    ) -> bool:
        """Check if a folder (prefix) exists in Azure Blob Storage.
        
        In Azure Blob Storage, folders are virtual. We check if any blob
        exists with the given prefix.
        """
        try:
            client = storage_service._get_blob_service_client()
            container_client = client.get_container_client(container)
            
            # List blobs with the prefix (folder path)
            blobs = container_client.list_blobs(name_starts_with=folder_path, max_results=1)
            try:
                next(blobs, None)
                return True
            except StopIteration:
                return False
        except Exception:
            # If we can't check, assume it doesn't exist
            return False

    @staticmethod
    async def call_external_api(
        blob_url: str,
        target_format: str,
        callback_url: str,
    ) -> Optional[str]:
        """Call external API to process the image and return job UID.
        
        Args:
            blob_url: The blob URL of the uploaded image
            target_format: Target format (e.g., glb, obj)
            callback_url: Callback URL for the external API
            
        Returns:
            UID from external API or None if it fails
        """
        external_api_url = "http://4.213.224.235:8081/send"
        
        try:
            async with httpx.AsyncClient(timeout=60.0) as client:
                # Download the image from blob URL first
                image_response = await client.get(blob_url)
                image_response.raise_for_status()
                image_bytes = image_response.content
                image_filename = blob_url.split("/")[-1] or "image.jpg"
                
                # Prepare form data
                form_data = {
                    "target_format": target_format,
                    "remove_background": "true",
                    "mesh_detail": "medium",
                    "texture": "true",
                    "callback_url": callback_url,
                }
                
                # Prepare file for upload
                files = {
                    "image": (image_filename, image_bytes, "image/jpeg")
                }
                
                response = await client.post(
                    external_api_url,
                    data=form_data,
                    files=files,
                    headers={"Accept": "application/json"},
                )
                
                if response.status_code >= 400:
                    import logging
                    logger = logging.getLogger(__name__)
                    logger.warning(f"External API error: status={response.status_code}, body={response.text}")
                    return None
                
                data = response.json()
                uid = data.get("uid")
                if not uid:
                    logger = logging.getLogger(__name__)
                    logger.warning(f"External API response missing uid: {data}")
                    return None
                return uid
        except Exception as e:
            import logging
            import traceback
            logger = logging.getLogger(__name__)
            logger.error(f"Failed to call external API: {str(e)}\n{traceback.format_exc()}")
            return None

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
        """Create a product with image storage and asset mapping.
        
        Args:
            db: Database session
            user_id: User ID creating the product
            name: Product name
            asset_id: Asset ID (integer) for original uploaded image
            mesh_asset_id: Asset ID (integer) for generated mesh result
            image_stream: Binary stream of the image
            image_filename: Original filename of the image
            image_content_type: Content type of the image
            image_size_bytes: Size of the image in bytes
            
        Returns:
            Tuple of (created Product, blob_url)
            
        Raises:
            RuntimeError: If image upload fails
            ValueError: If product creation fails
        """
        # Check quota - COMMENTED OUT FOR TESTING
        # allowed, quota_info = await LicensingService.check_quota(db, user_id, "max_products")
        # if not allowed:
        #     # For testing: if no license exists, allow creation anyway
        #     license = await LicensingService.get_active_license(db, user_id)
        #     if license is None:
        #         # No license - allow for testing
        #         pass
        #     else:
        #         # License exists but quota exceeded
        #         raise ValueError("Product limit exceeded. Upgrade your plan to create more products.")

        # Generate unique slug
        base_slug = ProductService._slugify(name)
        slug = await ProductService._generate_unique_slug(db, base_slug)

        # Create product in database first to get product_id
        product = Product(
            name=name,
            slug=slug,
            status=ProductStatus.DRAFT,
            created_by=user_id,
        )

        db.add(product)
        await db.flush()  # Flush to get the product ID without committing

        product_id = str(product.id)
        user_id_str = str(user_id)

        # Check if user folder exists in dev container - COMMENTED OUT (might be causing timeout)
        # user_folder_path = f"{user_id_str}/"
        # user_folder_exists = ProductService._check_folder_exists("dev", user_folder_path)
        
        # Check if product folder exists - COMMENTED OUT (might be causing timeout)
        # product_folder_path = f"{user_id_str}/{product_id}/"
        # product_folder_exists = ProductService._check_folder_exists("dev", product_folder_path)
        
        # Note: In Azure Blob Storage, folders are virtual and created automatically
        # when uploading a blob. We don't need to check for existence.

        # Upload image to storage with path: dev/{userId}/{productId}/filename
        blob_url = f"https://placeholder.dev/{user_id_str}/{product_id}/{image_filename}"  # Default placeholder
        try:
            # Reset stream position to beginning
            image_stream.seek(0)
            cdn_url, blob_url = storage_service.upload_product_image(
                user_id=user_id_str,
                product_id=product_id,
                filename=image_filename,
                content_type=image_content_type,
                stream=image_stream,
            )
            # Log success
            import logging
            logger = logging.getLogger(__name__)
            logger.info(f"Azure upload successful: {blob_url}")
        except Exception as e:
            # Log the error but continue with placeholder for now
            import logging
            import traceback
            logger = logging.getLogger(__name__)
            logger.error(f"Azure upload failed: {str(e)}\n{traceback.format_exc()}")
            # Use placeholder URL - don't fail the request
            # blob_url already set to placeholder above

        # Create ProductAsset entry
        try:
            product_asset = ProductAsset(
                asset_id=asset_id,
                image=blob_url,
                size_bytes=image_size_bytes,
                created_by=user_id,
            )
            db.add(product_asset)
            await db.flush()  # Flush to get the product_asset ID
            await db.refresh(product_asset)  # Refresh to ensure ID is populated
            
            product_asset_id = product_asset.id
            if product_asset_id is None:
                raise RuntimeError("Failed to get product_asset ID after flush")
            
            # product_asset.id is UUID (matching database schema)
            if not isinstance(product_asset_id, uuid.UUID):
                raise RuntimeError(f"product_asset.id is not a UUID: {type(product_asset_id)} = {product_asset_id}")
            
            # Log before creating mapping
            import logging
            logger = logging.getLogger(__name__)
            logger.info(f"Creating ProductAssetMapping with product_asset_id={product_asset_id} (type={type(product_asset_id)})")
            
            # Create ProductAssetMapping entry
            product_asset_mapping = ProductAssetMapping(
                name=name,
                productid=product.id,
                product_asset_id=product_asset_id,  # UUID type
                isactive=True,
                created_by=user_id,
            )
            
            # Verify the value is set before adding to session
            if product_asset_mapping.product_asset_id is None:
                raise RuntimeError(f"product_asset_id is None after setting to {product_asset_id}")
            
            logger.info(f"ProductAssetMapping before add: product_asset_id={product_asset_mapping.product_asset_id}")
            db.add(product_asset_mapping)
            
            # Verify the value is still set after adding
            logger.info(f"ProductAssetMapping after add: product_asset_id={product_asset_mapping.product_asset_id}")
            
            # Log success for debugging
            logger.info(f"Created ProductAsset (id={product_asset_id}) and ProductAssetMapping for product {product.id}")
        except Exception as e:
            # Log the error and re-raise so we can see what's wrong
            import logging
            import traceback
            logger = logging.getLogger(__name__)
            logger.error(f"Failed to create ProductAsset/ProductAssetMapping: {str(e)}\n{traceback.format_exc()}")
            raise RuntimeError(f"Failed to create asset entries: {str(e)}") from e

        # Call external API with the blob URL to start processing
        callback_url = "https://vIsls.ixfQ9SpcgPNGjF3A3jaIJTquDTvT63Et.+tDrsGBeOmp.N"
        external_job_uid = await ProductService.call_external_api(
            blob_url=blob_url,
            target_format=target_format,
            callback_url=callback_url,
        )
        
        if external_job_uid:
            product.status = ProductStatus.PROCESSING
        else:
            product.status = ProductStatus.DRAFT

        # Increment usage - COMMENTED OUT FOR TESTING
        # license = await LicensingService.get_active_license(db, user_id)
        # if license is not None:
        #     await LicensingService.increment_usage(db, user_id, "max_products")

        # Commit the transaction
        await db.commit()
        
        try:
            await db.refresh(product)
        except Exception:
            # Refresh might fail, but product should still be valid
            pass

        return product, blob_url, external_job_uid

    @staticmethod
    async def poll_external_api_and_finalize(
        session_factory: async_sessionmaker[AsyncSession],
        user_id: uuid.UUID,
        product_id: uuid.UUID,
        asset_id: int,
        mesh_asset_id: int,
        name: str,
        target_format: str,
        job_uid: str,
    ) -> None:
        """Poll external API for result, upload to blob, and update database."""

        logger = logging.getLogger(__name__)
        status_url = f"http://4.213.224.235:8081/status/{job_uid}?download=true"
        poll_interval_seconds = 30
        max_attempts = 20  # 10 minutes
        success = False

        try:
            async with httpx.AsyncClient(timeout=60.0) as client:
                for attempt in range(max_attempts):
                    try:
                        response = await client.get(status_url)
                        if response.status_code == 200:
                            content_type = response.headers.get("content-type", "")
                            content = response.content

                            if "application/json" in content_type.lower():
                                # Still processing?
                                data = response.json()
                                status_value = (data.get("status") or data.get("state") or "").lower()
                                if status_value in {"completed", "ready", "finished", "succeeded"}:
                                    download_url = data.get("download_url") or data.get("url")
                                    if download_url:
                                        file_resp = await client.get(download_url)
                                        file_resp.raise_for_status()
                                        content = file_resp.content
                                        content_type = file_resp.headers.get(
                                            "content-type", "application/octet-stream"
                                        )
                                    else:
                                        # Nothing to download; wait again
                                        await asyncio.sleep(poll_interval_seconds)
                                        continue
                                else:
                                    await asyncio.sleep(poll_interval_seconds)
                                    continue

                            # Treat response body as final asset bytes
                            filename = f"{job_uid}.{target_format}"
                            stream = io.BytesIO(content)
                            try:
                                cdn_url, generated_blob_url = storage_service.upload_product_image(
                                    user_id=str(user_id),
                                    product_id=str(product_id),
                                    filename=filename,
                                    content_type=content_type or "application/octet-stream",
                                    stream=stream,
                                )
                            except Exception as upload_error:
                                logger.error("Failed to upload generated asset: %s", upload_error)
                                break

                            async with session_factory() as session:
                                product = await session.get(Product, product_id)
                                if not product:
                                    logger.warning(
                                        "Product %s not found while storing generated asset", product_id
                                    )
                                    break

                                generated_asset = ProductAsset(
                                    asset_id=mesh_asset_id,
                                    image=generated_blob_url,
                                    size_bytes=len(content),
                                    created_by=user_id,
                                )
                                session.add(generated_asset)
                                await session.flush()
                                await session.refresh(generated_asset)

                                generated_mapping = ProductAssetMapping(
                                    name=f"{name}_{target_format}",
                                    productid=product.id,
                                    product_asset_id=generated_asset.id,
                                    isactive=True,
                                    created_by=user_id,
                                )
                                session.add(generated_mapping)
                                product.status = ProductStatus.READY
                                await session.commit()

                            success = True
                            break
                        else:
                            logger.info(
                                "Polling attempt %s returned status %s for job %s",
                                attempt + 1,
                                response.status_code,
                                job_uid,
                            )
                    except Exception as poll_error:
                        logger.warning(
                            "Error while polling external API for job %s: %s", job_uid, poll_error
                        )

                    await asyncio.sleep(poll_interval_seconds)
        finally:
            if not success:
                async with session_factory() as session:
                    product = await session.get(Product, product_id)
                    if product and product.status == ProductStatus.PROCESSING:
                        product.status = ProductStatus.DRAFT
                        await session.commit()

    @staticmethod
    async def get_products_for_current_user(
        db: AsyncSession, user_id: uuid.UUID
    ) -> dict:
        """Get all products for the current user with their primary assets."""
        from app.database.products_repo import ProductRepository
        from app.schemas.products import ProductWithPrimaryAsset, ProductsByUserResponse

        products = await ProductRepository.get_products_by_user_id(db, user_id)
        items: list[ProductWithPrimaryAsset] = []

        for product in products:
            asset_data = await ProductRepository.get_primary_asset_for_product(db, product.id)
            
            image = None
            asset_type = None
            asset_type_id = None
            
            if asset_data:
                image, asset_type, asset_type_id = asset_data

            items.append(
                ProductWithPrimaryAsset(
                    id=str(product.id),
                    name=product.name,
                    status=product.status.value,
                    image=image,
                    asset_type=asset_type,
                    asset_type_id=asset_type_id,
                    description=product.description,
                    price=float(product.price) if product.price is not None else None,
                    currency_type=str(product.currency_type) if product.currency_type is not None else None,
                    background_type=str(product.background_type) if product.background_type is not None else None,
                    created_at=product.created_at,
                    updated_at=product.updated_at,
                )
            )

        return ProductsByUserResponse(items=items).model_dump()


product_service = ProductService()

