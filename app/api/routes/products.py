"""Product management routes."""

import io
import uuid
from datetime import datetime
from typing import Optional

import asyncio
from fastapi import APIRouter, File, Form, HTTPException, Query, Request, UploadFile, status
from pydantic import BaseModel
from sqlalchemy import and_, desc, func, or_, select, cast, String
from sqlalchemy.ext.asyncio import async_sessionmaker
from sqlalchemy.orm import joinedload

from app.api.deps import CurrentUser, DB
from app.models.models import (
    AssetStatic,
    Configurator,
    Hotspot,
    Product,
    ProductAsset,
    ProductAssetMapping,
    ProductStatus,
    PublishLink,
)
from app.schemas.products import (
    ConfiguratorSettings,
    ProductAssetsData,
    ProductAssetsResponse,
    ProductCreate,
    ProductImageItem,
    ProductListResponse,
    ProductsByUserResponse,
    ProductResponse,
    ProductStatusData,
    ProductStatusResponse,
    ProductUpdate,
    ProductWithPrimaryAsset,
    PublishProductRequest,
    PublishProductResponse,
)
from app.services.activity_service import ActivityService
from app.services.licensing_service import LicensingService
from app.services.product_service import product_service
from app.services.storage import storage_service
from app.utils.envelopes import api_success

router = APIRouter(tags=["products"])


def _slugify(text: str) -> str:
    """Convert text to URL-friendly slug."""
    import re

    text = text.lower().strip()
    text = re.sub(r"[^\w\s-]", "", text)
    text = re.sub(r"[-\s]+", "-", text)
    return text[:100]


async def _generate_unique_slug(
    db: DB, base_slug: str, exclude_id: Optional[uuid.UUID] = None
) -> str:
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


# No org context needed; keep API org-free


@router.get("/products", response_model=dict)
async def list_products(
    current_user: CurrentUser,
    db: DB,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100, alias="pageSize"),
    q: Optional[str] = Query(None, max_length=200),
    status_filter: Optional[str] = Query(None, alias="status"),
    tags: Optional[str] = None,
    sort: str = Query("-createdAt"),
):
    """List products with filtering and pagination."""
    # Base query
    query = select(Product).where(Product.deleted_at.is_(None))

    # Apply filters (DB has no metadata column; search name only)
    if q:
        search_pattern = f"%{q}%"
        query = query.where(Product.name.ilike(search_pattern))

    if status_filter:
        query = query.where(Product.status == status_filter)

    # tags column not present in DB; ignore tags filter

    # Count total
    count_query = select(func.count()).select_from(query.subquery())
    total_result = await db.execute(count_query)
    total = total_result.scalar() or 0

    # Apply sorting (map friendly keys to real DB columns)
    desc_order = sort.startswith("-")
    sort_field = sort[1:] if desc_order else sort
    field_map = {
        "createdAt": Product.created_date,
        "updatedAt": Product.updated_date,
        "name": Product.name,
        "status": Product.status,
    }
    order_base = field_map.get(sort_field, Product.created_date)
    order_col = desc(order_base) if desc_order else order_base

    query = query.order_by(order_col)

    # Apply pagination
    offset = (page - 1) * page_size
    query = query.offset(offset).limit(page_size)

    # Execute
    result = await db.execute(query)
    products = result.scalars().all()

    # Build response
    items = [
        ProductResponse(
            id=str(p.id),
            name=p.name,
            description=None,
            brand=None,
            accent_color="#2563EB",
            accent_overlay=None,
            tags=[],
            status=p.status.value,
            created_at=p.created_at,
            updated_at=p.updated_at,
        )
        for p in products
    ]

    total_pages = (total + page_size - 1) // page_size

    return api_success(
        {
            "items": [item.model_dump(exclude_none=True) for item in items],
            "meta": {
                "page": page,
                "pageSize": page_size,
                "total": total,
                "totalPages": total_pages,
            },
        }
    )


