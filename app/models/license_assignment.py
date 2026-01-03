"""LicenseAssignment model - Active license with usage tracking.

This module contains the LicenseAssignment model which tracks active licenses
for users, including usage limits and current usage counters.
"""

import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import Enum, ForeignKey, Index, Text, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import TIMESTAMP

from typing import TYPE_CHECKING

from app.models.base import Base
from app.models.models import AuditMixin, CreatedAtMixin, UUIDMixin
from app.models.subscription_enums import LicenseStatus

if TYPE_CHECKING:
    from app.models.models import User
    from app.models.subscription import Subscription


class LicenseAssignment(UUIDMixin, CreatedAtMixin, AuditMixin, Base):
    """License assignment model.

    Tracks an active license for a user, including:
    - Usage limits (max products, AI credits, views, galleries)
    - Current usage counters (how much has been used)
    - License status (active, revoked, etc.)

    This is the core model for quota enforcement and usage tracking.
    """

    __tablename__ = "tbl_license_assignments"
    __table_args__ = (
        UniqueConstraint("subscription_id", "user_id", name="uq_license_subscription_user"),
        Index("ix_license_user", "user_id"),
    )

    subscription_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("tbl_subscriptions.id", ondelete="CASCADE"), nullable=False
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("tbl_users.id", ondelete="CASCADE"), nullable=False
    )
    status: Mapped[LicenseStatus] = mapped_column(
        Enum(LicenseStatus, name="license_status", native_enum=False),
        nullable=False,
        server_default=text("'active'"),
    )
    # limits and usage_counters are TEXT in database, storing JSON as string
    limits: Mapped[Optional[str]] = mapped_column(Text)
    usage_counters: Mapped[Optional[str]] = mapped_column(Text)

    # Property for backward compatibility
    @property
    def updated_at(self) -> Optional[datetime]:
        return self.updated_date

    subscription: Mapped["Subscription"] = relationship("Subscription", back_populates="licenses")
    user: Mapped["User"] = relationship("User", back_populates="licenses")

