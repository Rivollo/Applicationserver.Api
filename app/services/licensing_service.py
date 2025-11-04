"""Licensing and subscription management service."""

import json
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
            .order_by(LicenseAssignment.created_date.desc())
            .limit(1)
        )
        license_obj = result.scalar_one_or_none()
        # Parse TEXT fields to dicts for backward compatibility
        if license_obj:
            license_obj._limits_dict = json.loads(license_obj.limits) if license_obj.limits else {}
            license_obj._usage_dict = json.loads(license_obj.usage_counters) if license_obj.usage_counters else {}
        return license_obj

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

        limits = getattr(license, "_limits_dict", None)
        if limits is None:
            limits = json.loads(license.limits) if license.limits else {}
            license._limits_dict = limits

        usage = getattr(license, "_usage_dict", None)
        if usage is None:
            usage = json.loads(license.usage_counters) if license.usage_counters else {}
            license._usage_dict = usage

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

        usage = getattr(license, "_usage_dict", None)
        if usage is None:
            usage = json.loads(license.usage_counters) if license.usage_counters else {}
        else:
            # Create shallow copy to avoid mutating cached dict without serialization
            usage = dict(usage)
        usage[quota_key] = usage.get(quota_key, 0) + increment
        license.usage_counters = json.dumps(usage)
        license._usage_dict = usage

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
            quotas_dict = {
                "max_products": 2,
                "max_ai_credits_month": 5,
                "max_public_views": 1000,
            }
            free_plan = Plan(
                code="free",
                name="Free",
                quotas=json.dumps(quotas_dict),  # Serialize to JSON string
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

        # Parse quotas from TEXT field
        quotas_dict = json.loads(free_plan.quotas) if free_plan.quotas else {}

        # Create license assignment
        license = LicenseAssignment(
            subscription_id=subscription.id,
            user_id=user.id,
            status="active",
            limits=json.dumps(quotas_dict),  # Serialize to JSON string
            usage_counters=json.dumps({}),  # Serialize to JSON string
        )
        db.add(license)
        await db.commit()

        return license
