"""Product management routes."""

import io
import logging
import secrets
import uuid
from datetime import datetime
from typing import Optional

import asyncio
from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Request, UploadFile, status
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from pydantic import BaseModel
from sqlalchemy import and_, desc, func, or_, select, cast, String, insert, update
from sqlalchemy.ext.asyncio import async_sessionmaker
from sqlalchemy.orm import joinedload

from app.api.deps import CurrentUser, DB, get_current_user
from app.core.config import settings
from app.models.models import (
    AssetStatic,
    Background,
    BackgroundType,
    Configurator,
    CurrencyType,
    Hotspot,
    Product,
    ProductAsset,
    ProductAssetMapping,
    ProductLink,
    ProductStatus,
    PublishLink,
)
from app.schemas.products import (
    BackgroundResponse,
    BackgroundsResponse,
    BackgroundTypeResponse,
    BackgroundTypesResponse,
    ConfiguratorSettings,
    CurrencyTypeResponse,
    CurrencyTypesResponse,
    ProductAssetsData,
    ProductAssetsResponse,
    ProductCreate,
    ProductDetailsUpdate,
    ProductImageItem,
    ProductLinkCreate,
    ProductLinkResponse,
    ProductLinksResponse,
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

router = APIRouter(tags=["products"], dependencies=[Depends(get_current_user)])
basic_auth_scheme = HTTPBasic()


def verify_public_basic_auth(credentials: HTTPBasicCredentials = Depends(basic_auth_scheme)) -> None:
    """Verify HTTP Basic auth credentials for public endpoints."""
    correct_username = secrets.compare_digest(credentials.username, settings.PUBLIC_API_USERNAME)
    correct_password = secrets.compare_digest(credentials.password, settings.PUBLIC_API_PASSWORD)
    if not (correct_username and correct_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication credentials",
            headers={"WWW-Authenticate": "Basic"},
        )


public_router = APIRouter(
    tags=["products"],
    dependencies=[Depends(verify_public_basic_auth)],
)


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
    try:
        # Parse product ID
        try:
            prod_uuid = uuid.UUID(product_id)
        except ValueError:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Product not found")

        # Fetch product with configurator and background
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

        # Fetch background data if background_type exists (stores background ID as integer)
        background_data = None
        if product.background_type:
            background_result = await db.execute(
                select(Background).where(Background.id == product.background_type)
            )
            background = background_result.scalar_one_or_none()
            if background:
                background_data = BackgroundResponse(
                    id=background.id,
                    background_type_id=background.background_type_id,
                    name=background.name,
                    description=background.description,
                    isactive=background.isactive,
                    image=background.image,
                    created_by=str(background.created_by) if background.created_by else None,
                    created_date=background.created_date,
                    updated_by=str(background.updated_by) if background.updated_by else None,
                    updated_date=background.updated_date,
                )

        # Fetch product links
        links_query = select(ProductLink).where(
            ProductLink.productid == str(product.id),
            ProductLink.isactive == True,
        ).order_by(ProductLink.created_date.desc())
        
        links_result = await db.execute(links_query)
        product_links = links_result.scalars().all()
        
        # Filter out None values and ensure we only process valid ProductLink instances
        valid_links = [link for link in product_links if link is not None and isinstance(link, ProductLink)]
        
        links_data = [
            ProductLinkResponse(
                id=link.id,
                productid=str(link.productid),
                name=link.name,
                link=link.link,
                description=link.description,
                isactive=link.isactive,
                created_by=str(link.created_by) if link.created_by else None,
                created_date=link.created_date,
                updated_by=str(link.updated_by) if link.updated_by else None,
                updated_date=link.updated_date,
            )
            for link in valid_links
        ]

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

        response_dict = response_data.model_dump(exclude_none=True)
        if background_data:
            response_dict["background"] = background_data.model_dump(exclude_none=True)
        if links_data:
            response_dict["links"] = [link.model_dump(exclude_none=True) for link in links_data]

        return api_success(response_dict)
    except HTTPException:
        raise
    except Exception as e:
        import traceback
        logger = logging.getLogger(__name__)
        error_msg = f"Error getting product: {str(e)}\n{traceback.format_exc()}"
        logger.error(error_msg)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get product: {str(e)}",
        )


