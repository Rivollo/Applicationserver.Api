"""Activity logging service for audit trail."""

import uuid
from typing import Any, Optional

from fastapi import Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.models import ActivityLog


class ActivityService:
    """Service for logging user actions."""

    @staticmethod
    async def log_activity(
        db: AsyncSession,
        action: str,
        user_id: Optional[uuid.UUID] = None,
        org_id: Optional[uuid.UUID] = None,
        target_type: Optional[str] = None,
        target_id: Optional[str] = None,
        metadata: Optional[dict[str, Any]] = None,
        request: Optional[Request] = None,
    ) -> ActivityLog:
        """Log an activity/action."""
        ip_address = None
        user_agent = None

        if request:
            # Extract IP from request headers
            ip_address = request.headers.get("x-forwarded-for")
            if ip_address:
                # Get first IP if multiple
                ip_address = ip_address.split(",")[0].strip()
            else:
                ip_address = request.client.host if request.client else None

            user_agent = request.headers.get("user-agent")

        metadata_value: Optional[str]
        if metadata is None:
            metadata_value = None
        else:
            import json

            metadata_value = json.dumps(metadata)

        activity = ActivityLog(
            actor_user_id=user_id,
            org_id=org_id,
            action=action,
            target_type=target_type,
            target_id=target_id,
            ip_address=ip_address,
            user_agent=user_agent,
            activity_metadata=metadata_value,
        )

        db.add(activity)
        await db.commit()
        await db.refresh(activity)

        return activity

    @staticmethod
    async def log_auth_action(
        db: AsyncSession,
        action: str,
        user_id: uuid.UUID,
        request: Optional[Request] = None,
        metadata: Optional[dict[str, Any]] = None,
    ) -> ActivityLog:
        """Log authentication-related actions (login, signup, etc)."""
        return await ActivityService.log_activity(
            db=db,
            action=action,
            user_id=user_id,
            target_type="user",
            target_id=str(user_id),
            metadata=metadata,
            request=request,
        )

    @staticmethod
    async def log_product_action(
        db: AsyncSession,
        action: str,
        user_id: uuid.UUID,
        product_id: uuid.UUID,
        org_id: Optional[uuid.UUID] = None,
        request: Optional[Request] = None,
        metadata: Optional[dict[str, Any]] = None,
    ) -> ActivityLog:
        """Log product-related actions (create, update, delete, publish)."""
        return await ActivityService.log_activity(
            db=db,
            action=action,
            user_id=user_id,
            org_id=org_id,
            target_type="product",
            target_id=str(product_id),
            metadata=metadata,
            request=request,
        )
