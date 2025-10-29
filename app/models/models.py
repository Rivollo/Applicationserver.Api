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
from sqlalchemy.dialects.postgresql import ARRAY, CITEXT, JSONB, UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func
from sqlalchemy.types import TIMESTAMP

from app.models.base import Base


class UUIDMixin:
    id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)


class CreatedAtMixin:
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default=func.now(), nullable=False
    )


class TimestampMixin(CreatedAtMixin):
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


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


class Organization(UUIDMixin, TimestampMixin, SoftDeleteMixin, Base):
    __tablename__ = "organizations"

    name: Mapped[str] = mapped_column(Text, nullable=False)
    slug: Mapped[str] = mapped_column(Text, nullable=False)
    branding: Mapped[dict[str, Any]] = mapped_column(
        JSONB, server_default=text("'{}'::jsonb"), nullable=False
    )

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
    products: Mapped[list["Product"]] = relationship("Product", back_populates="organization")
    jobs: Mapped[list["Job"]] = relationship("Job", back_populates="organization")


class User(UUIDMixin, TimestampMixin, SoftDeleteMixin, Base):
    __tablename__ = "users"

    email: Mapped[str] = mapped_column(CITEXT, unique=True, nullable=False)
    password_hash: Mapped[Optional[str]] = mapped_column(Text)
    name: Mapped[Optional[str]] = mapped_column(Text)
    avatar_url: Mapped[Optional[str]] = mapped_column(Text)

    subscriptions: Mapped[list["Subscription"]] = relationship("Subscription", back_populates="user")
    licenses: Mapped[list["LicenseAssignment"]] = relationship("LicenseAssignment", back_populates="user")
    identities: Mapped[list["AuthIdentity"]] = relationship("AuthIdentity", back_populates="user")


class OrgMember(CreatedAtMixin, Base):
    __tablename__ = "org_members"
    __table_args__ = (UniqueConstraint("org_id", "user_id", name="uq_org_user"),)

    org_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), primary_key=True
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    role: Mapped[OrgRole] = mapped_column(Enum(OrgRole, name="org_role"), nullable=False)

    organization: Mapped[Organization] = relationship("Organization", back_populates="members")
    user: Mapped[User] = relationship("User")


class Plan(UUIDMixin, Base):
    __tablename__ = "plans"

    code: Mapped[str] = mapped_column(String, unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String, nullable=False)
    quotas: Mapped[dict[str, Any]] = mapped_column(JSONB, server_default=text("'{}'::jsonb"), nullable=False)

    subscriptions: Mapped[list["Subscription"]] = relationship("Subscription", back_populates="plan")


class Subscription(UUIDMixin, Base):
    __tablename__ = "subscriptions"
    __table_args__ = (Index("ix_subscriptions_user", "user_id"),)

    user_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    plan_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("plans.id"), nullable=False
    )
    status: Mapped[SubscriptionStatus] = mapped_column(
        Enum(SubscriptionStatus, name="subscription_status"), nullable=False
    )
    seats_purchased: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("1"))
    billing: Mapped[dict[str, Any]] = mapped_column(JSONB, server_default=text("'{}'::jsonb"), nullable=False)
    current_period_start: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default=func.now(), nullable=False
    )
    current_period_end: Mapped[Optional[datetime]] = mapped_column(TIMESTAMP(timezone=True))
    trial_end_at: Mapped[Optional[datetime]] = mapped_column(TIMESTAMP(timezone=True))
    renews_at: Mapped[Optional[datetime]] = mapped_column(TIMESTAMP(timezone=True))

    user: Mapped[User] = relationship("User", back_populates="subscriptions")
    plan: Mapped[Plan] = relationship("Plan", back_populates="subscriptions")
    licenses: Mapped[list["LicenseAssignment"]] = relationship("LicenseAssignment", back_populates="subscription")


