# Database Tables

## `users`
- **Columns:**
  - `id` (PK, serial)
  - `email` (unique, text)
  - `status` (text, default `PENDING_PASSWORD`)
  - `email_verified` (bool, default `false`)
  - `created_at` (timestamp, default `now()`)
- **Related constraints:** unique index on `email`.
- **Used by:**
  - `POST /webhooks/stripe` upserts users by `email`.
  - `GET /access/paid-emails` fetches emails of subscribed users.
  - Auth dependencies (`auth_required`, `subscription_required`) resolve bearer tokens to `User` rows.

## `subscriptions`
- **Columns:**
  - `id` (PK, serial)
  - `user_id` (FK → `users.id`)
  - `stripe_customer_id` (text, nullable)
  - `stripe_subscription_id` (text, nullable, treated as unique in practice)
  - `status` (text)
  - `current_period_end` (timestamp, nullable)
  - `plan` (text, nullable)
  - `created_at` (timestamp, default `now()`)
- **Related constraints:** FK on `user_id` → `users.id`.
- **Used by:**
  - `POST /webhooks/stripe` reads & writes `status`, `plan`, `stripe_*` columns.
  - `GET /access/paid-emails` selects active/trialing statuses.
  - `subscription_required` enforces status ∈ {`trialing`, `active`} for dashboard routes.

## `accounts`
- **Columns:**
  - `id` (PK, serial)
  - `user_id` (FK → `users.id`)
  - `broker` (text, default `OANDA`)
  - `account_id` (text)
  - `token_encrypted` (bytea/varbinary, nullable)
  - `label` (text, nullable)
  - `is_primary` (bool, default `true`)
  - `created_at` (timestamp, default `now()`)
- **Related constraints:**
  - FK on `user_id` → `users.id`.
  - Unique constraint `uq_accounts_user_broker_account` on (`user_id`, `account_id`).
- **Used by:**
  - `POST /accounts` inserts `user_id`, `account_id`, `token_encrypted`, `label`.
  - `GET /accounts/status` queries by `account_id` and `user_id` to check `token_encrypted`.
  - All `/dashboard/*` endpoints ensure ownership via `user_id` filter and then read `id` for joins.
  - `app.api_ingest._resolve_account` (dormant) expects to look up internal ids by `account_id`.

## `trades`
- **Columns:**
  - `id` (PK, serial)
  - `account_id` (FK → `accounts.id`)
  - `instrument` (text, nullable)
  - `side` (text, nullable)
  - `units` (int, nullable)
  - `opened_at` (timestamp, nullable)
  - `closed_at` (timestamp, nullable)
  - `entry_price`, `exit_price`, `commission`, `spread_cost`, `slippage_cost`, `pnl_net` (numeric, nullable)
  - `reason_open`, `reason_close` (text, nullable)
  - `external_id` (text, nullable, unique per (`account_id`, `external_id`) — defined in migrations but missing from the ORM class)
- **Related constraints:**
  - FK on `account_id` → `accounts.id`.
  - Unique constraint `uq_trades_account_external` on (`account_id`, `external_id`).
  - Index `ix_trades_account_closed` on (`account_id`, `closed_at`).
- **Used by:**
  - `/dashboard/*` endpoints aggregate, filter, and serialize trade metrics (`instrument`, `side`, `units`, `opened_at`, `closed_at`, `entry_price`, `exit_price`, `pnl_net`).
  - `app.api_ingest.ingest_trade` (unmounted) depends on the `external_id` column for idempotent upserts.

## `equity_snapshots`
- **Columns:**
  - `id` (PK, serial)
  - `account_id` (FK → `accounts.id`)
  - `taken_at` (timestamp, nullable)
  - `balance`, `equity`, `margin_used` (numeric, nullable)
- **Related constraints:**
  - FK on `account_id` → `accounts.id`.
  - Unique constraint `uq_equitysnapshots_account_taken` on (`account_id`, `taken_at`).
  - Index `ix_equitysnapshots_account_taken` on (`account_id`, `taken_at`).
- **Used by:**
  - `GET /dashboard/summary` fetches the most recent row for balance/equity.
  - `GET /dashboard/equity-series` streams time-series data.
  - `app.api_ingest.ingest_snapshot` (unmounted) reads/writes rows keyed by (`account_id`, `taken_at`).

## `signals`
- **Columns (per Alembic migrations):**
  - `id` (PK, serial)
  - `signal_id` (text, unique)
  - `created_at` (timestamp with time zone, default `now()`)
  - `symbol` (text, nullable)
  - `direction` (text, nullable)
  - `entry`, `sl`, `tp` (numeric, nullable)
  - `rationale` (text, nullable)
- **Related constraints:** unique constraint on `signal_id`.
- **Used by:** intended for `app.api_ingest.ingest_signal`, but the ORM `Signal` model is currently missing, so the handler cannot function.

## `tier1_cache`
- **Columns:**
  - `email` (PK, text)
  - `active` (bool)
  - `refreshed_at` (timestamp, default `now()`)
- **Used by:** No active handler references this table yet; likely intended for future entitlement/allowlist caching.

## Missing ORM Definitions
- `NotificationPreferences` and `TradingEntitlements` are referenced in `app.profile` but no models or tables exist for them.
- A SQLAlchemy `Signal` model is absent even though migrations create the table and handlers attempt to import it.