@router.post("/products", response_model=dict, status_code=status.HTTP_201_CREATED)
async def create_product(
    payload: ProductCreate,
    current_user: CurrentUser,
    request: Request,
    db: DB,
):
    """Create a new product."""
    # Check quota
    allowed, quota_info = await LicensingService.check_quota(db, current_user.id, "max_products")

    if not allowed:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Product limit exceeded. Upgrade your plan to create more products.",
        )

    # Generate unique slug per org
    slug = await _generate_unique_slug(db, _slugify(payload.name))

    # Create product (DB doesn't have tags/metadata columns)
    product = Product(
        name=payload.name,
        slug=slug,
        status=ProductStatus.DRAFT,
        created_by=current_user.id,
    )

    db.add(product)
    await db.flush()

    # Increment usage
    await LicensingService.increment_usage(db, current_user.id, "max_products")

    # Log activity
    await ActivityService.log_product_action(
        db=db,
        action="product.created",
        user_id=current_user.id,
        product_id=product.id,
        request=request,
    )

    await db.commit()
    await db.refresh(product)

    response_data = ProductResponse(
        id=str(product.id),
        name=product.name,
        description=payload.description,
        brand=payload.brand,
        accent_color=payload.accent_color,
        accent_overlay=payload.accent_overlay,
        tags=payload.tags,
        status=product.status.value,
        created_at=product.created_at,
        updated_at=product.updated_at,
    )

    return api_success(response_data.model_dump(exclude_none=True))


@router.post("/createProduct", response_model=dict, status_code=status.HTTP_201_CREATED)
async def create_product_with_image(
    request: Request,
    db: DB,
    userId: str = Form(..., description="User ID creating the product"),
    name: str = Form(..., min_length=1, max_length=200, description="Product name"),
    asset_id: int = Form(..., description="Asset ID (integer)"),
    mesh_asset_id: int = Form(..., description="Mesh asset ID for generated output (integer)"),
    target_format: str = Form(..., description="Target format for external API (e.g., glb, obj)"),
    image: UploadFile = File(..., description="Image file to upload (JPG, PNG, WEBP, GIF)"),
):
    """Create a new product with an image file upload (authentication disabled for testing)."""
    # Validate user ID
    try:
        user_uuid = uuid.UUID(userId)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid userId format. Expected UUID string.",
        )

    # Validate file type
    if not image.filename:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Image file is required",
        )

    # Validate image file extension
    allowed_extensions = {".jpg", ".jpeg", ".png", ".webp", ".gif"}
    file_ext = None
    for ext in allowed_extensions:
        if image.filename.lower().endswith(ext):
            file_ext = ext
            break
    
    if not file_ext:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid image format. Allowed formats: {', '.join(allowed_extensions)}",
        )

    # Read image file
    try:
        image_bytes = await image.read()
        content_type = image.content_type or f"image/{file_ext[1:]}"
        filename = image.filename or f"product-image{file_ext}"
        image_stream = io.BytesIO(image_bytes)
        image_size_bytes = len(image_bytes)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Failed to read image file: {str(e)}",
        )

    # Use ProductService to create product and upload image
    try:
        product, blob_url, external_job_uid = await product_service.create_product_with_image(
            db=db,
            user_id=user_uuid,
            name=name,
            asset_id=asset_id,
            mesh_asset_id=mesh_asset_id,
            target_format=target_format,
            image_stream=image_stream,
            image_filename=filename,
            image_content_type=content_type,
            image_size_bytes=image_size_bytes,
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(e),
        )
    except RuntimeError as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e),
        )
    except Exception as e:
        # Catch all other exceptions and return the actual error for debugging
        import traceback
        error_detail = f"{str(e)}\n\nTraceback:\n{traceback.format_exc()}"
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=error_detail,
        )

    # Log activity - COMMENTED OUT FOR TESTING (might be causing timeout)
    # await ActivityService.log_product_action(
    #     db=db,
    #     action="product.created",
    #     user_id=user_uuid,
    #     product_id=product.id,
    #     request=request,
    # )

    response_data = ProductResponse(
        id=str(product.id),
        name=product.name,
        description=None,
        brand=None,
        accent_color="#2563EB",
        accent_overlay=None,
        tags=[],
        status=product.status.value,
        created_at=product.created_at,
        updated_at=product.updated_at,
    )

    # Return response with blob URL
    response_dict = response_data.model_dump(exclude_none=True)
    response_dict["image_blob_url"] = blob_url

    # Kick off background polling for external API
    if external_job_uid:
        engine = db.bind
        if engine is not None:
            session_factory = async_sessionmaker(bind=engine, expire_on_commit=False)
            asyncio.create_task(
                product_service.poll_external_api_and_finalize(
                    session_factory=session_factory,
                    user_id=user_uuid,
                    product_id=product.id,
                    asset_id=asset_id,
                    mesh_asset_id=mesh_asset_id,
                    name=name,
                    target_format=target_format,
                    job_uid=external_job_uid,
                )
            )

    return api_success(response_dict)


