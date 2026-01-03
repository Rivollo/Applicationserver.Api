"""Repository layer for support operations - abstracts data access."""

from typing import Optional
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.models import Support
from app.queries.support_queries import SupportQueries


class SupportRepository:
    """Repository layer for support data access operations."""

    def __init__(self, db: AsyncSession):
        """Initialize repository with database session."""
        self.db = db

    async def create(
        self,
        fullname: str,
        comment: Optional[str],
        user_id: Optional[UUID],
    ) -> Support:
        """Create a new support entry."""
        return await SupportQueries.create_support_entry(
            db=self.db,
            fullname=fullname,
            comment=comment,
            created_by=user_id,
        )

    async def get_by_id(self, support_id: int) -> Optional[Support]:
        """Get support entry by ID."""
        return await SupportQueries.get_support_by_id(db=self.db, support_id=support_id)

    async def get_by_user_id(self, user_id: UUID, limit: int = 100) -> list[Support]:
        """Get all support entries for a user."""
        return await SupportQueries.get_support_by_user_id(
            db=self.db, user_id=user_id, limit=limit
        )

