"""Plan model - Subscription plan definitions.

This module contains the Plan model which defines subscription tiers
(Free, Pro, Enterprise) with their features and quotas.
"""

from datetime import datetime
from typing import TYPE_CHECKING, Optional

from sqlalchemy import String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base
from app.models.models import AuditMixin, UUIDMixin

if TYPE_CHECKING:
    from app.models.subscription import Subscription


class Plan(UUIDMixin, AuditMixin, Base):
    """Subscription plan model (Free, Pro, Enterprise).

    Plans define the features and quotas available to users.
    Each plan has a code (e.g., "free", "pro", "enterprise") and quotas stored as JSON.
    """

    __tablename__ = "tbl_mstr_plans"

    code: Mapped[str] = mapped_column(String, unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String, nullable=False)
    # quotas is TEXT in database, storing JSON as string
    quotas: Mapped[Optional[str]] = mapped_column(Text)

    # Property for backward compatibility
    @property
    def created_at(self) -> datetime:
        return self.created_date

    subscriptions: Mapped[list["Subscription"]] = relationship("Subscription", back_populates="plan")