@router.get("/products/{product_id}", response_model=dict)
async def get_product(
    product_id: str,
    current_user: CurrentUser,
    db: DB,
):
    """Get product by ID."""
    # Parse product ID
    try:
        prod_uuid = uuid.UUID(product_id)
    except ValueError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Product not found")

    # Fetch product with configurator
    result = await db.execute(
        select(Product)
        .options(joinedload(Product.configurator))
        .where(
            Product.id == prod_uuid if prod_uuid else cast(Product.id, String).like(f"{product_id}%"),
            Product.deleted_at.is_(None),
        )
    )
    product = result.scalar_one_or_none()

    if not product:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Product not found")

    # Build configurator settings if exists
    configurator_data = None
    if product.configurator:
        import json
        cfg = json.loads(product.configurator.settings) if product.configurator.settings else {}
        configurator_data = ConfiguratorSettings(**cfg)

    response_data = ProductResponse(
        id=str(product.id),
        name=product.name,
        description=None,
        brand=None,
        accent_color="#2563EB",
        accent_overlay=None,
        tags=[],
        status=product.status.value,
        created_at=product.created_at,
        updated_at=product.updated_at,
        configurator=configurator_data,
    )

    return api_success(response_data.model_dump(exclude_none=True))


@router.get("/products/{product_id}/assets", response_model=dict)
async def get_product_assets(product_id: str, db: DB):
    """Return all assets associated with a product."""
    try:
        product_uuid = uuid.UUID(product_id)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid productId format. Expected UUID string.",
        )

    # Get product to retrieve name
    product = await db.get(Product, product_uuid)
    if not product:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Product not found.",
        )

    # Join ProductAsset with ProductAssetMapping and AssetStatic
    stmt = (
        select(
            ProductAsset.asset_id,
            ProductAsset.image,
            AssetStatic.name.label("asset_name"),
            AssetStatic.assetid.label("asset_type_id"),
        )
        .join(ProductAssetMapping, ProductAsset.id == ProductAssetMapping.product_asset_id)
        .join(AssetStatic, ProductAsset.asset_id == AssetStatic.id)
        .where(ProductAssetMapping.productid == product_uuid)
        .where(ProductAssetMapping.isactive == True)
        .order_by(ProductAssetMapping.created_date.desc())
    )
    result = await db.execute(stmt)
    rows = result.all()

    # Separate mesh (assetid = 2) from other images
    meshurl: Optional[str] = None
    images: list[ProductImageItem] = []

    for row in rows:
        asset_id, image_url, asset_name, asset_type_id = row
        if asset_type_id == 2:
            # This is the mesh (assetid = 2 in tbl_asset)
            meshurl = image_url
        else:
            # This is a regular image
            images.append(ProductImageItem(url=image_url, type=asset_name))

    # Build response
    data = ProductAssetsData(
        id=str(product.id),
        name=product.name,
        status=product.status.value,
        meshurl=meshurl,
        images=images,
    )

    return api_success(ProductAssetsResponse(data=data).model_dump())


