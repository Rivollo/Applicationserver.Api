from __future__ import annotations

import enum
import uuid
from datetime import date, datetime
from typing import Any, Optional

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Date,
    Enum,
    ForeignKey,
    Index,
    Integer,
    PrimaryKeyConstraint,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import CITEXT, JSONB, UUID as PGUUID
from sqlalchemy.orm import Mapped, column_property, mapped_column, relationship
from sqlalchemy.sql import func
from sqlalchemy.sql.expression import literal_column
from sqlalchemy.types import TIMESTAMP

from app.models.base import Base


class UUIDMixin:
    id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)


class AuditMixin:
    """Audit fields that exist in all tables: created_by, created_date, updated_by, updated_date"""
    created_by: Mapped[Optional[uuid.UUID]] = mapped_column(PGUUID(as_uuid=True))
    created_date: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default=func.now(), nullable=False
    )
    updated_by: Mapped[Optional[uuid.UUID]] = mapped_column(PGUUID(as_uuid=True))
    updated_date: Mapped[Optional[datetime]] = mapped_column(TIMESTAMP(timezone=True))


class CreatedAtMixin:
    """For tables that have created_at column directly (in addition to audit fields)"""
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        server_default=func.now(),
        nullable=False
    )


class TimestampMixin(AuditMixin):
    """Map created_at/updated_at to created_date/updated_date for backward compatibility"""
    @property
    def created_at(self) -> datetime:
        return self.created_date

    @property
    def updated_at(self) -> Optional[datetime]:
        return self.updated_date


class SoftDeleteMixin:
    deleted_at: Mapped[Optional[datetime]] = mapped_column(TIMESTAMP(timezone=True))


class OrgRole(str, enum.Enum):
    OWNER = "owner"
    ADMIN = "admin"
    MEMBER = "member"


class SubscriptionStatus(str, enum.Enum):
    TRIALING = "trialing"
    ACTIVE = "active"
    CANCELED = "canceled"
    PAST_DUE = "past_due"


class LicenseStatus(str, enum.Enum):
    INVITED = "invited"
    ACTIVE = "active"
    REVOKED = "revoked"


class AssetType(str, enum.Enum):
    IMAGE = "image"
    MODEL = "model"
    MASK = "mask"
    THUMBNAIL = "thumbnail"


class ProductStatus(str, enum.Enum):
    DRAFT = "draft"
    PROCESSING = "processing"
    READY = "ready"
    PUBLISHED = "published"
    UNPUBLISHED = "unpublished"
    ARCHIVED = "archived"


