"""Query layer for support operations - contains raw database queries."""

from typing import Optional
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.models import Support


class SupportQueries:
    """Query layer for support table operations."""

    @staticmethod
    async def create_support_entry(
        db: AsyncSession,
        fullname: str,
        comment: Optional[str],
        created_by: Optional[UUID],
    ) -> Support:
        """Create a new support entry in the database."""
        support_entry = Support(
            fullname=fullname,
            comment=comment,
            created_by=created_by,
            isactive=True,
        )
        db.add(support_entry)
        await db.flush()
        await db.refresh(support_entry)
        await db.commit()
        return support_entry

    @staticmethod
    async def get_support_by_id(db: AsyncSession, support_id: int) -> Optional[Support]:
        """Get a support entry by ID."""
        stmt = select(Support).where(Support.id == support_id, Support.isactive == True)
        result = await db.execute(stmt)
        return result.scalar_one_or_none()

    @staticmethod
    async def get_support_by_user_id(
        db: AsyncSession, user_id: UUID, limit: int = 100
    ) -> list[Support]:
        """Get all support entries for a specific user."""
        stmt = (
            select(Support)
            .where(Support.created_by == user_id, Support.isactive == True)
            .order_by(Support.created_date.desc())
            .limit(limit)
        )
        result = await db.execute(stmt)
        return list(result.scalars().all())