@router.get("/products/user/{userId}", response_model=dict)
async def get_products_by_user(userId: str, db: DB):
    """Get all products for a user with their primary asset (asset_id = 1)."""
    try:
        user_uuid = uuid.UUID(userId)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid userId format. Expected UUID string.",
        )

    # Query products with LEFT JOIN to get primary asset (asset_id = 1) in a single query
    # Using a subquery to get the latest primary asset per product
    
    # Subquery to get the latest primary asset image per product
    # First, create a subquery with row_number
    ranked_assets = (
        select(
            ProductAssetMapping.productid,
            ProductAsset.image,
            ProductAsset.asset_id,
            AssetStatic.name.label("asset_name"),
            func.row_number()
            .over(
                partition_by=ProductAssetMapping.productid,
                order_by=ProductAssetMapping.created_date.desc()
            )
            .label("rn")
        )
        .join(ProductAsset, ProductAsset.id == ProductAssetMapping.product_asset_id)
        .join(AssetStatic, ProductAsset.asset_id == AssetStatic.id)
        .where(
            ProductAsset.asset_id == 1,  # Primary asset
            ProductAssetMapping.isactive == True,
        )
        .subquery()
    )
    
    # Filter to get only rn == 1 (latest per product)
    primary_asset_subquery = (
        select(
            ranked_assets.c.productid,
            ranked_assets.c.image,
            ranked_assets.c.asset_id,
            ranked_assets.c.asset_name,
        )
        .where(ranked_assets.c.rn == 1)
        .subquery()
    )
    
    # Main query: products LEFT JOIN with primary asset subquery
    query = (
        select(
            Product.id,
            Product.name,
            Product.status,
            Product.created_date,
            Product.updated_date,
            primary_asset_subquery.c.image.label("image"),
            primary_asset_subquery.c.asset_name.label("asset_type"),
            primary_asset_subquery.c.asset_id.label("asset_type_id"),
        )
        .outerjoin(
            primary_asset_subquery,
            Product.id == primary_asset_subquery.c.productid
        )
        .where(
            Product.created_by == user_uuid,
            Product.deleted_at.is_(None),
        )
        .order_by(Product.created_date.desc())
    )
    
    result = await db.execute(query)
    rows = result.all()

    # Build response items
    items: list[ProductWithPrimaryAsset] = []
    for row in rows:
        product_id, name, product_status, created_date, updated_date, image, asset_type, asset_type_id = row
        items.append(
            ProductWithPrimaryAsset(
                id=str(product_id),
                name=name,
                status=product_status.value,
                image=image,
                asset_type=asset_type,
                asset_type_id=asset_type_id,
                created_at=created_date,
                updated_at=updated_date,
            )
        )

    return api_success(ProductsByUserResponse(items=items).model_dump())


@router.get("/products/{product_id}/status", response_model=dict)
async def get_product_status(product_id: str, db: DB):
    """Get product status. If status is READY, returns assets. Otherwise returns status details."""
    try:
        product_uuid = uuid.UUID(product_id)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid productId format. Expected UUID string.",
        )

    # Get product
    product = await db.get(Product, product_uuid)
    if not product:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Product not found.",
        )

    # If status is READY, return assets (same as get_product_assets)
    if product.status == ProductStatus.READY:
        # Join ProductAsset with ProductAssetMapping and AssetStatic
        stmt = (
            select(
                ProductAsset.asset_id,
                ProductAsset.image,
                AssetStatic.name.label("asset_name"),
                AssetStatic.assetid.label("asset_type_id"),
            )
            .join(ProductAssetMapping, ProductAsset.id == ProductAssetMapping.product_asset_id)
            .join(AssetStatic, ProductAsset.asset_id == AssetStatic.id)
            .where(ProductAssetMapping.productid == product_uuid)
            .where(ProductAssetMapping.isactive == True)
            .order_by(ProductAssetMapping.created_date.desc())
        )
        result = await db.execute(stmt)
        rows = result.all()

        # Separate mesh (assetid = 2) from other images
        meshurl: Optional[str] = None
        images: list[ProductImageItem] = []

        for row in rows:
            asset_id, image_url, asset_name, asset_type_id = row
            if asset_type_id == 2:
                # This is the mesh (assetid = 2 in tbl_asset)
                meshurl = image_url
            else:
                # This is a regular image
                images.append(ProductImageItem(url=image_url, type=asset_name))

        # Build response (same as get_product_assets)
        data = ProductAssetsData(
            id=str(product.id),
            name=product.name,
            status=product.status.value,
            meshurl=meshurl,
            images=images,
        )

        return api_success(ProductAssetsResponse(data=data).model_dump())
    else:
        # Status is not READY, return status details with product info
        status_data = ProductStatusData(
            id=str(product.id),
            name=product.name,
            status=product.status.value,
            created_at=product.created_at,
            updated_at=product.updated_at,
        )

        return api_success(ProductStatusResponse(data=status_data).model_dump())


