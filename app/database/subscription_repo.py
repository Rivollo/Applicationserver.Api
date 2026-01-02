"""Repository layer for subscription-related database operations.

This module contains ONLY database access logic - no business rules.
Repository functions fetch data from the database and return raw models or primitive values.

Key Concepts:
- Subscription: A user's subscription to a plan (links user to a plan)
- Plan: A subscription tier (Free, Pro, Enterprise) with defined features
- LicenseAssignment: Tracks active license with usage limits and counters
"""

import uuid
from typing import Optional, Tuple

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.models import LicenseAssignment, Plan, Product, Subscription


class SubscriptionRepository:
    """Repository for subscription database operations."""

    @staticmethod
    async def get_subscription_and_plan(
        db: AsyncSession, subscription_id: uuid.UUID
    ) -> Optional[Tuple[Subscription, Plan]]:
        """
        Fetch a subscription and its associated plan from the database.

        Args:
            db: Database session
            subscription_id: ID of the subscription to fetch

        Returns:
            Tuple of (Subscription, Plan) if found, None otherwise
        """
        result = await db.execute(
            select(Subscription, Plan)
            .join(Plan, Subscription.plan_id == Plan.id)
            .where(Subscription.id == subscription_id)
        )
        row = result.first()
        return row if row else None

    @staticmethod
    async def get_user_product_count(db: AsyncSession, user_id: uuid.UUID) -> int:
        """
        Count the number of non-deleted products created by a user.

        This is used for quota calculation - products are counted separately
        from other usage counters stored in LicenseAssignment.

        Args:
            db: Database session
            user_id: ID of the user whose products to count

        Returns:
            Number of products (integer)
        """
        result = await db.execute(
            select(Product).where(
                Product.created_by == user_id,
                Product.deleted_at.is_(None),
            )
        )
        products = result.scalars().all()
        return len(products)

    @staticmethod
    async def get_plan_by_code(db: AsyncSession, plan_code: str) -> Optional[Plan]:
        """
        Fetch a plan by its code (e.g., "free", "pro", "enterprise").

        Args:
            db: Database session
            plan_code: Code of the plan to fetch

        Returns:
            Plan model if found, None otherwise
        """
        result = await db.execute(select(Plan).where(Plan.code == plan_code))
        return result.scalar_one_or_none()