class LicenseAssignment(UUIDMixin, CreatedAtMixin, Base):
    __tablename__ = "license_assignments"
    __table_args__ = (
        UniqueConstraint("subscription_id", "user_id", name="uq_license_subscription_user"),
        Index("ix_license_user", "user_id"),
    )

    subscription_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("subscriptions.id", ondelete="CASCADE"), nullable=False
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    status: Mapped[LicenseStatus] = mapped_column(
        Enum(LicenseStatus, name="license_status"), nullable=False, server_default=text("'active'"),
    )
    limits: Mapped[dict[str, Any]] = mapped_column(JSONB, server_default=text("'{}'::jsonb"), nullable=False)
    usage_counters: Mapped[dict[str, Any]] = mapped_column(JSONB, server_default=text("'{}'::jsonb"), nullable=False)

    subscription: Mapped[Subscription] = relationship("Subscription", back_populates="licenses")
    user: Mapped[User] = relationship("User", back_populates="licenses")


class Asset(UUIDMixin, CreatedAtMixin, Base):
    __tablename__ = "assets"
    __table_args__ = (Index("ix_assets_org_type", "org_id", "type"),)

    org_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    type: Mapped[AssetType] = mapped_column(Enum(AssetType, name="asset_type"), nullable=False)
    storage: Mapped[str] = mapped_column(String, nullable=False, server_default=text("'azure_blob'"))
    url: Mapped[str] = mapped_column(Text, nullable=False)
    mime_type: Mapped[Optional[str]] = mapped_column(String)
    size_bytes: Mapped[Optional[int]] = mapped_column(BigInteger)
    width: Mapped[Optional[int]] = mapped_column(Integer)
    height: Mapped[Optional[int]] = mapped_column(Integer)
    checksum_sha256: Mapped[Optional[str]] = mapped_column(String)
    created_by: Mapped[Optional[uuid.UUID]] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )

    organization: Mapped[Organization] = relationship("Organization", back_populates="assets")


class Product(UUIDMixin, TimestampMixin, SoftDeleteMixin, Base):
    __tablename__ = "products"
    __table_args__ = (
        UniqueConstraint("org_id", "slug", name="uq_product_org_slug"),
    )

    org_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(Text, nullable=False)
    slug: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[ProductStatus] = mapped_column(
        Enum(ProductStatus, name="product_status"), nullable=False, server_default=text("'draft'"),
    )
    cover_asset_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("assets.id", ondelete="SET NULL")
    )
    model_asset_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("assets.id", ondelete="SET NULL")
    )
    tags: Mapped[list[str]] = mapped_column(
        ARRAY(String), server_default=text("'{}'::text[]"), nullable=False
    )
    product_metadata: Mapped[dict[str, Any]] = mapped_column(
        "metadata", JSONB, server_default=text("'{}'::jsonb"), nullable=False
    )
    published_at: Mapped[Optional[datetime]] = mapped_column(TIMESTAMP(timezone=True))
    created_by: Mapped[Optional[uuid.UUID]] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )

    organization: Mapped[Organization] = relationship("Organization", back_populates="products")
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


class Configurator(UUIDMixin, Base):
    __tablename__ = "configurators"

    product_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("products.id", ondelete="CASCADE"), unique=True, nullable=False
    )
    settings: Mapped[dict[str, Any]] = mapped_column(JSONB, server_default=text("'{}'::jsonb"), nullable=False)

    product: Mapped[Product] = relationship("Product", back_populates="configurator")


class Hotspot(UUIDMixin, CreatedAtMixin, Base):
    __tablename__ = "hotspots"
    __table_args__ = (
        Index("ix_hotspots_product_order", "product_id", "order_index"),
        CheckConstraint("pos_x BETWEEN -1.0 AND 1.0", name="ck_hotspot_pos_x"),
        CheckConstraint("pos_y BETWEEN -1.0 AND 1.0", name="ck_hotspot_pos_y"),
        CheckConstraint("pos_z BETWEEN -1.0 AND 1.0", name="ck_hotspot_pos_z"),
    )

    product_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("products.id", ondelete="CASCADE"), nullable=False
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
        Enum(HotspotActionType, name="hotspot_action"),
        nullable=False,
        server_default=text("'none'"),
    )
    action_payload: Mapped[dict[str, Any]] = mapped_column(JSONB, server_default=text("'{}'::jsonb"), nullable=False)
    order_index: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))

    product: Mapped[Product] = relationship("Product", back_populates="hotspots")


