"""Seed database with initial data (plans, demo users)."""

import asyncio
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker

from app.core.config import settings
from app.models.models import Plan, User, Organization, OrgMember, Subscription, LicenseAssignment, OrgRole
from app.core.security import hash_password


async def seed_plans(session: AsyncSession) -> None:
    """Create or update subscription plans."""
    plans_data = [
        {
            "code": "free",
            "name": "Free",
            "quotas": {
                "max_products": 2,
                "max_ai_credits_month": 5,
                "max_public_views": 1000,
                "max_galleries": 0,
            },
        },
        {
            "code": "pro",
            "name": "Pro",
            "quotas": {
                "max_products": 50,
                "max_ai_credits_month": 50,
                "max_public_views": 25000,
                "max_galleries": 10,
            },
        },
        {
            "code": "enterprise",
            "name": "Enterprise",
            "quotas": {
                "max_products": None,  # Unlimited
                "max_ai_credits_month": None,
                "max_public_views": None,
                "max_galleries": None,
            },
        },
    ]

    for plan_data in plans_data:
        result = await session.execute(select(Plan).where(Plan.code == plan_data["code"]))
        existing_plan = result.scalar_one_or_none()

        if existing_plan:
            # Update existing plan
            existing_plan.name = plan_data["name"]
            existing_plan.quotas = plan_data["quotas"]
            print(f"✓ Updated plan: {plan_data['name']}")
        else:
            # Create new plan
            plan = Plan(**plan_data)
            session.add(plan)
            print(f"✓ Created plan: {plan_data['name']}")

    await session.commit()


async def seed_demo_user(session: AsyncSession) -> None:
    """Create a demo user with free plan."""
    demo_email = "demo@rivollo.com"

    result = await session.execute(select(User).where(User.email == demo_email))
    existing_user = result.scalar_one_or_none()

    if existing_user:
        print(f"✓ Demo user already exists: {demo_email}")
        return

    # Create demo user
    demo_user = User(
        email=demo_email,
        password_hash=hash_password("demo123456"),
        name="Demo User",
    )
    session.add(demo_user)
    await session.flush()

    # Create organization
    demo_org = Organization(
        name="Demo Organization",
        slug=f"demo-org-{str(demo_user.id)[:8]}",
        branding={},
    )
    session.add(demo_org)
    await session.flush()

    # Add user as org owner
    org_member = OrgMember(
        org_id=demo_org.id,
        user_id=demo_user.id,
        role=OrgRole.OWNER,
    )
    session.add(org_member)

    # Get free plan
    result = await session.execute(select(Plan).where(Plan.code == "free"))
    free_plan = result.scalar_one_or_none()

    if free_plan:
        # Create subscription
        subscription = Subscription(
            user_id=demo_user.id,
            plan_id=free_plan.id,
            status="active",
            seats_purchased=1,
        )
        session.add(subscription)
        await session.flush()

        # Create license
        license_assignment = LicenseAssignment(
            subscription_id=subscription.id,
            user_id=demo_user.id,
            status="active",
            limits=free_plan.quotas,
            usage_counters={},
        )
        session.add(license_assignment)

    await session.commit()

    print(f"✓ Created demo user: {demo_email} (password: demo123456)")


async def main() -> None:
    """Run all seed operations."""
    print("🌱 Seeding database...")

    # Ensure async URL (handle common provider variants)
    database_url = settings.DATABASE_URL
    if database_url.startswith("postgres://"):
        database_url = database_url.replace("postgres://", "postgresql+asyncpg://", 1)
    elif database_url.startswith("postgresql://"):
        database_url = database_url.replace("postgresql://", "postgresql+asyncpg://", 1)
    elif database_url.startswith("postgresql+psycopg2://"):
        database_url = database_url.replace("postgresql+psycopg2://", "postgresql+asyncpg://", 1)
    elif database_url.startswith("postgresql+psycopg://"):
        database_url = database_url.replace("postgresql+psycopg://", "postgresql+asyncpg://", 1)

    engine = create_async_engine(database_url, echo=False)
    async_session = async_sessionmaker(engine, expire_on_commit=False)

    async with async_session() as session:
        await seed_plans(session)
        await seed_demo_user(session)

    await engine.dispose()

    print("✅ Database seeding completed!")


if __name__ == "__main__":
    asyncio.run(main())