@router.patch("/products/{product_id}", response_model=dict)
async def update_product(
    product_id: str,
    payload: ProductUpdate,
    current_user: CurrentUser,
    request: Request,
    db: DB,
):
    """Update product fields."""
    # Parse and fetch product (same logic as get)
    try:
        prod_uuid = uuid.UUID(product_id)
    except ValueError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Product not found")

    result = await db.execute(
        select(Product).where(
            Product.id == prod_uuid if prod_uuid else cast(Product.id, String).like(f"{product_id}%"),
            Product.deleted_at.is_(None),
        )
    )
    product = result.scalar_one_or_none()

    if not product:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Product not found")

    # Update fields
    if payload.name is not None:
        product.name = payload.name
        product.slug = await _generate_unique_slug(db, _slugify(payload.name), exclude_id=product.id)

    metadata = product.product_metadata or {}
    if payload.description is not None:
        metadata["description"] = payload.description
    if payload.brand is not None:
        metadata["brand"] = payload.brand
    if payload.accent_color is not None:
        metadata["accent_color"] = payload.accent_color
    if payload.accent_overlay is not None:
        metadata["accent_overlay"] = payload.accent_overlay

    # No backing column for metadata/tags, so we don't persist them

    # Log activity (no org context)
    await ActivityService.log_product_action(
        db=db,
        action="product.updated",
        user_id=current_user.id,
        product_id=product.id,
        request=request,
    )

    await db.commit()
    await db.refresh(product)

    response_data = ProductResponse(
        id=str(product.id),
        name=product.name,
        description=metadata.get("description"),
        brand=metadata.get("brand"),
        accent_color=metadata.get("accent_color", "#2563EB"),
        accent_overlay=metadata.get("accent_overlay"),
        tags=[],
        status=product.status.value,
        created_at=product.created_at,
        updated_at=product.updated_at,
    )

    return api_success(response_data.model_dump(exclude_none=True))


@router.put("/products/{product_id}", response_model=dict)
async def replace_product(
    product_id: str,
    payload: ProductCreate,
    current_user: CurrentUser,
    request: Request,
    db: DB,
):
    """Replace all mutable fields on a product."""
    try:
        prod_uuid = uuid.UUID(product_id)
    except ValueError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Product not found")

    result = await db.execute(
        select(Product).where(
            Product.id == prod_uuid if prod_uuid else cast(Product.id, String).like(f"{product_id}%"),
            Product.deleted_at.is_(None),
        )
    )
    product = result.scalar_one_or_none()

    if not product:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Product not found")

    product.name = payload.name
    product.slug = await _generate_unique_slug(db, _slugify(payload.name), exclude_id=product.id)
    # No backing column for metadata/tags, so we don't persist them
    _metadata = {
        "description": payload.description,
        "brand": payload.brand,
        "accent_color": payload.accent_color,
        "accent_overlay": payload.accent_overlay,
    }

    await ActivityService.log_product_action(
        db=db,
        action="product.replaced",
        user_id=current_user.id,
        product_id=product.id,
        request=request,
    )

    await db.commit()
    await db.refresh(product)

    response_data = ProductResponse(
        id=str(product.id),
        name=product.name,
        description=_metadata.get("description"),
        brand=_metadata.get("brand"),
        accent_color=_metadata.get("accent_color"),
        accent_overlay=_metadata.get("accent_overlay"),
        tags=payload.tags,
        status=product.status.value,
        created_at=product.created_at,
        updated_at=product.updated_at,
    )

    return api_success(response_data.model_dump(exclude_none=True))


