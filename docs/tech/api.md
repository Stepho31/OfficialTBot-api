# API Inventory

## Active Routes
| Method | Path | Handler | Auth | Inputs / Outputs | DB Tables (R/W) | Idempotency Keys | Errors |
| --- | --- | --- | --- | --- | --- | --- | --- |
| GET | `/healthz` | `app.main.healthz` | none | **In:** none<br>**Out:** `{"ok": true}` | direct connection ping (`SELECT 1`) only | none | DB connection failure → 500 |
| POST | `/stripe/create-checkout-session` | `app.stripe_checkout.create_checkout_session` | none | **In:** none<br>**Out:** `CheckoutSessionOut` → `{ url: str }` | none | none | Stripe client exceptions → 400 |
| POST | `/webhooks/stripe` | `app.stripe_webhooks.stripe_webhook` | none (relies on `stripe-signature` header) | **In:** raw Stripe webhook payload + `stripe-signature` header<br>**Out:** `{ "received": true }` (or `{ "ok": true }` for ignored events) | `users` (r/w), `subscriptions` (r/w) | none | 400 invalid signature; implicit 500s on DB errors |
| GET | `/access/paid-emails` | `app.access.paid_emails` | none | **In:** none<br>**Out:** `PaidEmailsOut` → `{ emails: EmailStr[] }` | `subscriptions` (r), `users` (r) | none | none |
| POST | `/accounts` | `app.accounts.connect_account` | bearer | **In:** `AccountConnectIn` → `{ account_id: str, token?: str, label?: str }`<br>Optional OANDA validation via HTTP GET<br>**Out:** `{ ok: true, account_id: str }` | `accounts` (w) | none (duplicate insert fails unique constraint) | 400 invalid OANDA account/token; 401 missing/invalid bearer |
| GET | `/accounts/status` | `app.accounts.account_status` | bearer | **In:** query `account_id: str`<br>**Out:** `AccountStatusOut` → `{ account_id: str, connected: bool, last_checked: datetime|null }` | `accounts` (r) | none | 401 missing/invalid bearer; 404 account not found |
| GET | `/dashboard/summary` | `app.dashboard.summary` | bearer (active subscription) | **In:** query `account_id: int`<br>**Out:** `DashboardSummaryOut` → `{ account_id: int, wtd_pnl: float, wins: int, losses: int, win_rate: float, balance?: float, equity?: float }` | `accounts` (r), `trades` (r), `equity_snapshots` (r) | none | 401/402 missing auth or inactive subscription; 404 account not found |
| GET | `/dashboard/open-trades` | `app.dashboard.open_trades` | bearer (active subscription) | **In:** query `account_id: int`<br>**Out:** list of `{ instrument?: str, side?: str, units?: int, opened_at?: datetime, closed_at?: datetime, entry_price?: float, exit_price?: float, pnl_net?: float }` | `accounts` (r), `trades` (r) | none | 401/402 missing auth or inactive subscription; 404 account not found |
| GET | `/dashboard/trades` | `app.dashboard.trades` | bearer (active subscription) | **In:** query `account_id: int`, `from_dt?: str`, `to_dt?: str`<br>**Out:** list of `{ instrument?: str, side?: str, units?: int, opened_at?: datetime, closed_at?: datetime, entry_price?: float, exit_price?: float, pnl_net?: float }` | `accounts` (r), `trades` (r) | none | 401/402 missing auth or inactive subscription; 404 account not found |
| GET | `/dashboard/equity-series` | `app.dashboard.equity_series` | bearer (active subscription) | **In:** query `account_id: int`, `window: str = "30d"`<br>**Out:** list of `{ taken_at: datetime, equity?: float }` | `accounts` (r), `equity_snapshots` (r) | none | 401/402 missing auth or inactive subscription; 404 account not found |
| GET | `/proofs/daily/latest` | `app.proofs.latest_daily` | none | **In:** none<br>**Out:** `{ date, hash, signature, public_key, ipfs_cid }` (all nullable) | none | none | none |

## Dormant or Missing Surfaces
- `app.api_v1.router` and `app.profile.router` are defined but never included in `app.main`; every handler there is currently unreachable.
- `app.api_ingest.router` (intended for bot ingestion) is not mounted and references `require_bot_key` plus `app.models.Signal`, neither of which exist—bot endpoints cannot run until both are implemented.
- Alembic migrations create a `signals` table, but no SQLAlchemy `Signal` model or handlers actively use it.

## Planned Additions (Gap List)
- `POST /api/connections/upsert` – Accept encrypted OANDA credentials (token + account id) and upsert per-user account records.
- `POST /api/user/trading/toggle` – Persist trade mode, risk caps, and user consent timestamp for entitlement checks.
- `GET /api/portfolio/overview`, `GET /api/positions`, `GET /api/trades` – User-scoped read APIs that surface current holdings, positions, and trade history behind auth.
- `POST /api/bot/trade/upsert` – Bot-authenticated ingest path (guarded by `x-bot-key`) that upserts trades idempotently by external identifiers.
- `POST /api/stripe/webhook` – Move Stripe webhook under the `/api` namespace and connect events to entitlements/subscriptions.

## Environment Variables
| Name | Purpose |
| --- | --- |
| `DATABASE_URL` | SQLAlchemy connection string used by `app.db.engine` and startup table creation. |
| `STRIPE_SECRET_KEY` | API key for Stripe client calls (`stripe_checkout`, `stripe_webhooks`). |
| `STRIPE_WEBHOOK_SECRET` | Shared secret to validate inbound Stripe webhook signatures. |
| `FRONTEND_ORIGIN` | Allowed CORS origin and the redirect base for Stripe checkout success/cancel URLs. |
| `JWT_SECRET` | HS256 signing key for `app.security` token issuance and validation. |
| `ENCRYPTION_KEY` | Fernet key used to encrypt/decrypt broker tokens in `app.crypto`. |
| `OANDA_ENV` | Chooses OANDA API base URL (`practice` vs `live`) for account verification. |
| `EMAIL_FROM` | Default sender address for outbound email notifications. |
| `SMTP_HOST` | Hostname for the SMTP relay used by `app.emails`. |
| `SMTP_PORT` | Port for the SMTP relay. |
| `DEV_ALLOW_ALL_CORS` | When true, overrides CORS allowlist with `*` for local development.

