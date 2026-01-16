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
        logger.info("Processing get link types request")
        link_types = await ProductLinkService.get_link_types(db)
        logger.info("Get link types request processed successfully")
        return api_success(link_types)
    except Exception as e:
        error_message = f"An error occurred: {str(e)}"
        logger.error("A system failure occurred in get link types", exc_info=True)
        return {"error": error_message}


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
    """Create product links for a product."""
    try:
        prod_uuid = uuid.UUID(product_id)
    except ValueError:
        return {"error": "Invalid productId format"}

    try:
        logger.info(f"Processing create product links request for product {prod_uuid}")
        
        # Convert HttpUrl to string
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
        logger.info(f"Create product links request processed successfully")
        return api_success(result)
    except Exception as e:
        error_message = f"An error occurred: {str(e)}"
        logger.error("A system failure occurred in create product links", exc_info=True)
        return {"error": error_message}


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
        return {"error": "Invalid productId format"}

    try:
        logger.info(f"Processing get product links request for product {prod_uuid}")
        links = await ProductLinkService.get_product_links(db, prod_uuid)
        logger.info("Get product links request processed successfully")
        return api_success(links)
    except Exception as e:
        error_message = f"An error occurred: {str(e)}"
        logger.error("A system failure occurred in get product links", exc_info=True)
        return {"error": error_message}


@router.patch("/links/{link_id}", response_model=dict)
async def update_link(
    link_id: int,
    payload: ProductLinkUpdate,
    current_user: CurrentUser,
    db: DB,
):
    """Update a product link."""
    try:
        logger.info(f"Processing update link request for link {link_id}")
        
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
        logger.info("Update link request processed successfully")
        return api_success(result)
    except Exception as e:
        error_message = f"An error occurred: {str(e)}"
        logger.error("A system failure occurred in update link", exc_info=True)
        return {"error": error_message}


@router.delete("/links/{link_id}", response_model=dict)
async def delete_link(
    link_id: int,
    current_user: CurrentUser,
    db: DB,
):
    """Soft delete a product link."""
    try:
        logger.info(f"Processing delete link request for link {link_id}")
        result = await ProductLinkService.delete_link(
            db=db,
            link_id=link_id,
            user_id=current_user.id,
        )
        logger.info("Delete link request processed successfully")
        return api_success(result)
    except Exception as e:
        error_message = f"An error occurred: {str(e)}"
        logger.error("A system failure occurred in delete link", exc_info=True)
        return {"error": error_message}
