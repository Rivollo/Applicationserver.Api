"""Hotspot-specific schemas."""

import uuid
from typing import Optional

from pydantic import Field
from pydantic import BaseModel

from app.schemas.products import HotspotCreate
from app.schemas.products import HotspotPosition



class HotspotUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    position: Optional[HotspotPosition] = None
    hotspot_type: Optional[int] = None
    text_font: Optional[str] = None
    text_color: Optional[str] = None
    bg_color: Optional[str] = None
    action_type: Optional[str] = None
    action_payload: Optional[dict] = None


HotspotUpdate.model_rebuild()