async def _build_product_assets_response(product_id: str, db: DB) -> dict:
    """Shared builder for product assets response."""
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

    # Fetch background data if background_type exists
    background_data = None
    if product.background_type:
        background_result = await db.execute(
            select(Background).where(Background.id == product.background_type)
        )
        background = background_result.scalar_one_or_none()
        if background:
            # Also fetch background type
            background_type_result = await db.execute(
                select(BackgroundType).where(BackgroundType.id == background.background_type_id)
            )
            background_type = background_type_result.scalar_one_or_none()
            
            background_data = {
                "id": background.id,
                "background_type_id": background.background_type_id,
                "background_type": {
                    "id": background_type.id if background_type else None,
                    "name": background_type.name if background_type else None,
                    "description": background_type.description if background_type else None,
                } if background_type else None,
                "name": background.name,
                "description": background.description,
                "isactive": background.isactive,
                "image": background.image,
                "created_by": str(background.created_by) if background.created_by else None,
                "created_date": background.created_date,
                "updated_by": str(background.updated_by) if background.updated_by else None,
                "updated_date": background.updated_date,
            }

    # Fetch product links from tbl_product_links using raw SQL query
    try:
        from sqlalchemy import text
        sql_query = text("""
            SELECT id, productid, "name", link, description, isactive, 
                   created_by, created_date, updated_by, updated_date
            FROM public.tbl_product_links
            WHERE productid = :product_id AND isactive = true
            ORDER BY created_date DESC
        """)
        result = await db.execute(sql_query, {"product_id": str(product_uuid)})
        rows = result.fetchall()
        
        links_data = None
        if rows:
            # Filter for active links
            active_rows = [row for row in rows if row[5] is True or (row[5] is not None and bool(row[5]))]
            if active_rows:
                links_data = [
                    {
                        "id": row[0] if row[0] is not None else None,
                        "productid": str(row[1]) if row[1] else None,
                        "name": row[2] if row[2] else None,
                        "link": row[3] if row[3] else None,
                        "description": row[4] if row[4] else None,
                        "isactive": bool(row[5]) if row[5] is not None else False,
                        "created_by": str(row[6]) if row[6] else None,
                        "created_date": row[7] if row[7] else None,
                        "updated_by": str(row[8]) if row[8] else None,
                        "updated_date": row[9] if row[9] else None,
                    }
                    for row in active_rows
                ]
            # If no active links but we have rows, include all for debugging
            elif rows:
                links_data = [
                    {
                        "id": row[0] if row[0] is not None else None,
                        "productid": str(row[1]) if row[1] else None,
                        "name": row[2] if row[2] else None,
                        "link": row[3] if row[3] else None,
                        "description": row[4] if row[4] else None,
                        "isactive": bool(row[5]) if row[5] is not None else False,
                        "created_by": str(row[6]) if row[6] else None,
                        "created_date": row[7] if row[7] else None,
                        "updated_by": str(row[8]) if row[8] else None,
                        "updated_date": row[9] if row[9] else None,
                    }
                    for row in rows
                ]
    except Exception as e:
        import traceback
        logger = logging.getLogger(__name__)
        logger.error(f"Error fetching product links: {str(e)}\n{traceback.format_exc()}")
        links_data = None

    # Build response
    data = ProductAssetsData(
        id=str(product.id),
        name=product.name,
        description=product.description,
        price=float(product.price) if product.price else None,
        currency_type=product.currency_type,
        status=product.status.value,
        created_at=product.created_at,
        updated_at=product.updated_at,
        meshurl=meshurl,
        images=images,
        background=background_data,
        links=links_data,
    )

    return ProductAssetsResponse(data=data).model_dump()


@router.get("/products/{product_id}/assets", response_model=dict)
async def get_product_assets(
    product_id: str,
    current_user: CurrentUser,
    db: DB,
):
    """Return all assets associated with a product (authenticated)."""
    return api_success(await _build_product_assets_response(product_id, db))


@public_router.get("/public/products/{product_id}/assets", response_model=dict)
async def get_product_assets_public(
    product_id: str,
    db: DB,
):
    """Public (unauthenticated) endpoint that returns product assets."""
    return api_success(await _build_product_assets_response(product_id, db))


