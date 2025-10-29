-- =========================================================
-- Rivollo — PostgreSQL Schema (simple, extensible)
-- =========================================================

-- Extensions
CREATE EXTENSION IF NOT EXISTS pgcrypto; -- gen_random_uuid()
CREATE EXTENSION IF NOT EXISTS citext;   -- case-insensitive email

-- ======================
-- Core: Organizations & Users
-- ======================
CREATE TABLE IF NOT EXISTS organizations (
  id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  name         TEXT NOT NULL,
  slug         TEXT NOT NULL,
  branding     JSONB NOT NULL DEFAULT '{}',
  created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
  deleted_at   TIMESTAMPTZ
);
CREATE UNIQUE INDEX IF NOT EXISTS org_slug_uniq ON organizations (slug) WHERE deleted_at IS NULL;

CREATE TABLE IF NOT EXISTS users (
  id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  email         CITEXT UNIQUE NOT NULL,
  password_hash TEXT,                         -- NULL for Google-only accounts
  name          TEXT,
  avatar_url    TEXT,
  created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
  deleted_at    TIMESTAMPTZ
);

CREATE TABLE IF NOT EXISTS org_members (
  org_id     UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
  user_id    UUID NOT NULL REFERENCES users(id)         ON DELETE CASCADE,
  role       TEXT NOT NULL CHECK (role IN ('owner','admin','member')),
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY (org_id, user_id)
);

-- ======================
-- Plans, Subscriptions (user-scoped), Licenses
-- ======================
CREATE TABLE IF NOT EXISTS plans (
  id      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  code    TEXT UNIQUE NOT NULL,              -- 'free','pro','enterprise'
  name    TEXT NOT NULL,
  quotas  JSONB NOT NULL DEFAULT '{}'        -- default per-user limits
  -- e.g., { "max_products": 50, "max_ai_credits_month": 50, "monthly_view_quota": 25000 }
);

