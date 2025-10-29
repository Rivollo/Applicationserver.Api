"""Licensing and subscription management service."""

import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.models import LicenseAssignment, Plan, Subscription, User


class LicensingService:
    """Service for managing subscriptions and license enforcement."""

    @staticmethod
    async def get_active_license(db: AsyncSession, user_id: uuid.UUID) -> Optional[LicenseAssignment]:
        """Get active license for a user."""
        result = await db.execute(
            select(LicenseAssignment)
            .where(
                LicenseAssignment.user_id == user_id,
                LicenseAssignment.status == "active",
            )
            .order_by(LicenseAssignment.created_at.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def check_quota(
        db: AsyncSession,
        user_id: uuid.UUID,
        quota_key: str,
        increment: int = 1,
    ) -> tuple[bool, Optional[dict]]:
        """
        Check if user has quota available.

        Returns (allowed, limits_info)
        """
        license = await LicensingService.get_active_license(db, user_id)

        if not license:
            # No active license - deny
            return False, None

        limits = license.limits or {}
        usage = license.usage_counters or {}

        # Get limit for this quota
        limit = limits.get(quota_key)
        if limit is None:
            # No limit set - allow
            return True, limits

        current_usage = usage.get(quota_key, 0)

        if current_usage + increment > limit:
            # Quota exceeded
            return False, {"limit": limit, "current": current_usage, "quota": quota_key}

        return True, limits

    @staticmethod
    async def increment_usage(
        db: AsyncSession,
        user_id: uuid.UUID,
        quota_key: str,
        increment: int = 1,
    ) -> bool:
        """Increment usage counter for a user's license."""
        license = await LicensingService.get_active_license(db, user_id)

        if not license:
            return False

        usage = license.usage_counters or {}
        usage[quota_key] = usage.get(quota_key, 0) + increment
        license.usage_counters = usage

        await db.commit()
        return True

    @staticmethod
    async def get_user_plan_code(db: AsyncSession, user_id: uuid.UUID) -> str:
        """Get the plan code for a user (free, pro, enterprise)."""
        license = await LicensingService.get_active_license(db, user_id)

        if not license:
            return "free"

        # Get subscription and plan
        result = await db.execute(
            select(Plan)
            .join(Subscription)
            .where(Subscription.id == license.subscription_id)
        )
        plan = result.scalar_one_or_none()

        return plan.code if plan else "free"

    @staticmethod
    async def create_free_plan_license(
        db: AsyncSession,
        user: User,
    ) -> LicenseAssignment:
        """Create a free plan license for a new user."""
        # Get or create free plan
        result = await db.execute(select(Plan).where(Plan.code == "free"))
        free_plan = result.scalar_one_or_none()

        if not free_plan:
            free_plan = Plan(
                code="free",
                name="Free",
                quotas={
                    "max_products": 2,
                    "max_ai_credits_month": 5,
                    "max_public_views": 1000,
                },
            )
            db.add(free_plan)
            await db.flush()

        # Create subscription
        subscription = Subscription(
            user_id=user.id,
            plan_id=free_plan.id,
            status="active",
            seats_purchased=1,
        )
        db.add(subscription)
        await db.flush()

        # Create license assignment
        license = LicenseAssignment(
            subscription_id=subscription.id,
            user_id=user.id,
            status="active",
            limits=free_plan.quotas,
            usage_counters={},
        )
        db.add(license)
        await db.commit()

        return license