class Job(UUIDMixin, CreatedAtMixin, Base):
    __tablename__ = "jobs"
    __table_args__ = (
        Index("ix_jobs_product_status", "product_id", "status"),
        Index("ix_jobs_org", "org_id"),
    )

    org_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    product_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("products.id", ondelete="CASCADE"), nullable=False
    )
    image_asset_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("assets.id"), nullable=False
    )
    model_asset_id: Mapped[Optional[uuid.UUID]] = mapped_column(PGUUID(as_uuid=True), ForeignKey("assets.id"))
    status: Mapped[JobStatus] = mapped_column(
        Enum(JobStatus, name="job_status"), nullable=False, server_default=text("'pending'"),
    )
    engine: Mapped[Optional[str]] = mapped_column(String)
    gpu_type: Mapped[Optional[str]] = mapped_column(String)
    credits_used: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("1"))
    started_at: Mapped[Optional[datetime]] = mapped_column(TIMESTAMP(timezone=True))
    completed_at: Mapped[Optional[datetime]] = mapped_column(TIMESTAMP(timezone=True))
    error: Mapped[dict[str, Any]] = mapped_column(JSONB, server_default=text("'{}'::jsonb"), nullable=False)

    organization: Mapped[Organization] = relationship("Organization", back_populates="jobs")
    product: Mapped[Product] = relationship("Product", back_populates="jobs")


class PublishLink(UUIDMixin, CreatedAtMixin, Base):
    __tablename__ = "publish_links"
    __table_args__ = (
        Index(
            "ix_publish_links_product_enabled",
            "product_id",
            postgresql_where=text("is_enabled"),
        ),
    )

    product_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("products.id", ondelete="CASCADE"), nullable=False
    )
    public_id: Mapped[str] = mapped_column(String, unique=True, nullable=False)
    is_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))
    expires_at: Mapped[Optional[datetime]] = mapped_column(TIMESTAMP(timezone=True))
    password_hash: Mapped[Optional[str]] = mapped_column(Text)
    iframe_allowed: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))
    view_count: Mapped[int] = mapped_column(BigInteger, nullable=False, server_default=text("0"))
    last_viewed_at: Mapped[Optional[datetime]] = mapped_column(TIMESTAMP(timezone=True))

    product: Mapped[Product] = relationship("Product", back_populates="publish_links")


class Gallery(UUIDMixin, TimestampMixin, SoftDeleteMixin, Base):
    __tablename__ = "galleries"
    __table_args__ = (UniqueConstraint("org_id", "slug", name="uq_gallery_org_slug"),)

    org_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(Text, nullable=False)
    slug: Mapped[str] = mapped_column(Text, nullable=False)
    is_public: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    settings: Mapped[dict[str, Any]] = mapped_column(JSONB, server_default=text("'{}'::jsonb"), nullable=False)
    created_by: Mapped[Optional[uuid.UUID]] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )

    items: Mapped[list["GalleryItem"]] = relationship(
        "GalleryItem", back_populates="gallery", cascade="all, delete-orphan"
    )


class GalleryItem(UUIDMixin, CreatedAtMixin, Base):
    __tablename__ = "gallery_items"
    __table_args__ = (
        UniqueConstraint("gallery_id", "product_id", name="uq_gallery_product"),
        Index("ix_gallery_items_order", "gallery_id", "order_index"),
    )

    gallery_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("galleries.id", ondelete="CASCADE"), nullable=False
    )
    product_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("products.id", ondelete="CASCADE"), nullable=False
    )
    order_index: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))

    gallery: Mapped[Gallery] = relationship("Gallery", back_populates="items")
    product: Mapped[Product] = relationship("Product")


class AnalyticsEvent(Base):
    __tablename__ = "analytics_events"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    org_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    product_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("products.id", ondelete="SET NULL")
    )
    publish_link_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("publish_links.id", ondelete="SET NULL")
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
    __tablename__ = "analytics_daily_product"
    __table_args__ = (
        PrimaryKeyConstraint("day", "org_id", "product_id", name="pk_analytics_daily_product"),
    )

    day: Mapped[date] = mapped_column(Date, nullable=False)
    org_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    product_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("products.id", ondelete="CASCADE"), nullable=False
    )
    views: Mapped[int] = mapped_column(BigInteger, nullable=False, server_default=text("0"))
    engaged: Mapped[int] = mapped_column(BigInteger, nullable=False, server_default=text("0"))
    adds_from_3d: Mapped[int] = mapped_column(BigInteger, nullable=False, server_default=text("0"))


