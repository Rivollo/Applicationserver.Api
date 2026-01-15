"""Product link management routes."""

import uuid
import logging

from fastapi import APIRouter, Depends, HTTPException, status

from app.api.deps import CurrentUser, DB, get_current_user
from app.schemas.product_links import (
    BulkProductLinkCreate,
    ProductLinkCreate,
    ProductLinkUpdate,
)
from app.services.product_link_service import ProductLinkService
from app.utils.envelopes import api_success
from app.utils.exceptions import NotFoundException, ValidationException

logger = logging.getLogger(__name__)

router = APIRouter(
    tags=["product-links"],
    dependencies=[Depends(get_current_user)],
)


@router.get("/product-link-types", response_model=dict)
async def get_link_types(
    current_user: CurrentUser,
    db: DB,
):
    """Get all active product link types for dropdown."""
    try:
        link_types = await ProductLinkService.get_link_types(db)
        return api_success(link_types)

    except (NotFoundException, ValidationException):
        raise

    except Exception:
        logger.error("Unexpected error while fetching link types", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while processing the request",
        )


@router.post(
    "/products/{product_id}/links",
    response_model=dict,
    status_code=status.HTTP_201_CREATED,
)
async def create_product_links(
    product_id: str,
    payload: BulkProductLinkCreate,
    current_user: CurrentUser,
    db: DB,
):
    """
    Create product links for a product.

    """
    try:
        prod_uuid = uuid.UUID(product_id)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid productId format",
        )

    try:
        # Convert Pydantic models to dicts and explicitly convert HttpUrl to str
        links_data = []
        for link in payload.links:
            link_dict = link.model_dump(mode='python')

            if 'link' in link_dict and link_dict['link'] is not None:
                link_dict['link'] = str(link_dict['link'])
            links_data.append(link_dict)
        
        result = await ProductLinkService.create_product_links(
            db=db,
            product_id=prod_uuid,
            links_data=links_data,
            user_id=current_user.id,
        )
        return api_success(result)

    except (NotFoundException, ValidationException):
        raise

    except Exception:
        logger.error("Unexpected error while creating product links", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while processing the request",
        )


@router.get("/products/{product_id}/links", response_model=dict)
async def get_product_links(
    product_id: str,
    current_user: CurrentUser,
    db: DB,
):
    """Get all active links for a product."""
    try:
        prod_uuid = uuid.UUID(product_id)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid productId format",
        )

    try:
        links = await ProductLinkService.get_product_links(db, prod_uuid)
        return api_success(links)

    except (NotFoundException, ValidationException):
        raise

    except Exception:
        logger.error("Unexpected error while fetching product links", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while processing the request",
        )


@router.patch("/links/{link_id}", response_model=dict)
async def update_link(
    link_id: int,
    payload: ProductLinkUpdate,
    current_user: CurrentUser,
    db: DB,
):
    """Update a product link."""
    try:
        # Convert HttpUrl to string if present
        link_url = str(payload.link) if payload.link is not None else None
        
        result = await ProductLinkService.update_link(
            db=db,
            link_id=link_id,
            name=payload.name,
            link_url=link_url,
            description=payload.description,
            link_type=payload.link_type,
            user_id=current_user.id,
        )
        return api_success(result)

    except (NotFoundException, ValidationException):
        raise

    except Exception:
        logger.error("Unexpected error while updating product link", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while processing the request",
        )


@router.delete("/links/{link_id}", response_model=dict)
async def delete_link(
    link_id: int,
    current_user: CurrentUser,
    db: DB,
):
    """Soft delete a product link."""
    try:
        result = await ProductLinkService.delete_link(
            db=db,
            link_id=link_id,
            user_id=current_user.id,
        )
        return api_success(result)

    except NotFoundException:
        raise

    except Exception:
        logger.error("Unexpected error while deleting product link", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while processing the request",
        )
