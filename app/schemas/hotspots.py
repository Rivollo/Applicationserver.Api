"""Hotspot-specific schemas."""

import uuid
from typing import Optional

from pydantic import Field

from app.schemas.products import HotspotCreate


class HotspotUpsertRequest(HotspotCreate):
    """
    Request schema for creating or updating a hotspot.

    Extends HotspotCreate with product_id and optional hotspot_id.
    - If hotspot_id is absent → creates a new hotspot.
    - If hotspot_id is present → updates the existing hotspot.
    """

    product_id: uuid.UUID = Field(
        ...,
        description="UUID of the product to attach the hotspot to (required).",
    )
    hotspot_id: Optional[uuid.UUID] = Field(
        None,
        description="UUID of the hotspot to update. If omitted, a new hotspot is created.",
    )