class AuthIdentity(UUIDMixin, CreatedAtMixin, Base):
    __tablename__ = "auth_identities"
    __table_args__ = (UniqueConstraint("provider", "provider_user_id", name="uq_auth_identity_provider"),)

    user_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    provider: Mapped[AuthProvider] = mapped_column(Enum(AuthProvider, name="auth_provider"), nullable=False)
    provider_user_id: Mapped[str] = mapped_column(String, nullable=False)
    email: Mapped[str] = mapped_column(CITEXT, nullable=False)
    last_login_at: Mapped[Optional[datetime]] = mapped_column(TIMESTAMP(timezone=True))
    meta: Mapped[dict[str, Any]] = mapped_column(JSONB, server_default=text("'{}'::jsonb"), nullable=False)

    user: Mapped[User] = relationship("User", back_populates="identities")


class EmailVerification(UUIDMixin, Base):
    __tablename__ = "email_verifications"

    user_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    token: Mapped[str] = mapped_column(String, unique=True, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)
    used_at: Mapped[Optional[datetime]] = mapped_column(TIMESTAMP(timezone=True))


class PasswordReset(UUIDMixin, Base):
    __tablename__ = "password_resets"

    user_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    token: Mapped[str] = mapped_column(String, unique=True, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)
    used_at: Mapped[Optional[datetime]] = mapped_column(TIMESTAMP(timezone=True))


class ActivityLog(UUIDMixin, CreatedAtMixin, Base):
    __tablename__ = "activity_logs"
    __table_args__ = (Index("ix_activity_logs_org_created_at", "org_id", "created_at"),)

    org_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("organizations.id", ondelete="SET NULL")
    )
    user_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    action: Mapped[str] = mapped_column(String, nullable=False)
    target_type: Mapped[Optional[str]] = mapped_column(String)
    target_id: Mapped[Optional[str]] = mapped_column(String)
    ip_address: Mapped[Optional[str]] = mapped_column(String)
    user_agent: Mapped[Optional[str]] = mapped_column(Text)
    activity_metadata: Mapped[dict[str, Any]] = mapped_column(
        "metadata", JSONB, server_default=text("'{}'::jsonb"), nullable=False
    )


class Notification(UUIDMixin, CreatedAtMixin, Base):
    __tablename__ = "notifications"
    __table_args__ = (
        Index(
            "ix_notifications_user_unread",
            "user_id",
            postgresql_where=text("read_at IS NULL"),
        ),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    type: Mapped[str] = mapped_column(String, nullable=False)
    title: Mapped[str] = mapped_column(String, nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    channel: Mapped[NotificationChannel] = mapped_column(
        Enum(NotificationChannel, name="notification_channel"),
        nullable=False,
        server_default=text("'in_app'"),
    )
    data: Mapped[dict[str, Any]] = mapped_column(JSONB, server_default=text("'{}'::jsonb"), nullable=False)
    read_at: Mapped[Optional[datetime]] = mapped_column(TIMESTAMP(timezone=True))


class UserNotificationPreference(UUIDMixin, Base):
    __tablename__ = "user_notification_prefs"
    __table_args__ = (UniqueConstraint("user_id", "notification_type", name="uq_user_notification_pref"),)

    user_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    notification_type: Mapped[str] = mapped_column(String, nullable=False)
    channels: Mapped[list[str]] = mapped_column(JSONB, server_default=text("'[]'::jsonb"), nullable=False)
    muted: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
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
        PGUUID(as_uuid=True), ForeignKey("assets.id", ondelete="CASCADE"), nullable=False
    )
    part_name: Mapped[str] = mapped_column(String, nullable=False)
    storage: Mapped[str] = mapped_column(String, nullable=False, server_default=text("'azure_blob'"))
    url: Mapped[str] = mapped_column(Text, nullable=False)
    mime_type: Mapped[Optional[str]] = mapped_column(String)
    size_bytes: Mapped[Optional[int]] = mapped_column(BigInteger)


# Alias for backwards compatibility
JobStatusEnum = JobStatus
