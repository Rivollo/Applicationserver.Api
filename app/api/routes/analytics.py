"""Analytics and reporting routes."""

import uuid
from datetime import date, datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Query
from sqlalchemy import func, select

from app.api.deps import CurrentUser, DB
from app.models.models import AnalyticsDailyProduct, AnalyticsEvent, Product
from app.schemas.analytics import (
    AnalyticsOverviewResponse,
    AnalyticsSummary,
    AnalyticsTimeSeries,
    TimeSeriesPoint,
)
from app.utils.envelopes import api_success

router = APIRouter(tags=["analytics"])


# Org-free analytics; no org scoping


@router.get("/analytics/overview", response_model=dict)
async def get_analytics_overview(
    current_user: CurrentUser,
    db: DB,
    start_date: Optional[date] = Query(None, alias="startDate"),
    end_date: Optional[date] = Query(None, alias="endDate"),
    product_id: Optional[str] = Query(None, alias="productId"),
):
    """Get analytics overview with summary, time series, and top products."""
    # No org checks

    # Default to last 30 days if not specified
    if not end_date:
        end_date = date.today()
    if not start_date:
        start_date = end_date - timedelta(days=30)

    # Build base query
    query = select(
        func.sum(AnalyticsDailyProduct.views).label("total_views"),
        func.sum(AnalyticsDailyProduct.engaged).label("total_engaged"),
        func.sum(AnalyticsDailyProduct.adds_from_3d).label("total_adds"),
    ).where(
        AnalyticsDailyProduct.day >= start_date,
        AnalyticsDailyProduct.day <= end_date,
    )

    # Filter by product if specified
    if product_id:
        # Parse product ID
        try:
            prod_uuid = uuid.UUID(product_id)
        except ValueError:
            prod_uuid = None

        if prod_uuid:
            query = query.where(AnalyticsDailyProduct.product_id == prod_uuid)

    # Execute summary query
    result = await db.execute(query)
    row = result.first()

    total_views = int(row.total_views) if row.total_views else 0
    total_engaged = int(row.total_engaged) if row.total_engaged else 0
    total_adds = int(row.total_adds) if row.total_adds else 0

    # Get time series data (views by day)
    ts_query = select(
        AnalyticsDailyProduct.day,
        func.sum(AnalyticsDailyProduct.views).label("daily_views"),
    ).where(
        AnalyticsDailyProduct.day >= start_date,
        AnalyticsDailyProduct.day <= end_date,
    )

    if product_id and prod_uuid:
        ts_query = ts_query.where(AnalyticsDailyProduct.product_id == prod_uuid)

    ts_query = ts_query.group_by(AnalyticsDailyProduct.day).order_by(AnalyticsDailyProduct.day)

    ts_result = await db.execute(ts_query)
    ts_rows = ts_result.all()

    time_series_data = [
        TimeSeriesPoint(date=row.day, value=int(row.daily_views))
        for row in ts_rows
    ]

    # Get top products (top 5 by views)
    top_query = (
        select(
            Product.id,
            Product.name,
            func.sum(AnalyticsDailyProduct.views).label("product_views"),
        )
        .join(AnalyticsDailyProduct, Product.id == AnalyticsDailyProduct.product_id)
        .where(
            AnalyticsDailyProduct.day >= start_date,
            AnalyticsDailyProduct.day <= end_date,
            Product.deleted_at.is_(None),
        )
        .group_by(Product.id, Product.name)
        .order_by(func.sum(AnalyticsDailyProduct.views).desc())
        .limit(5)
    )

    top_result = await db.execute(top_query)
    top_rows = top_result.all()

    top_products = [
        {
            "id": str(row.id),
            "name": row.name,
            "views": int(row.product_views),
        }
        for row in top_rows
    ]

    response_data = AnalyticsOverviewResponse(
        summary=AnalyticsSummary(
            views=total_views,
            engagedViews=total_engaged,
            addsFrom3D=total_adds,
        ),
        timeSeries=[
            AnalyticsTimeSeries(
                label="Views",
                data=time_series_data,
            )
        ],
        topProducts=top_products,
    )

    return api_success(response_data.model_dump())


@router.post("/analytics/events", response_model=dict)
async def track_event(
    event_data: dict,
    db: DB,
):
    """Track an analytics event (public endpoint for embedded products)."""
    # Create analytics event
    event = AnalyticsEvent(
        org_id=event_data.get("org_id"),
        product_id=event_data.get("product_id"),
        publish_link_id=event_data.get("publish_link_id"),
        session_id=event_data.get("session_id"),
        event_type=event_data.get("event_type", "view"),
        user_agent=event_data.get("user_agent"),
        ip_hash=event_data.get("ip_hash"),
        payload=event_data.get("payload", {}),
    )

    db.add(event)
    await db.commit()

    return api_success({"tracked": True})