class JobStatus(str, enum.Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


class HotspotActionType(str, enum.Enum):
    NONE = "none"
    LINK = "link"
    MATERIAL_SWITCH = "material-switch"
    VARIANT_SWITCH = "variant-switch"
    TEXT_ONLY = "text-only"


class NotificationChannel(str, enum.Enum):
    IN_APP = "in_app"
    EMAIL = "email"
    PUSH = "push"


class AuthProvider(str, enum.Enum):
    GOOGLE = "google"
    EMAIL = "email"


class Organization(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "tbl_organizations"

    name: Mapped[str] = mapped_column(Text, nullable=False)
    slug: Mapped[str] = mapped_column(Text, nullable=False)
    # branding is TEXT in database, storing JSON as string
    branding: Mapped[Optional[str]] = mapped_column(Text)
    # Virtual column - organizations table doesn't have deleted_at in database
    deleted_at = column_property(literal_column("NULL::timestamptz"))

    __table_args__ = (
        Index(
            "ix_organizations_slug_unique",
            "slug",
            unique=True,
            postgresql_where=text("deleted_at IS NULL"),
        ),
    )

    members: Mapped[list["OrgMember"]] = relationship("OrgMember", back_populates="organization")
    assets: Mapped[list["Asset"]] = relationship("Asset", back_populates="organization")


class User(UUIDMixin, CreatedAtMixin, AuditMixin, Base):
    """User model - has BOTH created_at AND audit fields (created_date, etc.)"""
    __tablename__ = "tbl_users"

    email: Mapped[str] = mapped_column(CITEXT, unique=True, nullable=False)
    password_hash: Mapped[Optional[str]] = mapped_column(Text)
    name: Mapped[Optional[str]] = mapped_column(Text)
    avatar_url: Mapped[Optional[str]] = mapped_column(Text)

    # Virtual column - users table doesn't have deleted_at in database
    deleted_at = column_property(literal_column("NULL::timestamptz"))

    # Property for backward compatibility
    @property
    def updated_at(self) -> Optional[datetime]:
        return self.updated_date

    subscriptions: Mapped[list["Subscription"]] = relationship("Subscription", back_populates="user")
    licenses: Mapped[list["LicenseAssignment"]] = relationship("LicenseAssignment", back_populates="user")
    identities: Mapped[list["AuthIdentity"]] = relationship("AuthIdentity", back_populates="user")


class OrgMember(AuditMixin, Base):
    __tablename__ = "tbl_org_members"
    __table_args__ = (UniqueConstraint("org_id", "user_id", name="uq_org_user"),)

    org_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("tbl_organizations.id", ondelete="CASCADE"), primary_key=True
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("tbl_users.id", ondelete="CASCADE"), primary_key=True
    )
    role: Mapped[OrgRole] = mapped_column(Enum(OrgRole, name="org_role", native_enum=False), nullable=False)

    # Property for backward compatibility
    @property
    def created_at(self) -> datetime:
        return self.created_date

    organization: Mapped[Organization] = relationship("Organization", back_populates="members")
    user: Mapped[User] = relationship("User")


class Plan(UUIDMixin, AuditMixin, Base):
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


class Subscription(UUIDMixin, Base):
    __tablename__ = "tbl_subscriptions"
    __table_args__ = (Index("ix_subscriptions_user", "user_id"),)

    user_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("tbl_users.id", ondelete="CASCADE"), nullable=False
    )
    plan_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("tbl_mstr_plans.id"), nullable=False
    )
    status: Mapped[SubscriptionStatus] = mapped_column(
        Enum(SubscriptionStatus, name="subscription_status", native_enum=False), nullable=False
    )
    seats_purchased: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("1"))
    # billing column is TEXT in database, but we treat it as JSONB in Python
    billing: Mapped[Optional[str]] = mapped_column(Text)

    # These columns exist in the database as nullable timestamps
    current_period_start: Mapped[Optional[datetime]] = mapped_column(TIMESTAMP(timezone=True))
    current_period_end: Mapped[Optional[datetime]] = mapped_column(TIMESTAMP(timezone=True))

    # Audit fields that exist in the database
    created_by: Mapped[Optional[uuid.UUID]] = mapped_column(PGUUID(as_uuid=True))
    created_date: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default=func.now(), nullable=False
    )
    updated_by: Mapped[Optional[uuid.UUID]] = mapped_column(PGUUID(as_uuid=True))
    updated_date: Mapped[Optional[datetime]] = mapped_column(TIMESTAMP(timezone=True))

    # Virtual columns - these don't exist in the actual database table
    # Keeping as properties for backward compatibility with code that references them
    trial_end_at = column_property(literal_column("NULL::timestamptz"))
    renews_at = column_property(literal_column("NULL::timestamptz"))

    user: Mapped[User] = relationship("User", back_populates="subscriptions")
    plan: Mapped[Plan] = relationship("Plan", back_populates="subscriptions")
    licenses: Mapped[list["LicenseAssignment"]] = relationship("LicenseAssignment", back_populates="subscription")


class LicenseAssignment(UUIDMixin, CreatedAtMixin, AuditMixin, Base):
    """LicenseAssignment - has BOTH created_at AND audit fields"""
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
        Enum(LicenseStatus, name="license_status", native_enum=False), nullable=False, server_default=text("'active'"),
    )
    # limits and usage_counters are TEXT in database, storing JSON as string
    limits: Mapped[Optional[str]] = mapped_column(Text)
    usage_counters: Mapped[Optional[str]] = mapped_column(Text)

    # Property for backward compatibility
    @property
    def updated_at(self) -> Optional[datetime]:
        return self.updated_date

    subscription: Mapped[Subscription] = relationship("Subscription", back_populates="licenses")
    user: Mapped[User] = relationship("User", back_populates="licenses")


