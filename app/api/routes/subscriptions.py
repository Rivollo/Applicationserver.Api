"""Subscription and plan management routes."""

import json
from datetime import datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Depends
from sqlalchemy import select

from app.api.deps import CurrentUser, DB, OptionalUser
from app.models.models import LicenseAssignment, Plan, Product, Subscription
from app.schemas.subscriptions import (
    PlanFeature,
    Plan as PlanSchema,
    QuotaInfo,
    QuotaUsage,
    SubscriptionMe,
    TrialInfo,
)
from app.services.licensing_service import LicensingService
from app.utils.envelopes import api_success

router = APIRouter(tags=["subscriptions"])


@router.get("/subscriptions/me", response_model=dict)
async def get_my_subscription(
    current_user: CurrentUser,
    db: DB,
):
    """Get current user's subscription and quota information."""
    # Get active license
    license_assignment = await LicensingService.get_active_license(db, current_user.id)

    if not license_assignment:
        # Return default free plan info
        return api_success(
            SubscriptionMe(
                plan="free",
                trial=TrialInfo(active=False, daysRemaining=0, startedAt=None),
                quotas={
                    "aiCredits": QuotaUsage(included=5, purchased=0, used=0).model_dump(),
                    "publicViews": QuotaUsage(included=1000, purchased=0, used=0).model_dump(),
                    "products": QuotaInfo(used=0, limit=2).model_dump(),
                    "galleries": QuotaInfo(used=0, limit=0).model_dump(),
                },
            ).model_dump()
        )

    # Get subscription and plan
    result = await db.execute(
        select(Subscription, Plan)
        .join(Plan, Subscription.plan_id == Plan.id)
        .where(Subscription.id == license_assignment.subscription_id)
    )
    row = result.first()

    if not row:
        return api_success(
            SubscriptionMe(
                plan="free",
                trial=TrialInfo(active=False, daysRemaining=0, startedAt=None),
                quotas={},
            ).model_dump()
        )

    subscription, plan = row

    # Check if trial is active
    trial_active = False
    days_remaining = 0
    trial_started = None

    if subscription.trial_end_at:
        now = datetime.utcnow()
        if subscription.trial_end_at > now:
            trial_active = True
            days_remaining = max(0, (subscription.trial_end_at - now).days)
            # Calculate trial start (7 days before end)
            trial_started = subscription.trial_end_at - timedelta(days=7)

    # Get usage counters
    limits = getattr(license_assignment, "_limits_dict", None)
    if limits is None:
        limits = json.loads(license_assignment.limits) if license_assignment.limits else {}
        license_assignment._limits_dict = limits  # cache for downstream calls

    usage = getattr(license_assignment, "_usage_dict", None)
    if usage is None:
        usage = json.loads(license_assignment.usage_counters) if license_assignment.usage_counters else {}
        license_assignment._usage_dict = usage

    # Count products
    result = await db.execute(
        select(Product).where(
            Product.created_by == current_user.id,
            Product.deleted_at.is_(None),
        )
    )
    product_count = len(result.scalars().all())

    # Build quotas
    quotas = {
        "aiCredits": QuotaUsage(
            included=limits.get("max_ai_credits_month", 5),
            purchased=0,
            used=usage.get("ai_credits", 0),
        ).model_dump(),
        "publicViews": QuotaUsage(
            included=limits.get("max_public_views", 1000),
            purchased=0,
            used=usage.get("public_views", 0),
        ).model_dump(),
        "products": QuotaInfo(
            used=product_count,
            limit=limits.get("max_products"),
        ).model_dump(),
        "galleries": QuotaInfo(
            used=usage.get("galleries", 0),
            limit=limits.get("max_galleries"),
        ).model_dump(),
    }

    response_data = SubscriptionMe(
        plan=plan.code,
        trial=TrialInfo(
            active=trial_active,
            daysRemaining=days_remaining,
            startedAt=trial_started,
        ),
        quotas=quotas,
    )

    return api_success(response_data.model_dump())


@router.get("/subscriptions/plans", response_model=dict)
async def list_plans(
    current_user: OptionalUser = None,
):
    """List all available subscription plans (public endpoint)."""
    plans_data = [
        PlanSchema(
            name="Free",
            priceINR=0,
            description="Perfect for trying out Rivollo",
            features=[
                PlanFeature(label="2 product listings", available=True),
                PlanFeature(label="5 AI credits per month", available=True),
                PlanFeature(label="1,000 public views", available=True),
                PlanFeature(label="Basic analytics", available=True),
                PlanFeature(label="Galleries", available=False),
                PlanFeature(label="Advanced analytics", available=False),
                PlanFeature(label="Custom branding", available=False),
            ],
            featured=False,
        ),
        PlanSchema(
            name="Pro",
            priceINR=1999,
            description="Scale with galleries, credits, views, and advanced analytics",
            features=[
                PlanFeature(label="50 product listings", available=True),
                PlanFeature(label="50 AI credits per month", available=True),
                PlanFeature(label="25,000 public views", available=True),
                PlanFeature(label="10 galleries", available=True),
                PlanFeature(label="Advanced analytics", available=True),
                PlanFeature(label="Priority support", available=True),
                PlanFeature(label="Custom branding", available=True),
            ],
            featured=True,
        ),
        PlanSchema(
            name="Enterprise",
            priceINR=0,
            description="Unlimited everything with dedicated support. Contact sales for pricing.",
            features=[
                PlanFeature(label="Unlimited products", available=True),
                PlanFeature(label="Unlimited AI credits", available=True),
                PlanFeature(label="Unlimited public views", available=True),
                PlanFeature(label="Unlimited galleries", available=True),
                PlanFeature(label="Advanced analytics", available=True),
                PlanFeature(label="Custom branding", available=True),
                PlanFeature(label="Dedicated account manager", available=True),
                PlanFeature(label="SLA guarantee", available=True),
            ],
            featured=False,
        ),
    ]

    return api_success([p.model_dump() for p in plans_data])