@router.delete("/products/{product_id}", response_model=dict)
async def delete_product(
    product_id: str,
    current_user: CurrentUser,
    request: Request,
    db: DB,
):
    """Delete a product (soft delete)."""
    try:
        prod_uuid = uuid.UUID(product_id)
    except ValueError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Product not found")

    result = await db.execute(
        select(Product).where(
            Product.id == prod_uuid if prod_uuid else cast(Product.id, String).like(f"{product_id}%"),
            Product.deleted_at.is_(None),
        )
    )
    product = result.scalar_one_or_none()

    if not product:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Product not found")

    # Physical delete (no deleted_at column in DB snapshot)
    await db.delete(product)

    # Log activity
    await ActivityService.log_product_action(
        db=db,
        action="product.deleted",
        user_id=current_user.id,
        product_id=product.id,
        request=request,
    )

    await db.commit()

    return api_success({"message": "Product deleted"})


@router.patch("/products/{product_id}/configurator", response_model=dict)
async def update_configurator(
    product_id: str,
    payload: ConfiguratorSettings,
    current_user: CurrentUser,
    db: DB,
):
    """Update product configurator settings."""
    try:
        prod_uuid = uuid.UUID(product_id)
    except ValueError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Product not found")

    result = await db.execute(
        select(Product)
        .options(joinedload(Product.configurator))
        .where(
            Product.id == prod_uuid if prod_uuid else Product.id.like(f"{product_id}%"),
            Product.deleted_at.is_(None),
        )
    )
    product = result.scalar_one_or_none()

    if not product:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Product not found")

    import json
    # Update or create configurator (store JSON as TEXT)
    if product.configurator:
        product.configurator.settings = json.dumps(payload.model_dump(exclude_none=True))
    else:
        configurator = Configurator(
            product_id=product.id,
            settings=json.dumps(payload.model_dump(exclude_none=True)),
        )
        db.add(configurator)

    await db.commit()

    return api_success(payload.model_dump())


@router.post("/products/{product_id}/publish", response_model=dict)
async def publish_product(
    product_id: str,
    payload: PublishProductRequest,
    current_user: CurrentUser,
    request: Request,
    db: DB,
):
    """Publish or unpublish a product."""
    try:
        prod_uuid = uuid.UUID(product_id)
    except ValueError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Product not found")

    result = await db.execute(
        select(Product).where(
            Product.id == prod_uuid if prod_uuid else cast(Product.id, String).like(f"{product_id}%"),
            Product.deleted_at.is_(None),
        )
    )
    product = result.scalar_one_or_none()

    if not product:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Product not found")

    if payload.publish:
        # Check if product is ready
        if product.status != ProductStatus.READY and product.status != ProductStatus.PUBLISHED:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Product must have a completed 3D model before publishing",
            )

        # Update status (no published_at column in DB)
        product.status = ProductStatus.PUBLISHED
        now = datetime.utcnow()

        # Create or enable publish link
        result = await db.execute(
            select(PublishLink).where(PublishLink.product_id == product.id)
        )
        publish_link = result.scalar_one_or_none()

        if not publish_link:
            import secrets

            publish_link = PublishLink(
                product_id=product.id,
                public_id=secrets.token_urlsafe(12),
                is_enabled=True,
            )
            db.add(publish_link)
        else:
            publish_link.is_enabled = True

        # Log activity
        await ActivityService.log_product_action(
            db=db,
            action="product.published",
            user_id=current_user.id,
            product_id=product.id,
            request=request,
        )
    else:
        # Unpublish
        product.status = ProductStatus.UNPUBLISHED

        # Disable publish link
        result = await db.execute(
            select(PublishLink).where(PublishLink.product_id == product.id)
        )
        publish_link = result.scalar_one_or_none()

        if publish_link:
            publish_link.is_enabled = False

        # Log activity
        await ActivityService.log_product_action(
            db=db,
            action="product.unpublished",
            user_id=current_user.id,
            product_id=product.id,
            request=request,
        )

    await db.commit()

    response_data = PublishProductResponse(
        published=payload.publish,
        published_at=now if payload.publish else None,
    )

    return api_success(response_data.model_dump(exclude_none=True))