class Asset(UUIDMixin, AuditMixin, Base):
    __tablename__ = "tbl_assets"
    __table_args__ = (Index("ix_assets_org_type", "org_id", "type"),)

    org_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("tbl_organizations.id", ondelete="CASCADE"), nullable=False
    )
    type: Mapped[AssetType] = mapped_column(Enum(AssetType, name="asset_type", native_enum=False), nullable=False)
    storage: Mapped[str] = mapped_column(String, nullable=False, server_default=text("'azure_blob'"))
    url: Mapped[str] = mapped_column(Text, nullable=False)
    mime_type: Mapped[Optional[str]] = mapped_column(String)
    size_bytes: Mapped[Optional[int]] = mapped_column(BigInteger)
    width: Mapped[Optional[int]] = mapped_column(Integer)
    height: Mapped[Optional[int]] = mapped_column(Integer)
    checksum_sha256: Mapped[Optional[str]] = mapped_column(String)

    # Property for backward compatibility
    @property
    def created_at(self) -> datetime:
        return self.created_date

    organization: Mapped[Organization] = relationship("Organization", back_populates="assets")


class Product(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "tbl_products"
    __table_args__ = ()

    # No org_id column in current DB snapshot; expose virtual NULL
    org_id = column_property(literal_column("NULL::uuid"))
    name: Mapped[str] = mapped_column(Text, nullable=False)
    slug: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[ProductStatus] = mapped_column(
        Enum(ProductStatus, name="product_status", native_enum=False), nullable=False, server_default=text("'draft'"),
    )
    # cover_asset_id column no longer exists in some database snapshots; keep virtual
    cover_asset_id = column_property(literal_column("NULL::uuid"))
    model_asset_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("tbl_assets.id", ondelete="SET NULL")
    )
    # tags column absent in legacy snapshot; expose as virtual empty array
    tags = column_property(literal_column("'{}'::text[]"))
    # Note: products table doesn't have metadata column in actual DB
    # Keeping as virtual column for backward compatibility
    product_metadata = column_property(literal_column("'{}'::jsonb"))
    published_at = column_property(literal_column("NULL::timestamptz"))
    # created_by, updated_by from TimestampMixin -> AuditMixin
    # Virtual column - products table doesn't have deleted_at in database
    deleted_at = column_property(literal_column("NULL::timestamptz"))

    # No organization relationship without org_id FK
    configurator: Mapped[Optional["Configurator"]] = relationship(
        "Configurator", back_populates="product", uselist=False
    )
    hotspots: Mapped[list["Hotspot"]] = relationship(
        "Hotspot", back_populates="product", cascade="all, delete-orphan"
    )
    publish_links: Mapped[list["PublishLink"]] = relationship(
        "PublishLink", back_populates="product", cascade="all, delete-orphan"
    )
    jobs: Mapped[list["Job"]] = relationship("Job", back_populates="product")


class Configurator(UUIDMixin, AuditMixin, Base):
    __tablename__ = "tbl_configurators"

    product_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("tbl_products.id", ondelete="CASCADE"), unique=True, nullable=False
    )
    # settings is TEXT in database, storing JSON as string
    settings: Mapped[Optional[str]] = mapped_column(Text)

    # Property for backward compatibility
    @property
    def created_at(self) -> datetime:
        return self.created_date

    product: Mapped[Product] = relationship("Product", back_populates="configurator")