-- Subscription belongs to a USER (not an organization)
CREATE TABLE IF NOT EXISTS subscriptions (
  id                     UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id                UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  plan_id                UUID NOT NULL REFERENCES plans(id),
  status                 TEXT NOT NULL CHECK (status IN ('trialing','active','canceled','past_due')),
  seats_purchased        INT  NOT NULL DEFAULT 1,
  billing                JSONB NOT NULL DEFAULT '{}',  -- payment provider ref, invoices, etc.
  current_period_start   TIMESTAMPTZ NOT NULL DEFAULT now(),
  current_period_end     TIMESTAMPTZ,
  trial_end_at           TIMESTAMPTZ,
  renews_at              TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS subs_user_idx ON subscriptions (user_id);

-- Each seat granted to a user. Limits & usage are applied per-user here.
CREATE TABLE IF NOT EXISTS license_assignments (
  id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  subscription_id  UUID NOT NULL REFERENCES subscriptions(id) ON DELETE CASCADE,
  user_id          UUID NOT NULL REFERENCES users(id)         ON DELETE CASCADE,
  status           TEXT NOT NULL CHECK (status IN ('invited','active','revoked')) DEFAULT 'active',
  limits           JSONB NOT NULL DEFAULT '{}',               -- effective caps for this user
  usage_counters   JSONB NOT NULL DEFAULT '{}',               -- counters (reset each period in app logic)
  created_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (subscription_id, user_id)
);
CREATE INDEX IF NOT EXISTS license_user_idx ON license_assignments (user_id);

-- ============
-- Assets & Catalog
-- ============
CREATE TABLE IF NOT EXISTS assets (
  id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  org_id        UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
  type          TEXT NOT NULL CHECK (type IN ('image','model','mask','thumbnail')),
  storage       TEXT NOT NULL DEFAULT 'azure_blob',          -- or 's3','gcs','local'
  url           TEXT NOT NULL,
  mime_type     TEXT,
  size_bytes    BIGINT,
  width         INT,
  height        INT,
  checksum_sha256 TEXT,
  created_by    UUID REFERENCES users(id),
  created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS assets_org_type_idx ON assets (org_id, type);

CREATE TABLE IF NOT EXISTS products (
  id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  org_id         UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
  name           TEXT NOT NULL,
  slug           TEXT NOT NULL,
  status         TEXT NOT NULL DEFAULT 'draft'
                 CHECK (status IN ('draft','processing','ready','published','unpublished','archived')),
  cover_asset_id UUID REFERENCES assets(id),
  model_asset_id UUID REFERENCES assets(id),
  tags           TEXT[] DEFAULT '{}',
  metadata       JSONB NOT NULL DEFAULT '{}',
  published_at   TIMESTAMPTZ,
  created_by     UUID REFERENCES users(id),
  created_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
  deleted_at     TIMESTAMPTZ,
  UNIQUE (org_id, slug)
);

CREATE TABLE IF NOT EXISTS configurators (
  id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  product_id   UUID UNIQUE NOT NULL REFERENCES products(id) ON DELETE CASCADE,
  settings     JSONB NOT NULL DEFAULT '{}'    -- viewer and UI settings, variants, materials
);

-- Hotspots with coordinates + styling
CREATE TABLE IF NOT EXISTS hotspots (
  id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  product_id     UUID NOT NULL REFERENCES products(id) ON DELETE CASCADE,
  label          TEXT NOT NULL,
  description    TEXT NOT NULL,
  pos_x          DOUBLE PRECISION NOT NULL,
  pos_y          DOUBLE PRECISION NOT NULL,
  pos_z          DOUBLE PRECISION NOT NULL,
  text_font      TEXT,
  text_color     TEXT,
  bg_color       TEXT,
  action_type    TEXT NOT NULL CHECK (action_type IN ('none','link','material-switch','variant-switch','text-only')),
  action_payload JSONB NOT NULL DEFAULT '{}',
  order_index    INT NOT NULL DEFAULT 0,
  created_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
  CHECK (pos_x BETWEEN -1.0 AND 1.0),
  CHECK (pos_y BETWEEN -1.0 AND 1.0),
  CHECK (pos_z BETWEEN -1.0 AND 1.0)
);
CREATE INDEX IF NOT EXISTS hotspots_product_order_idx ON hotspots (product_id, order_index);

CREATE TABLE IF NOT EXISTS jobs (
  id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  org_id          UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
  product_id      UUID NOT NULL REFERENCES products(id)       ON DELETE CASCADE,
  image_asset_id  UUID NOT NULL REFERENCES assets(id),
  model_asset_id  UUID REFERENCES assets(id),
  status          TEXT NOT NULL DEFAULT 'pending'
                  CHECK (status IN ('pending','processing','completed','failed')),
  engine          TEXT,
  gpu_type        TEXT,
  credits_used    INT NOT NULL DEFAULT 1,
  started_at      TIMESTAMPTZ,
  completed_at    TIMESTAMPTZ,
  error           JSONB,
  created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS jobs_product_status_idx ON jobs (product_id, status);
CREATE INDEX IF NOT EXISTS jobs_org_idx ON jobs (org_id);

CREATE TABLE IF NOT EXISTS publish_links (
  id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  product_id     UUID NOT NULL REFERENCES products(id) ON DELETE CASCADE,
  public_id      TEXT UNIQUE NOT NULL,
  is_enabled     BOOLEAN NOT NULL DEFAULT TRUE,
  expires_at     TIMESTAMPTZ,
  password_hash  TEXT,
  iframe_allowed BOOLEAN NOT NULL DEFAULT TRUE,
  view_count     BIGINT NOT NULL DEFAULT 0,
  last_viewed_at TIMESTAMPTZ,
  created_at     TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS publish_product_enabled_idx ON publish_links (product_id) WHERE is_enabled;

-- =========
-- Galleries
-- =========
CREATE TABLE IF NOT EXISTS galleries (
  id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  org_id      UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
  name        TEXT NOT NULL,
  slug        TEXT NOT NULL,
  is_public   BOOLEAN NOT NULL DEFAULT FALSE,
  settings    JSONB NOT NULL DEFAULT '{}',
  created_by  UUID REFERENCES users(id),
  created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
  deleted_at  TIMESTAMPTZ,
  UNIQUE (org_id, slug)
);

CREATE TABLE IF NOT EXISTS gallery_items (
  id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  gallery_id   UUID NOT NULL REFERENCES galleries(id) ON DELETE CASCADE,
  product_id   UUID NOT NULL REFERENCES products(id)  ON DELETE CASCADE,
  order_index  INT NOT NULL DEFAULT 0,
  created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (gallery_id, product_id)
);
CREATE INDEX IF NOT EXISTS gallery_items_order_idx ON gallery_items (gallery_id, order_index);

-- ==========
-- Analytics
-- ==========
CREATE TABLE IF NOT EXISTS analytics_events (
  id               BIGSERIAL PRIMARY KEY,
  org_id           UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
  product_id       UUID REFERENCES products(id) ON DELETE SET NULL,
  publish_link_id  UUID REFERENCES publish_links(id) ON DELETE SET NULL,
  session_id       TEXT,
  event_type       TEXT NOT NULL,
  user_agent       TEXT,
  ip_hash          TEXT,
  occurred_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
  payload          JSONB NOT NULL DEFAULT '{}'
);
CREATE INDEX IF NOT EXISTS ae_org_time_idx ON analytics_events (org_id, occurred_at);
CREATE INDEX IF NOT EXISTS ae_product_time_idx ON analytics_events (product_id, occurred_at);
CREATE INDEX IF NOT EXISTS ae_payload_gin ON analytics_events USING GIN (payload);

CREATE TABLE IF NOT EXISTS analytics_daily_product (
  day           DATE NOT NULL,
  org_id        UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
  product_id    UUID NOT NULL REFERENCES products(id)      ON DELETE CASCADE,
  views         BIGINT NOT NULL DEFAULT 0,
  engaged       BIGINT NOT NULL DEFAULT 0,
  adds_from_3d  BIGINT NOT NULL DEFAULT 0,
  PRIMARY KEY (day, org_id, product_id)
);
CREATE INDEX IF NOT EXISTS adp_org_day_idx ON analytics_daily_product (org_id, day);

-- ==========================
-- Auth (Google + Email flows)
-- ==========================
CREATE TABLE IF NOT EXISTS auth_identities (
  id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id           UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  provider          TEXT NOT NULL CHECK (provider IN ('google','email')),
  provider_user_id  TEXT NOT NULL,
  email             CITEXT NOT NULL,
  last_login_at     TIMESTAMPTZ,
  meta              JSONB NOT NULL DEFAULT '{}',
  UNIQUE (provider, provider_user_id)
);

CREATE TABLE IF NOT EXISTS email_verifications (
  id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id     UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  token       TEXT UNIQUE NOT NULL,
  expires_at  TIMESTAMPTZ NOT NULL,
  used_at     TIMESTAMPTZ
);

CREATE TABLE IF NOT EXISTS password_resets (
  id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
