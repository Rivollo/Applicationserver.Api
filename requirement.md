
# Rivollo — Functional Requirements & User Stories (v2)

## 0) One-liner

Turn 2D product photos into interactive 3D configurators with hotspots, variants, animations, shareable links, and analytics — all under per-user plans and licensing.

---

## 1) Scope

**In-scope (MVP)**
Auth (email + Google), per-user subscriptions + licenses, product pipeline (upload → AI 3D job → configure → publish), hotspots (coords + styling), shareable viewer, analytics, activity logs, and notifications.

**Out-of-scope (MVP)**
Multi-image reconstruction, CAD import, payment gateway, advanced role permissions beyond simple org membership.

---

## 2) Personas & Goals

* **Creator / Seller (Primary)** – Individual or team member who uploads photos, generates 3D models, and shares links.
* **Viewer / Shopper** – Customer who views, rotates, or interacts with the 3D product.
* **Admin / Owner** – Controls subscription, manages seats (licenses), monitors analytics, and branding.

---

## 3) End-to-End Flows

### A) Authentication & Account Setup

* **Email / Password** (classic signup via `users` + `auth_identities`)
* **Google OAuth** (`provider = google`)
* **Verification / Reset**:

  * Email verification → `email_verifications` token.
  * Forgot password → `password_resets` token.
* **Activity Log**: login, signup, reset events recorded in `activity_logs`.

**Acceptance:**

* Login returns JWT `{ success, data: { user, token } }`.
* Google sign-in auto-creates user if new.
* Verification and password reset tokens expire after 15 min.

---

### B) Subscription & License Management (User-Scoped)

* Each **subscription** belongs to a **user** (not org).
* Each subscription has multiple **license assignments** for invited collaborators.
* **Usage & limits** apply per-user, not per-plan.
* Example per-user caps: `max_products`, `max_ai_credits_month`, `max_public_views`.

**Endpoints:**

* `/plans`, `/subscriptions`, `/licenses`
* `GET /licenses/me` → returns current limits + usage.

**Acceptance:**

* Creating product checks `license_assignments.usage_counters.products` < `limits.max_products`.
* Revoked license → 403 on any resource write.
* Trial plans auto-convert after 7 days.

---

### C) Add → Generate → Configure → Publish

1. **Create Product** – minimal metadata (`name`, `slug`, `status=draft`) → linked to org + creator user.
2. **Upload Photo** → creates `asset (type=image)`; optional background removal step.
3. **AI 3D Job** → creates `job` row (`status=pending→processing→completed|failed`).
4. **Configure 3D View** → add materials, variants, camera presets.
5. **Hotspots** → precise `pos_x,pos_y,pos_z`, label, description, font + colors + action.
6. **Publish** → generates `publish_link` (`public_id`, `is_enabled`) for sharing.

**Acceptance:**

* Cannot publish without completed 3D model.
* Hotspot positions must be between -1 and 1 (normalized model space).
* Each publish creates activity log (“product_published”) and notification to owner.

---

### D) Viewer, Sharing & Interaction

* **Viewer** supports orbit, zoom, variant & material switching, hotspots with styled labels.
* **Public URL** (from `publish_links.public_id`) can be shared via copy/WhatsApp.
* Optional password protection on public link.
* Viewer telemetry → `analytics_events` table.

**Acceptance:**

* Unpublishing disables link instantly.
* Each unique viewer triggers a `viewer.view` event.
* Hotspot click records `hotspot.open` event with payload `{ id, label }`.

---

### E) Analytics & Dashboard

* Metrics (aggregated per product & per day):

  * `views`, `engaged`, `adds_from_3d`, `top_hotspots`, `best_variants`.
* Raw events → `analytics_events`; roll-ups → `analytics_daily_product`.
* Date range filters; Pro users unlock advanced KPIs & exports.

**Acceptance:**

* Free plan → basic metrics only.
* Premium → advanced KPIs + geo/device breakdown.
* Dashboard page loads cached 24 h summary (configurable).

---

### F) Notifications & Activity Logs

* **Notifications** (`notifications`):

  * Triggered by job completion, quota warnings, or shared link activity.
  * Channels: in-app (default) / email / push (from `user_notification_prefs`).
* **Activity Logs** (`activity_logs`):

  * Captures create/update/delete actions across products, jobs, links, auth.
  * Includes actor user ID, target type & ID, timestamp, IP, user_agent.

**Acceptance:**

* Each user sees their own unread notifications (`read_at IS NULL`).
* User prefs can mute notification types (e.g., `"job.completed"`).
* Logs retained 90 days.

---

### G) Organization & Assets

* **Organizations** group assets & products (for branding and team visibility).
* **Org Members** have simple roles: owner / admin / member.
* Assets (images, models) are org-scoped, referenced in jobs/products.

**Acceptance:**

* Member without license can view but not edit/publish.
* Owner can transfer product ownership between users of same org.

---

## 4) User Stories

### Creator / Seller

* As a user, I can upload a 2D image and generate a 3D model with one click.
* As a user, I can configure hotspots with coordinates, text, and colors to guide customers.
* As a user, I can publish my product and share a public link.
* As a user, I can view analytics of who interacted with my 3D model.
* As a user, I get a notification when my 3D job completes.

### Admin / Owner

* As a subscription owner, I can purchase additional licenses and assign them to users.
* As an admin, I can monitor per-user usage and revoke inactive seats.
* As an admin, I can view org-level activity logs for transparency.

### Viewer / Shopper

* As a shopper, I can rotate, zoom, switch variants, and tap hotspots to learn more.
* As a shopper, I can click the CTA link to visit the seller’s page.

---

## 5) Key Acceptance Criteria (Summary)

| Area                   | Given / When / Then                                                                                               |
| ---------------------- | ----------------------------------------------------------------------------------------------------------------- |
| **License Limits**     | *Given* user exceeds `max_products`, *when* they try to create a new product, *then* return 403 `LIMIT_EXCEEDED`. |
| **3D Job Lifecycle**   | *Given* job pending, *when* it completes, *then* update status → completed and notify user.                       |
| **Hotspot Validation** | *Given* pos_x > 1.0, *when* saving, *then* return 400 `INVALID_COORDINATE`.                                       |
| **Analytics Access**   | *Given* Free plan user, *when* requesting advanced KPIs, *then* return 403.                                       |
| **Notifications**      | *Given* new event `job.completed`, *when* preferences allow, *then* insert notification row and send in-app.      |

---

## 6) Non-Functional Requirements

* **Performance** – 3D viewer optimized for mobile (≤ 1 MB GLB load target).
* **Security** – JWT auth, password hashing (Argon2), HTTPS only.
* **Auditability** – All user actions → `activity_logs`.
* **Scalability** – Each user’s quota enforcement purely on `license_assignments`.
* **Accessibility** – Hotspot text contrast and keyboard navigation.

---

## 7) Core Data Entities (Aligned to Schema)

`users`, `auth_identities`, `email_verifications`, `password_resets`,
`plans`, `subscriptions`, `license_assignments`,
`organizations`, `org_members`,
`products`, `assets`, `jobs`, `configurators`, `hotspots`, `publish_links`,
`analytics_events`, `analytics_daily_product`,
`activity_logs`, `notifications`, `user_notification_prefs`.

---

## 8) Example Data Flow

**User uploads photo → 3D job runs → model ready → publish link shared → viewers interact → analytics recorded → creator notified → usage updated → activity logged.**