class Hotspot(UUIDMixin, CreatedAtMixin, AuditMixin, Base):
    """Hotspot - has BOTH created_at AND audit fields"""
    __tablename__ = "tbl_hotspots"
    __table_args__ = (
        Index("ix_hotspots_product_order", "product_id", "order_index"),
        CheckConstraint("pos_x BETWEEN -1.0 AND 1.0", name="ck_hotspot_pos_x"),
        CheckConstraint("pos_y BETWEEN -1.0 AND 1.0", name="ck_hotspot_pos_y"),
        CheckConstraint("pos_z BETWEEN -1.0 AND 1.0", name="ck_hotspot_pos_z"),
    )

    product_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("tbl_products.id", ondelete="CASCADE"), nullable=False
    )
    label: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    pos_x: Mapped[float] = mapped_column(nullable=False)
    pos_y: Mapped[float] = mapped_column(nullable=False)
    pos_z: Mapped[float] = mapped_column(nullable=False)
    text_font: Mapped[Optional[str]] = mapped_column(String)
    text_color: Mapped[Optional[str]] = mapped_column(String)
    bg_color: Mapped[Optional[str]] = mapped_column(String)
    action_type: Mapped[HotspotActionType] = mapped_column(
        Enum(HotspotActionType, name="hotspot_action", native_enum=False),
        nullable=False,
        server_default=text("'none'"),
    )
    # action_payload is TEXT in database, storing JSON as string
    action_payload: Mapped[Optional[str]] = mapped_column(Text)
    order_index: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))

    # Property for backward compatibility
    @property
    def updated_at(self) -> Optional[datetime]:
        return self.updated_date

    product: Mapped[Product] = relationship("Product", back_populates="hotspots")


class Job(UUIDMixin, AuditMixin, Base):
    __tablename__ = "tbl_jobs"
    __table_args__ = (
        Index("ix_jobs_product_status", "product_id", "status"),
    )

    # Note: org_id not in actual database, made virtual for backward compatibility
    @property
    def org_id(self) -> Optional[uuid.UUID]:
        return self.product.org_id if hasattr(self, 'product') and self.product else None

    product_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("tbl_products.id", ondelete="CASCADE"), nullable=False
    )
    image_asset_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("tbl_assets.id")
    )
    model_asset_id: Mapped[Optional[uuid.UUID]] = mapped_column(PGUUID(as_uuid=True), ForeignKey("tbl_assets.id"))
    status: Mapped[str] = mapped_column(Text, nullable=False)
    engine: Mapped[Optional[str]] = mapped_column(Text)
    completed_at: Mapped[Optional[datetime]] = mapped_column(TIMESTAMP(timezone=True))

    # Virtual columns - these don't exist in actual database
    gpu_type = column_property(literal_column("NULL::text"))
    credits_used = column_property(literal_column("1::integer"))
    started_at = column_property(literal_column("NULL::timestamptz"))
    error = column_property(literal_column("'{}'::jsonb"))

    # Property for backward compatibility
    @property
    def created_at(self) -> datetime:
        return self.created_date

    product: Mapped[Product] = relationship("Product", back_populates="jobs")


class PublishLink(UUIDMixin, CreatedAtMixin, Base):
    __tablename__ = "tbl_publish_links"
    __table_args__ = (
        Index(
            "ix_publish_links_product_enabled",
            "product_id",
            postgresql_where=text("is_enabled"),
        ),
    )

    product_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("tbl_products.id", ondelete="CASCADE"), nullable=False
    )
    public_id: Mapped[str] = mapped_column(String, unique=True, nullable=False)
    is_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))
    expires_at: Mapped[Optional[datetime]] = mapped_column(TIMESTAMP(timezone=True))
    password_hash: Mapped[Optional[str]] = mapped_column(Text)
    iframe_allowed: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))
    view_count: Mapped[int] = mapped_column(BigInteger, nullable=False, server_default=text("0"))
    last_viewed_at: Mapped[Optional[datetime]] = mapped_column(TIMESTAMP(timezone=True))

    product: Mapped[Product] = relationship("Product", back_populates="publish_links")


class Gallery(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "tbl_galleries"
    __table_args__ = (UniqueConstraint("org_id", "slug", name="uq_gallery_org_slug"),)

    org_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("tbl_organizations.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(Text, nullable=False)
    slug: Mapped[str] = mapped_column(Text, nullable=False)
    is_public: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    # settings column doesn't exist in DB snapshot; expose virtual empty object
    settings = column_property(literal_column("'{}'::jsonb"))
    created_by: Mapped[Optional[uuid.UUID]] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("tbl_users.id", ondelete="SET NULL")
    )
    # Virtual column - galleries table doesn't have deleted_at in database
    deleted_at = column_property(literal_column("NULL::timestamptz"))

    items: Mapped[list["GalleryItem"]] = relationship(
        "GalleryItem", back_populates="gallery", cascade="all, delete-orphan"
    )


class GalleryItem(UUIDMixin, CreatedAtMixin, Base):
    __tablename__ = "tbl_gallery_items"
    __table_args__ = (
        UniqueConstraint("gallery_id", "product_id", name="uq_gallery_product"),
        Index("ix_gallery_items_order", "gallery_id", "order_index"),
    )

    gallery_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("tbl_galleries.id", ondelete="CASCADE"), nullable=False
    )
    product_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("tbl_products.id", ondelete="CASCADE"), nullable=False
    )
    order_index: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))

    gallery: Mapped[Gallery] = relationship("Gallery", back_populates="items")
    product: Mapped[Product] = relationship("Product")


