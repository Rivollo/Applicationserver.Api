"""Product management routes."""

import uuid
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, HTTPException, Query, Request, status
from sqlalchemy import desc, func, or_, select
from sqlalchemy.orm import joinedload

from app.api.deps import CurrentUser, DB
from app.models.models import (
    Configurator,
    Hotspot,
    OrgMember,
    Product,
    ProductStatus,
    PublishLink,
)
from app.schemas.products import (
    ConfiguratorSettings,
    ProductCreate,
    ProductListResponse,
    ProductResponse,
    ProductUpdate,
    PublishProductRequest,
    PublishProductResponse,
)
from app.services.activity_service import ActivityService
from app.services.licensing_service import LicensingService
from app.utils.envelopes import api_success

router = APIRouter(tags=["products"])


def _slugify(text: str) -> str:
    """Convert text to URL-friendly slug."""
    import re

    text = text.lower().strip()
    text = re.sub(r"[^\w\s-]", "", text)
    text = re.sub(r"[-\s]+", "-", text)
    return text[:100]


async def _get_user_org_id(db: DB, user_id: uuid.UUID) -> Optional[uuid.UUID]:
    """Get the user's primary organization ID."""
    result = await db.execute(
        select(OrgMember.org_id).where(OrgMember.user_id == user_id).limit(1)
    )
    org_id = result.scalar_one_or_none()
    return org_id


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
    org_id = await _get_user_org_id(db, current_user.id)

    if not org_id:
        return api_success({"items": [], "meta": {"page": 1, "pageSize": page_size, "total": 0, "totalPages": 0}})

    # Base query
    query = select(Product).where(
        Product.org_id == org_id,
        Product.deleted_at.is_(None),
    )

    # Apply filters
    if q:
        search_pattern = f"%{q}%"
        query = query.where(
            or_(
                Product.name.ilike(search_pattern),
                Product.product_metadata["description"].astext.ilike(search_pattern),
            )
        )

    if status_filter:
        query = query.where(Product.status == status_filter)

    if tags:
        tag_list = [t.strip() for t in tags.split(",")]
        query = query.where(Product.tags.overlap(tag_list))

    # Count total
    count_query = select(func.count()).select_from(query.subquery())
    total_result = await db.execute(count_query)
    total = total_result.scalar() or 0

    # Apply sorting
    if sort.startswith("-"):
        sort_field = sort[1:]
        order_col = desc(getattr(Product, sort_field, Product.created_at))
    else:
        order_col = getattr(Product, sort, Product.created_at)

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
            id=f"prod-{str(p.id)[:8]}",
            name=p.name,
            description=p.product_metadata.get("description"),
            brand=p.product_metadata.get("brand"),
            accent_color=p.product_metadata.get("accent_color", "#2563EB"),
            accent_overlay=p.product_metadata.get("accent_overlay"),
            tags=list(p.tags) if p.tags else [],
            status=p.status.value,
            created_at=p.created_at,
            updated_at=p.updated_at,
        )
        for p in products
    ]

    total_pages = (total + page_size - 1) // page_size

    return api_success(
        {
            "items": [item.model_dump() for item in items],
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
    org_id = await _get_user_org_id(db, current_user.id)

    if not org_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="User must belong to an organization",
        )

    # Check quota
    allowed, quota_info = await LicensingService.check_quota(db, current_user.id, "max_products")

    if not allowed:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Product limit exceeded. Upgrade your plan to create more products.",
        )

    # Generate slug
    slug = _slugify(payload.name)

    # Create product
    product = Product(
        org_id=org_id,
        name=payload.name,
        slug=slug,
        status=ProductStatus.DRAFT,
        created_by=current_user.id,
        tags=payload.tags,
        metadata={
            "description": payload.description,
            "brand": payload.brand,
            "accent_color": payload.accent_color,
            "accent_overlay": payload.accent_overlay,
        },
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
        org_id=org_id,
        product_id=product.id,
        request=request,
    )

    await db.commit()
    await db.refresh(product)

    response_data = ProductResponse(
        id=f"prod-{str(product.id)[:8]}",
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

    return api_success(response_data.model_dump())


@router.get("/products/{product_id}", response_model=dict)
async def get_product(
    product_id: str,
    current_user: CurrentUser,
    db: DB,
):
    """Get product by ID."""
    # Parse product ID
    try:
        # Handle both "prod-xxx" and UUID formats
        if product_id.startswith("prod-"):
            product_id = product_id[5:]

        prod_uuid = uuid.UUID(product_id) if len(product_id) > 8 else None
    except ValueError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Product not found")

    org_id = await _get_user_org_id(db, current_user.id)

    # Fetch product with configurator
    result = await db.execute(
        select(Product)
        .options(joinedload(Product.configurator))
        .where(
            Product.id == prod_uuid if prod_uuid else Product.id.like(f"{product_id}%"),
            Product.org_id == org_id,
            Product.deleted_at.is_(None),
        )
    )
    product = result.scalar_one_or_none()

    if not product:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Product not found")

    # Build configurator settings if exists
    configurator_data = None
    if product.configurator:
        configurator_data = ConfiguratorSettings(**product.configurator.settings)

    response_data = ProductResponse(
        id=f"prod-{str(product.id)[:8]}",
        name=product.name,
        description=product.product_metadata.get("description"),
        brand=product.product_metadata.get("brand"),
        accent_color=product.product_metadata.get("accent_color", "#2563EB"),
        accent_overlay=product.product_metadata.get("accent_overlay"),
        tags=list(product.tags) if product.tags else [],
        status=product.status.value,
        created_at=product.created_at,
        updated_at=product.updated_at,
        configurator=configurator_data,
    )

    return api_success(response_data.model_dump())


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
        if product_id.startswith("prod-"):
            product_id = product_id[5:]
        prod_uuid = uuid.UUID(product_id) if len(product_id) > 8 else None
    except ValueError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Product not found")

    org_id = await _get_user_org_id(db, current_user.id)

    result = await db.execute(
        select(Product).where(
            Product.id == prod_uuid if prod_uuid else Product.id.like(f"{product_id}%"),
            Product.org_id == org_id,
            Product.deleted_at.is_(None),
        )
    )
    product = result.scalar_one_or_none()

    if not product:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Product not found")

    # Update fields
    if payload.name is not None:
        product.name = payload.name
        product.slug = _slugify(payload.name)

    metadata = product.product_metadata or {}
    if payload.description is not None:
        metadata["description"] = payload.description
    if payload.brand is not None:
        metadata["brand"] = payload.brand
    if payload.accent_color is not None:
        metadata["accent_color"] = payload.accent_color
    if payload.accent_overlay is not None:
        metadata["accent_overlay"] = payload.accent_overlay

    product.product_metadata = metadata

    if payload.tags is not None:
        product.tags = payload.tags

    # Log activity
    await ActivityService.log_product_action(
        db=db,
        action="product.updated",
        user_id=current_user.id,
        org_id=org_id,
        product_id=product.id,
        request=request,
    )

    await db.commit()
    await db.refresh(product)

    response_data = ProductResponse(
        id=f"prod-{str(product.id)[:8]}",
        name=product.name,
        description=metadata.get("description"),
        brand=metadata.get("brand"),
        accent_color=metadata.get("accent_color", "#2563EB"),
        accent_overlay=metadata.get("accent_overlay"),
        tags=list(product.tags) if product.tags else [],
        status=product.status.value,
        created_at=product.created_at,
        updated_at=product.updated_at,
    )

    return api_success(response_data.model_dump())


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
        if product_id.startswith("prod-"):
            product_id = product_id[5:]
        prod_uuid = uuid.UUID(product_id) if len(product_id) > 8 else None
    except ValueError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Product not found")

    org_id = await _get_user_org_id(db, current_user.id)

    result = await db.execute(
        select(Product).where(
            Product.id == prod_uuid if prod_uuid else Product.id.like(f"{product_id}%"),
            Product.org_id == org_id,
            Product.deleted_at.is_(None),
        )
    )
    product = result.scalar_one_or_none()

    if not product:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Product not found")

    product.name = payload.name
    product.slug = _slugify(payload.name)
    product.tags = payload.tags
    product.product_metadata = {
        "description": payload.description,
        "brand": payload.brand,
        "accent_color": payload.accent_color,
        "accent_overlay": payload.accent_overlay,
    }

    await ActivityService.log_product_action(
        db=db,
        action="product.replaced",
        user_id=current_user.id,
        org_id=org_id,
        product_id=product.id,
        request=request,
    )

    await db.commit()
    await db.refresh(product)

    response_data = ProductResponse(
        id=f"prod-{str(product.id)[:8]}",
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

    return api_success(response_data.model_dump())


@router.delete("/products/{product_id}", response_model=dict)
async def delete_product(
    product_id: str,
    current_user: CurrentUser,
    request: Request,
    db: DB,
):
    """Delete a product (soft delete)."""
    try:
        if product_id.startswith("prod-"):
            product_id = product_id[5:]
        prod_uuid = uuid.UUID(product_id) if len(product_id) > 8 else None
    except ValueError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Product not found")

    org_id = await _get_user_org_id(db, current_user.id)

    result = await db.execute(
        select(Product).where(
            Product.id == prod_uuid if prod_uuid else Product.id.like(f"{product_id}%"),
            Product.org_id == org_id,
            Product.deleted_at.is_(None),
        )
    )
    product = result.scalar_one_or_none()

    if not product:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Product not found")

    # Soft delete
    product.deleted_at = datetime.utcnow()

    # Log activity
    await ActivityService.log_product_action(
        db=db,
        action="product.deleted",
        user_id=current_user.id,
        org_id=org_id,
        product_id=product.id,
        request=request,
    )

    await db.commit()

    return api_success({"message": "Product deleted successfully"})


@router.patch("/products/{product_id}/configurator", response_model=dict)
async def update_configurator(
    product_id: str,
    payload: ConfiguratorSettings,
    current_user: CurrentUser,
    db: DB,
):
    """Update product configurator settings."""
    try:
        if product_id.startswith("prod-"):
            product_id = product_id[5:]
        prod_uuid = uuid.UUID(product_id) if len(product_id) > 8 else None
    except ValueError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Product not found")

    org_id = await _get_user_org_id(db, current_user.id)

    result = await db.execute(
        select(Product)
        .options(joinedload(Product.configurator))
        .where(
            Product.id == prod_uuid if prod_uuid else Product.id.like(f"{product_id}%"),
            Product.org_id == org_id,
            Product.deleted_at.is_(None),
        )
    )
    product = result.scalar_one_or_none()

    if not product:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Product not found")

    # Update or create configurator
    if product.configurator:
        product.configurator.settings = payload.model_dump(exclude_none=True)
    else:
        configurator = Configurator(
            product_id=product.id,
            settings=payload.model_dump(exclude_none=True),
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
        if product_id.startswith("prod-"):
            product_id = product_id[5:]
        prod_uuid = uuid.UUID(product_id) if len(product_id) > 8 else None
    except ValueError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Product not found")

    org_id = await _get_user_org_id(db, current_user.id)

    result = await db.execute(
        select(Product).where(
            Product.id == prod_uuid if prod_uuid else Product.id.like(f"{product_id}%"),
            Product.org_id == org_id,
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

        # Update status
        product.status = ProductStatus.PUBLISHED
        product.published_at = datetime.utcnow()

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
            org_id=org_id,
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
            org_id=org_id,
            product_id=product.id,
            request=request,
        )

    await db.commit()

    response_data = PublishProductResponse(
        published=payload.publish,
        published_at=product.published_at,
    )

    return api_success(response_data.model_dump())
