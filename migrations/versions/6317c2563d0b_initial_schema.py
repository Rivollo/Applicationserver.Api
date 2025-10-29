"""initial schema

Revision ID: 6317c2563d0b
Revises: 
Create Date: 2025-10-29 19:19:01.016964

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = '6317c2563d0b'
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


org_role_enum = sa.Enum('owner', 'admin', 'member', name='org_role')
subscription_status_enum = sa.Enum('trialing', 'active', 'canceled', 'past_due', name='subscription_status')
license_status_enum = sa.Enum('invited', 'active', 'revoked', name='license_status')
asset_type_enum = sa.Enum('image', 'model', 'mask', 'thumbnail', name='asset_type')
product_status_enum = sa.Enum('draft', 'processing', 'ready', 'published', 'unpublished', 'archived', name='product_status')
job_status_enum = sa.Enum('pending', 'processing', 'completed', 'failed', name='job_status')
hotspot_action_enum = sa.Enum('none', 'link', 'material-switch', 'variant-switch', 'text-only', name='hotspot_action')
notification_channel_enum = sa.Enum('in_app', 'email', 'push', name='notification_channel')
auth_provider_enum = sa.Enum('google', 'email', name='auth_provider')


def upgrade() -> None:
    """Upgrade schema."""
    bind = op.get_bind()

    op.execute("CREATE EXTENSION IF NOT EXISTS pgcrypto")
    op.execute("CREATE EXTENSION IF NOT EXISTS citext")

    org_role_enum.create(bind, checkfirst=True)
    subscription_status_enum.create(bind, checkfirst=True)
    license_status_enum.create(bind, checkfirst=True)
    asset_type_enum.create(bind, checkfirst=True)
    product_status_enum.create(bind, checkfirst=True)
    job_status_enum.create(bind, checkfirst=True)
    hotspot_action_enum.create(bind, checkfirst=True)
    notification_channel_enum.create(bind, checkfirst=True)
    auth_provider_enum.create(bind, checkfirst=True)

    op.create_table(
        'organizations',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, nullable=False, server_default=sa.text('gen_random_uuid()')),
        sa.Column('name', sa.Text(), nullable=False),
        sa.Column('slug', sa.Text(), nullable=False),
        sa.Column('branding', postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column('created_at', sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.Column('updated_at', sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.Column('deleted_at', sa.TIMESTAMP(timezone=True), nullable=True),
    )
    op.create_index(
        'ix_organizations_slug_unique',
        'organizations',
        ['slug'],
        unique=True,
        postgresql_where=sa.text('deleted_at IS NULL'),
    )

    op.create_table(
        'users',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, nullable=False, server_default=sa.text('gen_random_uuid()')),
        sa.Column('email', postgresql.CITEXT(), nullable=False, unique=True),
        sa.Column('password_hash', sa.Text(), nullable=True),
        sa.Column('name', sa.Text(), nullable=True),
        sa.Column('avatar_url', sa.Text(), nullable=True),
        sa.Column('created_at', sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.Column('updated_at', sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.Column('deleted_at', sa.TIMESTAMP(timezone=True), nullable=True),
    )

    op.create_table(
        'plans',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, nullable=False, server_default=sa.text('gen_random_uuid()')),
        sa.Column('code', sa.String(), nullable=False, unique=True),
        sa.Column('name', sa.String(), nullable=False),
        sa.Column('quotas', postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
    )

    op.create_table(
        'subscriptions',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, nullable=False, server_default=sa.text('gen_random_uuid()')),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
        sa.Column('plan_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('plans.id'), nullable=False),
        sa.Column('status', subscription_status_enum, nullable=False),
        sa.Column('seats_purchased', sa.Integer(), nullable=False, server_default=sa.text('1')),
        sa.Column('billing', postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column('current_period_start', sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.Column('current_period_end', sa.TIMESTAMP(timezone=True)),
        sa.Column('trial_end_at', sa.TIMESTAMP(timezone=True)),
        sa.Column('renews_at', sa.TIMESTAMP(timezone=True)),
    )
    op.create_index('ix_subscriptions_user', 'subscriptions', ['user_id'])

    op.create_table(
        'license_assignments',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, nullable=False, server_default=sa.text('gen_random_uuid()')),
        sa.Column('subscription_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('subscriptions.id', ondelete='CASCADE'), nullable=False),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
        sa.Column('status', license_status_enum, nullable=False, server_default=sa.text("'active'")),
        sa.Column('limits', postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column('usage_counters', postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column('created_at', sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.UniqueConstraint('subscription_id', 'user_id', name='uq_license_subscription_user'),
    )
    op.create_index('ix_license_user', 'license_assignments', ['user_id'])

    op.create_table(
        'assets',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, nullable=False, server_default=sa.text('gen_random_uuid()')),
        sa.Column('org_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('organizations.id', ondelete='CASCADE'), nullable=False),
        sa.Column('type', asset_type_enum, nullable=False),
        sa.Column('storage', sa.String(), nullable=False, server_default=sa.text("'azure_blob'")),
        sa.Column('url', sa.Text(), nullable=False),
        sa.Column('mime_type', sa.String()),
        sa.Column('size_bytes', sa.BigInteger()),
        sa.Column('width', sa.Integer()),
        sa.Column('height', sa.Integer()),
        sa.Column('checksum_sha256', sa.String()),
        sa.Column('created_by', postgresql.UUID(as_uuid=True), sa.ForeignKey('users.id', ondelete='SET NULL')),
        sa.Column('created_at', sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text('now()')),
    )
    op.create_index('ix_assets_org_type', 'assets', ['org_id', 'type'])

    op.create_table(
        'products',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, nullable=False, server_default=sa.text('gen_random_uuid()')),
        sa.Column('org_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('organizations.id', ondelete='CASCADE'), nullable=False),
        sa.Column('name', sa.Text(), nullable=False),
        sa.Column('slug', sa.Text(), nullable=False),
        sa.Column('status', product_status_enum, nullable=False, server_default=sa.text("'draft'")),
        sa.Column('cover_asset_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('assets.id', ondelete='SET NULL')),
        sa.Column('model_asset_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('assets.id', ondelete='SET NULL')),
        sa.Column('tags', postgresql.ARRAY(sa.String()), nullable=False, server_default=sa.text("'{}'::text[]")),
        sa.Column('metadata', postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column('published_at', sa.TIMESTAMP(timezone=True)),
        sa.Column('created_by', postgresql.UUID(as_uuid=True), sa.ForeignKey('users.id', ondelete='SET NULL')),
        sa.Column('created_at', sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.Column('updated_at', sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.Column('deleted_at', sa.TIMESTAMP(timezone=True)),
        sa.UniqueConstraint('org_id', 'slug', name='uq_product_org_slug'),
    )

    op.create_table(
        'configurators',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, nullable=False, server_default=sa.text('gen_random_uuid()')),
        sa.Column('product_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('products.id', ondelete='CASCADE'), nullable=False, unique=True),
        sa.Column('settings', postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
    )

    op.create_table(
        'hotspots',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, nullable=False, server_default=sa.text('gen_random_uuid()')),
        sa.Column('product_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('products.id', ondelete='CASCADE'), nullable=False),
        sa.Column('label', sa.Text(), nullable=False),
        sa.Column('description', sa.Text(), nullable=False),
        sa.Column('pos_x', sa.Float(), nullable=False),
        sa.Column('pos_y', sa.Float(), nullable=False),
        sa.Column('pos_z', sa.Float(), nullable=False),
        sa.Column('text_font', sa.String()),
        sa.Column('text_color', sa.String()),
        sa.Column('bg_color', sa.String()),
        sa.Column('action_type', hotspot_action_enum, nullable=False, server_default=sa.text("'none'")),
        sa.Column('action_payload', postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column('order_index', sa.Integer(), nullable=False, server_default=sa.text('0')),
        sa.Column('created_at', sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.CheckConstraint('pos_x BETWEEN -1.0 AND 1.0', name='ck_hotspot_pos_x'),
        sa.CheckConstraint('pos_y BETWEEN -1.0 AND 1.0', name='ck_hotspot_pos_y'),
        sa.CheckConstraint('pos_z BETWEEN -1.0 AND 1.0', name='ck_hotspot_pos_z'),
    )
    op.create_index('ix_hotspots_product_order', 'hotspots', ['product_id', 'order_index'])

    op.create_table(
        'jobs',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, nullable=False, server_default=sa.text('gen_random_uuid()')),
        sa.Column('org_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('organizations.id', ondelete='CASCADE'), nullable=False),
        sa.Column('product_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('products.id', ondelete='CASCADE'), nullable=False),
        sa.Column('image_asset_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('assets.id'), nullable=False),
        sa.Column('model_asset_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('assets.id')),
        sa.Column('status', job_status_enum, nullable=False, server_default=sa.text("'pending'")),
        sa.Column('engine', sa.String()),
        sa.Column('gpu_type', sa.String()),
        sa.Column('credits_used', sa.Integer(), nullable=False, server_default=sa.text('1')),
        sa.Column('started_at', sa.TIMESTAMP(timezone=True)),
        sa.Column('completed_at', sa.TIMESTAMP(timezone=True)),
        sa.Column('error', postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column('created_at', sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text('now()')),
    )
    op.create_index('ix_jobs_product_status', 'jobs', ['product_id', 'status'])
    op.create_index('ix_jobs_org', 'jobs', ['org_id'])

    op.create_table(
        'publish_links',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, nullable=False, server_default=sa.text('gen_random_uuid()')),
        sa.Column('product_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('products.id', ondelete='CASCADE'), nullable=False),
        sa.Column('public_id', sa.String(), nullable=False, unique=True),
        sa.Column('is_enabled', sa.Boolean(), nullable=False, server_default=sa.text('true')),
        sa.Column('expires_at', sa.TIMESTAMP(timezone=True)),
        sa.Column('password_hash', sa.Text()),
        sa.Column('iframe_allowed', sa.Boolean(), nullable=False, server_default=sa.text('true')),
        sa.Column('view_count', sa.BigInteger(), nullable=False, server_default=sa.text('0')),
        sa.Column('last_viewed_at', sa.TIMESTAMP(timezone=True)),
        sa.Column('created_at', sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text('now()')),
    )
    op.create_index(
        'ix_publish_links_product_enabled',
        'publish_links',
        ['product_id'],
        postgresql_where=sa.text('is_enabled'),
    )

    op.create_table(
        'galleries',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, nullable=False, server_default=sa.text('gen_random_uuid()')),
        sa.Column('org_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('organizations.id', ondelete='CASCADE'), nullable=False),
        sa.Column('name', sa.Text(), nullable=False),
        sa.Column('slug', sa.Text(), nullable=False),
        sa.Column('is_public', sa.Boolean(), nullable=False, server_default=sa.text('false')),
        sa.Column('settings', postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column('created_by', postgresql.UUID(as_uuid=True), sa.ForeignKey('users.id', ondelete='SET NULL')),
        sa.Column('created_at', sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.Column('updated_at', sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.Column('deleted_at', sa.TIMESTAMP(timezone=True)),
        sa.UniqueConstraint('org_id', 'slug', name='uq_gallery_org_slug'),
    )

    op.create_table(
        'gallery_items',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, nullable=False, server_default=sa.text('gen_random_uuid()')),
        sa.Column('gallery_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('galleries.id', ondelete='CASCADE'), nullable=False),
        sa.Column('product_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('products.id', ondelete='CASCADE'), nullable=False),
        sa.Column('order_index', sa.Integer(), nullable=False, server_default=sa.text('0')),
        sa.Column('created_at', sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.UniqueConstraint('gallery_id', 'product_id', name='uq_gallery_product'),
    )
    op.create_index('ix_gallery_items_order', 'gallery_items', ['gallery_id', 'order_index'])

    op.create_table(
        'analytics_events',
        sa.Column('id', sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column('org_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('organizations.id', ondelete='CASCADE'), nullable=False),
        sa.Column('product_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('products.id', ondelete='SET NULL')),
        sa.Column('publish_link_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('publish_links.id', ondelete='SET NULL')),
        sa.Column('session_id', sa.String()),
        sa.Column('event_type', sa.String(), nullable=False),
        sa.Column('user_agent', sa.Text()),
        sa.Column('ip_hash', sa.String()),
        sa.Column('occurred_at', sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.Column('payload', postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
    )
    op.create_index('ix_analytics_events_org_time', 'analytics_events', ['org_id', 'occurred_at'])
    op.create_index('ix_analytics_events_product_time', 'analytics_events', ['product_id', 'occurred_at'])
    op.create_index(
        'ix_analytics_events_payload_gin',
        'analytics_events',
        ['payload'],
        postgresql_using='gin',
    )

    op.create_table(
        'analytics_daily_product',
        sa.Column('day', sa.Date(), nullable=False),
        sa.Column('org_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('organizations.id', ondelete='CASCADE'), nullable=False),
        sa.Column('product_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('products.id', ondelete='CASCADE'), nullable=False),
        sa.Column('views', sa.BigInteger(), nullable=False, server_default=sa.text('0')),
        sa.Column('engaged', sa.BigInteger(), nullable=False, server_default=sa.text('0')),
        sa.Column('adds_from_3d', sa.BigInteger(), nullable=False, server_default=sa.text('0')),
        sa.PrimaryKeyConstraint('day', 'org_id', 'product_id', name='pk_analytics_daily_product'),
    )

    op.create_table(
        'org_members',
        sa.Column('org_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('organizations.id', ondelete='CASCADE'), primary_key=True, nullable=False),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('users.id', ondelete='CASCADE'), primary_key=True, nullable=False),
        sa.Column('role', org_role_enum, nullable=False),
        sa.Column('created_at', sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.UniqueConstraint('org_id', 'user_id', name='uq_org_user'),
    )

    op.create_table(
        'auth_identities',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, nullable=False, server_default=sa.text('gen_random_uuid()')),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
        sa.Column('provider', auth_provider_enum, nullable=False),
        sa.Column('provider_user_id', sa.String(), nullable=False),
        sa.Column('email', postgresql.CITEXT(), nullable=False),
        sa.Column('last_login_at', sa.TIMESTAMP(timezone=True)),
        sa.Column('meta', postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column('created_at', sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.UniqueConstraint('provider', 'provider_user_id', name='uq_auth_identity_provider'),
    )

    op.create_table(
        'email_verifications',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, nullable=False, server_default=sa.text('gen_random_uuid()')),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
        sa.Column('token', sa.String(), nullable=False, unique=True),
        sa.Column('expires_at', sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column('used_at', sa.TIMESTAMP(timezone=True)),
    )

    op.create_table(
        'password_resets',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, nullable=False, server_default=sa.text('gen_random_uuid()')),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
        sa.Column('token', sa.String(), nullable=False, unique=True),
        sa.Column('expires_at', sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column('used_at', sa.TIMESTAMP(timezone=True)),
    )

    op.create_table(
        'activity_logs',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, nullable=False, server_default=sa.text('gen_random_uuid()')),
        sa.Column('org_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('organizations.id', ondelete='SET NULL')),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('users.id', ondelete='SET NULL')),
        sa.Column('action', sa.String(), nullable=False),
        sa.Column('target_type', sa.String()),
        sa.Column('target_id', sa.String()),
        sa.Column('ip_address', sa.String()),
        sa.Column('user_agent', sa.Text()),
        sa.Column('metadata', postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column('created_at', sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text('now()')),
    )
    op.create_index('ix_activity_logs_org_created_at', 'activity_logs', ['org_id', 'created_at'])

    op.create_table(
        'notifications',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, nullable=False, server_default=sa.text('gen_random_uuid()')),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
        sa.Column('type', sa.String(), nullable=False),
        sa.Column('title', sa.String(), nullable=False),
        sa.Column('body', sa.Text(), nullable=False),
        sa.Column('channel', notification_channel_enum, nullable=False, server_default=sa.text("'in_app'")),
        sa.Column('data', postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column('read_at', sa.TIMESTAMP(timezone=True)),
        sa.Column('created_at', sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text('now()')),
    )
    op.create_index(
        'ix_notifications_user_unread',
        'notifications',
        ['user_id'],
        postgresql_where=sa.text('read_at IS NULL'),
    )

    op.create_table(
        'user_notification_prefs',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, nullable=False, server_default=sa.text('gen_random_uuid()')),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
        sa.Column('notification_type', sa.String(), nullable=False),
        sa.Column('channels', postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column('muted', sa.Boolean(), nullable=False, server_default=sa.text('false')),
        sa.Column('updated_at', sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.UniqueConstraint('user_id', 'notification_type', name='uq_user_notification_pref'),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table('user_notification_prefs')
    op.drop_index('ix_notifications_user_unread', table_name='notifications')
    op.drop_table('notifications')
    op.drop_index('ix_activity_logs_org_created_at', table_name='activity_logs')
    op.drop_table('activity_logs')
    op.drop_table('password_resets')
    op.drop_table('email_verifications')
    op.drop_table('auth_identities')
    op.drop_table('org_members')
    op.drop_table('analytics_daily_product')
    op.drop_index('ix_analytics_events_payload_gin', table_name='analytics_events')
    op.drop_index('ix_analytics_events_product_time', table_name='analytics_events')
    op.drop_index('ix_analytics_events_org_time', table_name='analytics_events')
    op.drop_table('analytics_events')
    op.drop_index('ix_gallery_items_order', table_name='gallery_items')
    op.drop_table('gallery_items')
    op.drop_table('galleries')
    op.drop_index('ix_publish_links_product_enabled', table_name='publish_links')
    op.drop_table('publish_links')
    op.drop_index('ix_jobs_org', table_name='jobs')
    op.drop_index('ix_jobs_product_status', table_name='jobs')
    op.drop_table('jobs')
    op.drop_index('ix_hotspots_product_order', table_name='hotspots')
    op.drop_table('hotspots')
    op.drop_table('configurators')
    op.drop_table('products')
    op.drop_index('ix_assets_org_type', table_name='assets')
    op.drop_table('assets')
    op.drop_index('ix_license_user', table_name='license_assignments')
    op.drop_table('license_assignments')
    op.drop_index('ix_subscriptions_user', table_name='subscriptions')
    op.drop_table('subscriptions')
    op.drop_table('plans')
    op.drop_table('users')
    op.drop_index('ix_organizations_slug_unique', table_name='organizations')
    op.drop_table('organizations')

    auth_provider_enum.drop(op.get_bind(), checkfirst=True)
    notification_channel_enum.drop(op.get_bind(), checkfirst=True)
    hotspot_action_enum.drop(op.get_bind(), checkfirst=True)
    job_status_enum.drop(op.get_bind(), checkfirst=True)
    product_status_enum.drop(op.get_bind(), checkfirst=True)
    asset_type_enum.drop(op.get_bind(), checkfirst=True)
    license_status_enum.drop(op.get_bind(), checkfirst=True)
    subscription_status_enum.drop(op.get_bind(), checkfirst=True)
    org_role_enum.drop(op.get_bind(), checkfirst=True)