class AnalyticsEvent(Base):
    __tablename__ = "tbl_analytics_events"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    org_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("tbl_organizations.id", ondelete="CASCADE"), nullable=False
    )
    product_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("tbl_products.id", ondelete="SET NULL")
    )
    publish_link_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("tbl_publish_links.id", ondelete="SET NULL")
    )
    session_id: Mapped[Optional[str]] = mapped_column(String)
    event_type: Mapped[str] = mapped_column(String, nullable=False)
    user_agent: Mapped[Optional[str]] = mapped_column(Text)
    ip_hash: Mapped[Optional[str]] = mapped_column(String)
    occurred_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default=func.now(), nullable=False
    )
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, server_default=text("'{}'::jsonb"), nullable=False)


Index("ix_analytics_events_org_time", AnalyticsEvent.org_id, AnalyticsEvent.occurred_at)
Index("ix_analytics_events_product_time", AnalyticsEvent.product_id, AnalyticsEvent.occurred_at)
Index(
    "ix_analytics_events_payload_gin",
    AnalyticsEvent.payload,
    postgresql_using="gin",
)


class AnalyticsDailyProduct(Base):
    __tablename__ = "tbl_analytics_daily_product"
    __table_args__ = (
        PrimaryKeyConstraint("day", "org_id", "product_id", name="pk_analytics_daily_product"),
    )

    day: Mapped[date] = mapped_column(Date, nullable=False)
    org_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("tbl_organizations.id", ondelete="CASCADE"), nullable=False
    )
    product_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("tbl_products.id", ondelete="CASCADE"), nullable=False
    )
    views: Mapped[int] = mapped_column(BigInteger, nullable=False, server_default=text("0"))
    engaged: Mapped[int] = mapped_column(BigInteger, nullable=False, server_default=text("0"))
    adds_from_3d: Mapped[int] = mapped_column(BigInteger, nullable=False, server_default=text("0"))


class AuthIdentity(UUIDMixin, AuditMixin, Base):
    __tablename__ = "tbl_auth_identities"
    __table_args__ = (UniqueConstraint("provider", "provider_user_id", name="uq_auth_identity_provider"),)

    user_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("tbl_users.id", ondelete="CASCADE"), nullable=False
    )
    provider: Mapped[AuthProvider] = mapped_column(Enum(AuthProvider, name="auth_provider", native_enum=False), nullable=False)
    provider_user_id: Mapped[str] = mapped_column(String, nullable=False)
    email: Mapped[Optional[str]] = mapped_column(CITEXT)
    last_login_at: Mapped[Optional[datetime]] = mapped_column(TIMESTAMP(timezone=True))
    # meta is TEXT in database, storing JSON as string
    meta: Mapped[Optional[str]] = mapped_column(Text)

    # Property for backward compatibility
    @property
    def created_at(self) -> datetime:
        return self.created_date

    user: Mapped[User] = relationship("User", back_populates="identities")


class EmailVerification(UUIDMixin, Base):
    __tablename__ = "tbl_email_verifications"

    user_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("tbl_users.id", ondelete="CASCADE"), nullable=False
    )
    token: Mapped[str] = mapped_column(String, unique=True, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)
    used_at: Mapped[Optional[datetime]] = mapped_column(TIMESTAMP(timezone=True))


class PasswordReset(UUIDMixin, Base):
    __tablename__ = "tbl_password_resets"

    user_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("tbl_users.id", ondelete="CASCADE"), nullable=False
    )
    token: Mapped[str] = mapped_column(String, unique=True, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)
    used_at: Mapped[Optional[datetime]] = mapped_column(TIMESTAMP(timezone=True))