@router.get("/products/user/{userId}/products", response_model=dict)
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
            Product.description,
            Product.price,
            Product.currency_type,
            Product.background_type,
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
        product_id, name, product_status, description, price, currency_type, background_type, created_date, updated_date, image, asset_type, asset_type_id = row
        items.append(
            ProductWithPrimaryAsset(
                id=str(product_id),
                name=name,
                status=product_status.value,
                image=image,
                asset_type=asset_type,
                asset_type_id=asset_type_id,
                description=description,
                price=float(price) if price is not None else None,
                currency_type=currency_type,
                background_type=background_type,
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


@router.get("/currencytypes", response_model=dict)
async def get_currency_types(db: DB):
    """Get all currency types."""
    query = select(CurrencyType).order_by(CurrencyType.created_date.desc())
    
    result = await db.execute(query)
    currency_types = result.scalars().all()

    items = [
        CurrencyTypeResponse(
            id=ct.id,
            code=ct.code,
            name=ct.name,
            symbol=ct.symbol,
            description=ct.description,
            isactive=ct.isactive,
            created_by=str(ct.created_by) if ct.created_by else None,
            created_date=ct.created_date,
            updated_by=str(ct.updated_by) if ct.updated_by else None,
            updated_date=ct.updated_date,
        )
        for ct in currency_types
    ]

    return api_success(CurrencyTypesResponse(items=items).model_dump())


@router.get("/backgroundtypes", response_model=dict)
async def get_background_types(db: DB):
    """Get all background types."""
    query = select(BackgroundType).order_by(BackgroundType.created_date.desc())
    
    result = await db.execute(query)
    background_types = result.scalars().all()

    items = [
        BackgroundTypeResponse(
            id=bt.id,
            name=bt.name,
            description=bt.description,
            isactive=bt.isactive,
            created_by=str(bt.created_by) if bt.created_by else None,
            created_date=bt.created_date,
            updated_by=str(bt.updated_by) if bt.updated_by else None,
            updated_date=bt.updated_date,
        )
        for bt in background_types
    ]

    return api_success(BackgroundTypesResponse(items=items).model_dump())


@router.get("/backgrounds/{backgroundid}", response_model=dict)
async def get_background(backgroundid: int, db: DB):
    """Get background by ID."""
    result = await db.execute(
        select(Background).where(Background.id == backgroundid)
    )
    background = result.scalar_one_or_none()

    if not background:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Background not found",
        )

    background_data = BackgroundResponse(
        id=background.id,
        background_type_id=background.background_type_id,
        name=background.name,
        description=background.description,
        isactive=background.isactive,
        image=background.image,
        created_by=str(background.created_by) if background.created_by else None,
        created_date=background.created_date,
        updated_by=str(background.updated_by) if background.updated_by else None,
        updated_date=background.updated_date,
    )

    return api_success(background_data.model_dump(exclude_none=True))


@router.put("/products/{product_id}/details", response_model=dict)
async def update_product_details(
    product_id: str,
    payload: ProductDetailsUpdate,
    request: Request,
    db: DB,
):
    """Insert or update product details including name, description, price, currency_type, background, and links."""
    try:
        # Parse product ID
        try:
            prod_uuid = uuid.UUID(product_id)
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid productId format. Expected UUID string.",
            )

        # Get product
        product = await db.get(Product, prod_uuid)
        if not product:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Product not found.",
            )

        # Update product fields
        if payload.name is not None:
            if product is None:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Product not found.",
                )
            product.name = payload.name
            # Update slug if name changes
            product.slug = await _generate_unique_slug(db, _slugify(payload.name), exclude_id=product.id)

        if payload.description is not None:
            product.description = payload.description

        if payload.price is not None:
            # Store price as integer (BigInteger in database)
            product.price = int(payload.price) if payload.price else None

        if payload.currency_type is not None:
            # Verify currency type exists
            currency_result = await db.execute(
                select(CurrencyType).where(CurrencyType.id == payload.currency_type)
            )
            currency = currency_result.scalar_one_or_none()
            if not currency:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Currency type with ID {payload.currency_type} not found.",
                )
            # Store currency type ID as integer
            product.currency_type = payload.currency_type

        if payload.backgroundid is not None:
            # Verify background exists
            background_result = await db.execute(
                select(Background).where(Background.id == payload.backgroundid)
            )
            background = background_result.scalar_one_or_none()
            if not background:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Background with ID {payload.backgroundid} not found.",
                )
            # Store background ID in background_type column as integer
            product.background_type = payload.backgroundid

        # Get a valid user ID for audit fields (use product's created_by or a default UUID if None)
        audit_user_id = product.created_by
        if audit_user_id is None:
            # Generate a default UUID if product.created_by is None
            audit_user_id = uuid.uuid4()
        
        # Update product updated fields
        product.updated_by = audit_user_id
        product.updated_date = datetime.utcnow()

        # Handle links - replace all existing active links with new ones
        if payload.links is not None:
            try:
                # Ensure product is not None before accessing product.id
                if product is None:
                    raise HTTPException(
                        status_code=status.HTTP_404_NOT_FOUND,
                        detail="Product not found.",
                    )
                
                product_id = product.id
                
                # Mark all existing active links as inactive using raw SQL update to avoid ORM issues
                update_stmt = (
                    update(ProductLink.__table__)
                    .where(
                        ProductLink.productid == str(product_id),
                        ProductLink.isactive == True,
                    )
                    .values(
                        isactive=False,
                        updated_by=audit_user_id,
                        updated_date=datetime.utcnow(),
                    )
                )
                await db.execute(update_stmt)
                
                # Flush changes but don't commit yet
                await db.flush()
                
                # Create new links using individual raw SQL inserts with flush (not commit) to avoid batching
                # Insert each link individually to prevent SQLAlchemy from batching them
                # Ensure product is not None before accessing product.id
                if product is None:
                    raise HTTPException(
                        status_code=status.HTTP_404_NOT_FOUND,
                        detail="Product not found.",
                    )
                
                product_id = product.id
                for link_data in payload.links:
                    stmt = insert(ProductLink.__table__).values(
                        productid=str(product_id),
                        name=link_data.name,
                        link=link_data.link,
                        description=link_data.description,
                        isactive=True,
                        created_by=audit_user_id,
                        created_date=datetime.utcnow(),
                        updated_by=audit_user_id,
                        updated_date=datetime.utcnow(),
                    )
                    await db.execute(stmt)
                    # Flush each insert to avoid batching, but don't commit yet
                    await db.flush()
                
                # Commit all changes together (product updates, link deactivations, and new links)
                await db.commit()
                await db.refresh(product)
            except Exception as e:
                import traceback
                logger = logging.getLogger(__name__)
                logger.error(f"Error updating product links: {str(e)}\n{traceback.format_exc()}")
                await db.rollback()
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail=f"Failed to update product links: {str(e)}",
                )
        else:
            # No links to update, just commit product changes
            await db.commit()
            await db.refresh(product)

        # Fetch updated product with all related data (same as get_product)
        # Fetch background data if background_type exists (stores background ID as integer)
        background_data = None
        if product is not None and product.background_type:
            background_result = await db.execute(
                select(Background).where(Background.id == product.background_type)
            )
            background = background_result.scalar_one_or_none()
            if background:
                background_data = BackgroundResponse(
                    id=background.id,
                    background_type_id=background.background_type_id,
                    name=background.name,
                    description=background.description,
                    isactive=background.isactive,
                    image=background.image,
                    created_by=str(background.created_by) if background.created_by else None,
                    created_date=background.created_date,
                    updated_by=str(background.updated_by) if background.updated_by else None,
                    updated_date=background.updated_date,
                )

        # Fetch product links - ensure product is not None
        if product is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Product not found after update.",
            )
        
        product_id_for_query = str(product.id)
        links_query = select(ProductLink).where(
            ProductLink.productid == product_id_for_query,
            ProductLink.isactive == True,
        ).order_by(ProductLink.created_date.desc())
        
        links_result = await db.execute(links_query)
        product_links = links_result.scalars().all()
        
        # Filter out None values and ensure we only process valid ProductLink instances
        valid_links = [link for link in product_links if link is not None and isinstance(link, ProductLink)]
        
        links_data = [
            ProductLinkResponse(
                id=link.id,
                productid=str(link.productid),
                name=link.name,
                link=link.link,
                description=link.description,
                isactive=link.isactive,
                created_by=str(link.created_by) if link.created_by else None,
                created_date=link.created_date,
                updated_by=str(link.updated_by) if link.updated_by else None,
                updated_date=link.updated_date,
            )
            for link in valid_links
        ]

        # Ensure product is not None before accessing its attributes
        if product is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Product not found after update.",
            )
        
        response_data = {
            "id": str(product.id),
            "name": product.name,
            "description": product.description,
            "price": float(product.price) if product.price else None,  # Convert integer to float
            "currency_type": product.currency_type,
            "background_type": product.background_type,  # Background ID as integer
            "backgroundid": product.background_type,  # Same as background_type for backward compatibility
            "status": product.status.value,
            "created_at": product.created_at,
            "updated_at": product.updated_at,
        }

        if background_data:
            response_data["background"] = background_data.model_dump(exclude_none=True)
        if links_data:
            response_data["links"] = [link.model_dump(exclude_none=True) for link in links_data]

        return api_success(response_data)
    except HTTPException:
        # Re-raise HTTP exceptions as-is
        raise
    except Exception as e:
        import traceback
        logger = logging.getLogger(__name__)
        error_msg = f"Error updating product details: {str(e)}\n{traceback.format_exc()}"
        logger.error(error_msg)
        try:
            await db.rollback()
        except:
            pass
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to update product details: {str(e)}",
        )
