"""Dashboard overview routes."""

import uuid
from datetime import date, timedelta
from typing import Optional

from fastapi import APIRouter
from sqlalchemy import desc, func, select

from app.api.deps import CurrentUser, DB
from app.models.models import AnalyticsDailyProduct, OrgMember, Product, ProductStatus
from app.schemas.dashboard import DashboardOverviewResponse, InsightCard, ResumeCard
from app.utils.envelopes import api_success

router = APIRouter(tags=["dashboard"])


async def _get_user_org_id(db: DB, user_id: uuid.UUID) -> Optional[uuid.UUID]:
    """Get the user's primary organization ID."""
    result = await db.execute(
        select(OrgMember.org_id).where(OrgMember.user_id == user_id).limit(1)
    )
    return result.scalar_one_or_none()


@router.get("/dashboard/overview", response_model=dict)
async def get_dashboard_overview(
    current_user: CurrentUser,
    db: DB,
):
    """Get dashboard overview with resume cards and insights."""
    org_id = await _get_user_org_id(db, current_user.id)

    resume_cards = []
    insights = []

    if org_id:
        # Get recent products (processing or draft) for resume cards
        result = await db.execute(
            select(Product)
            .where(
                Product.org_id == org_id,
                Product.deleted_at.is_(None),
                Product.status.in_([ProductStatus.DRAFT, ProductStatus.PROCESSING]),
            )
            .order_by(desc(Product.updated_at))
            .limit(3)
        )
        recent_products = result.scalars().all()

        for product in recent_products:
            # Calculate progress based on status
            progress = None
            if product.status == ProductStatus.PROCESSING:
                progress = product.product_metadata.get("processing_progress", 50)
            elif product.status == ProductStatus.DRAFT:
                progress = 0

            resume_cards.append(
                ResumeCard(
                    productId=f"prod-{str(product.id)[:8]}",
                    productName=product.name,
                    status=product.status.value,
                    thumbnailUrl=None,
                    progress=progress,
                )
            )

        # Generate insights
        today = date.today()
        last_7_days_start = today - timedelta(days=7)
        last_14_days_start = today - timedelta(days=14)

        # Total views (last 7 days)
        views_query = select(func.sum(AnalyticsDailyProduct.views)).where(
            AnalyticsDailyProduct.org_id == org_id,
            AnalyticsDailyProduct.day >= last_7_days_start,
        )
        views_result = await db.execute(views_query)
        total_views = int(views_result.scalar() or 0)

        # Previous period views (7 days before)
        prev_views_query = select(func.sum(AnalyticsDailyProduct.views)).where(
            AnalyticsDailyProduct.org_id == org_id,
            AnalyticsDailyProduct.day >= last_14_days_start,
            AnalyticsDailyProduct.day < last_7_days_start,
        )
        prev_views_result = await db.execute(prev_views_query)
        prev_views = int(prev_views_result.scalar() or 0)

        # Calculate change
        views_change = "+0%"
        if prev_views > 0:
            change_pct = ((total_views - prev_views) / prev_views) * 100
            views_change = f"+{change_pct:.0f}%" if change_pct > 0 else f"{change_pct:.0f}%"

        insights.append(
            InsightCard(
                type="views",
                title="Total Views",
                value=f"{total_views:,}",
                change=views_change,
                icon="eye",
            )
        )

        # Engagement rate
        engaged_query = select(func.sum(AnalyticsDailyProduct.engaged)).where(
            AnalyticsDailyProduct.org_id == org_id,
            AnalyticsDailyProduct.day >= last_7_days_start,
        )
        engaged_result = await db.execute(engaged_query)
        total_engaged = int(engaged_result.scalar() or 0)

        engagement_rate = 0
        if total_views > 0:
            engagement_rate = (total_engaged / total_views) * 100

        insights.append(
            InsightCard(
                type="engagement",
                title="Engagement Rate",
                value=f"{engagement_rate:.1f}%",
                change=None,
                icon="activity",
            )
        )

        # Top performing product
        top_product_query = (
            select(
                Product.name,
                func.sum(AnalyticsDailyProduct.views).label("product_views"),
            )
            .join(AnalyticsDailyProduct, Product.id == AnalyticsDailyProduct.product_id)
            .where(
                AnalyticsDailyProduct.org_id == org_id,
                AnalyticsDailyProduct.day >= last_7_days_start,
                Product.deleted_at.is_(None),
            )
            .group_by(Product.name)
            .order_by(func.sum(AnalyticsDailyProduct.views).desc())
            .limit(1)
        )
        top_product_result = await db.execute(top_product_query)
        top_product_row = top_product_result.first()

        if top_product_row:
            insights.append(
                InsightCard(
                    type="topProduct",
                    title="Top Product",
                    value=top_product_row.name,
                    change=f"{int(top_product_row.product_views):,} views",
                    icon="star",
                )
            )

    response_data = DashboardOverviewResponse(
        resume=[card.model_dump() for card in resume_cards],
        insights=[insight.model_dump() for insight in insights],
    )

    return api_success(response_data.model_dump())
