"""Notification service for user notifications."""

import uuid
from typing import Any, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.models import Notification, NotificationChannel, UserNotificationPreference


class NotificationService:
    """Service for managing user notifications."""

    @staticmethod
    async def create_notification(
        db: AsyncSession,
        user_id: uuid.UUID,
        notification_type: str,
        title: str,
        body: str,
        data: Optional[dict[str, Any]] = None,
        channel: NotificationChannel = NotificationChannel.IN_APP,
    ) -> Notification:
        """Create a notification for a user."""
        # Check if user has muted this notification type
        prefs = await NotificationService.get_user_preferences(db, user_id, notification_type)

        if prefs and prefs.muted:
            # User has muted this notification type - skip
            return None

        notification = Notification(
            user_id=user_id,
            type=notification_type,
            title=title,
            body=body,
            data=data or {},
            channel=channel,
        )

        db.add(notification)
        await db.commit()
        await db.refresh(notification)

        return notification

    @staticmethod
    async def get_user_preferences(
        db: AsyncSession,
        user_id: uuid.UUID,
        notification_type: str,
    ) -> Optional[UserNotificationPreference]:
        """Get user notification preferences for a specific type."""
        result = await db.execute(
            select(UserNotificationPreference).where(
                UserNotificationPreference.user_id == user_id,
                UserNotificationPreference.notification_type == notification_type,
            )
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def notify_job_completed(
        db: AsyncSession,
        user_id: uuid.UUID,
        product_name: str,
        job_id: uuid.UUID,
    ) -> Optional[Notification]:
        """Notify user that a 3D job has completed."""
        return await NotificationService.create_notification(
            db=db,
            user_id=user_id,
            notification_type="job.completed",
            title="3D Model Ready",
            body=f"Your 3D model for '{product_name}' is ready to view and configure.",
            data={"job_id": str(job_id), "product_name": product_name},
        )

    @staticmethod
    async def notify_quota_warning(
        db: AsyncSession,
        user_id: uuid.UUID,
        quota_type: str,
        percentage: int,
    ) -> Optional[Notification]:
        """Notify user about quota usage warning."""
        return await NotificationService.create_notification(
            db=db,
            user_id=user_id,
            notification_type="quota.warning",
            title="Quota Warning",
            body=f"You've used {percentage}% of your {quota_type} quota.",
            data={"quota_type": quota_type, "percentage": percentage},
        )