class ActivityLog(UUIDMixin, AuditMixin, Base):
    __tablename__ = "tbl_activity_logs"
    __table_args__ = (Index("ix_activity_logs_org_occurred_at", "org_id", "occurred_at"),)

    actor_user_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("tbl_users.id", ondelete="SET NULL")
    )
    org_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("tbl_organizations.id", ondelete="SET NULL")
    )
    target_type: Mapped[str] = mapped_column(Text, nullable=False)
    target_id: Mapped[Optional[uuid.UUID]] = mapped_column(PGUUID(as_uuid=True))
    action: Mapped[str] = mapped_column(Text, nullable=False)
    ip: Mapped[Optional[str]] = mapped_column(Text)
    user_agent: Mapped[Optional[str]] = mapped_column(Text)
    occurred_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default=func.now(), nullable=False
    )
    # metadata is TEXT in database, storing JSON as string
    activity_metadata: Mapped[Optional[str]] = mapped_column("metadata", Text)

    # Property for backward compatibility
    @property
    def created_at(self) -> datetime:
        return self.created_date

    # Alias for backward compatibility
    @property
    def user_id(self) -> Optional[uuid.UUID]:
        return self.actor_user_id

    @user_id.setter
    def user_id(self, value: Optional[uuid.UUID]) -> None:
        self.actor_user_id = value

    @property
    def ip_address(self) -> Optional[str]:
        return self.ip

    @ip_address.setter
    def ip_address(self, value: Optional[str]) -> None:
        self.ip = value


class Notification(UUIDMixin, CreatedAtMixin, Base):
    __tablename__ = "tbl_notifications"
    __table_args__ = (
        Index(
            "ix_notifications_user_unread",
            "user_id",
            postgresql_where=text("read_at IS NULL"),
        ),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("tbl_users.id", ondelete="CASCADE"), nullable=False
    )
    type: Mapped[str] = mapped_column(String, nullable=False)
    title: Mapped[str] = mapped_column(String, nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    # 'channel' column does not exist in DB; expose default as virtual
    channel = column_property(literal_column("'in_app'::text"))
    # DB stores 'data' as TEXT; services are responsible for JSON serialization
    data: Mapped[Optional[str]] = mapped_column(Text)
    read_at: Mapped[Optional[datetime]] = mapped_column(TIMESTAMP(timezone=True))


class UserNotificationPreference(Base):
    __tablename__ = "tbl_user_notification_prefs"

    # Table has only user_id as key-like column; model it as PK for ORM
    user_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("tbl_users.id", ondelete="CASCADE"), primary_key=True
    )
    # Stored as TEXT in DB; service parses as JSON/CSV
    channels: Mapped[Optional[str]] = mapped_column(Text)
    muted_types: Mapped[Optional[str]] = mapped_column(Text)
    # Keep audit updated_date mapping for convenience
    updated_at: Mapped[Optional[datetime]] = mapped_column(
        "updated_date",
        TIMESTAMP(timezone=True),
    )


# Legacy models for backwards compatibility with existing routes
class Upload(UUIDMixin, CreatedAtMixin, Base):
    __tablename__ = "uploads"

    filename: Mapped[str] = mapped_column(String, nullable=False)
    upload_url: Mapped[str] = mapped_column(Text, nullable=False)
    file_url: Mapped[str] = mapped_column(Text, nullable=False)
    created_by: Mapped[str] = mapped_column(String, nullable=False)


class AssetPart(UUIDMixin, CreatedAtMixin, Base):
    __tablename__ = "asset_parts"

    asset_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("tbl_assets.id", ondelete="CASCADE"), nullable=False
    )
    part_name: Mapped[str] = mapped_column(String, nullable=False)
    storage: Mapped[str] = mapped_column(String, nullable=False, server_default=text("'azure_blob'"))
    url: Mapped[str] = mapped_column(Text, nullable=False)
    mime_type: Mapped[Optional[str]] = mapped_column(String)
    size_bytes: Mapped[Optional[int]] = mapped_column(BigInteger)


# Alias for backwards compatibility
JobStatusEnum = JobStatus
