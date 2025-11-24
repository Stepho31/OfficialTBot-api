# Autopip API – Architecture Notes (MVP)

## Data Model Highlights
- `users`: stores login identity, `role` (`user` or `admin`), `stripe_customer_id`, and a persistent `has_tier1` flag for lifetime email access.
- `subscriptions`: records Stripe subscription state. Tier-2 automation rows keep `stripe_subscription_id`, `status`, `current_period_end`, and `is_recurring`.
- `accounts`: user-scoped broker connections holding encrypted credentials.
- `broker_credentials`: AES-GCM–encrypted OANDA tokens keyed per user (unique row per user).
- `trades`: now references both `account_id` and `user_id`, ensuring idempotent upserts via `(user_id, external_id)` for agent syncs.
- `equity_snapshots`: per-account equity checkpoints, unique on `(account_id, taken_at)`.
- `signals`: ingestion store for bot-generated trade signals (idempotent on `signal_id`).

## Stripe Checkout & Webhooks
- Landing/UI call `POST /stripe/checkout` with `{ tier: "TIER1" | "TIER2" }`.
- The API creates a Stripe Checkout Session with tier metadata and correct price IDs.
- Webhook `POST /webhooks/stripe` verifies signatures, then:
  - `checkout.session.completed`: upserts the user, records Tier-1 purchases, and seeds Tier-2 subscriptions.
  - `customer.subscription.*`: keeps Tier-2 status, recurring flag, and billing period end in sync.
  - `invoice.payment_failed`: marks the subscription as `past_due`.

## Broker Credential Storage
- `PUT /v1/me/broker` allows Tier-2 users to save `oandaAccountId` + API key.
- Keys are encrypted with AES-GCM using `BROKER_SECRET_KEY` (base64-encoded 32-byte key). Cipher, IV, and tag are persisted separately.
- `GET /v1/me/broker` returns only presence metadata (`hasBrokerCreds`, masked account id, timestamps)—never the raw key.
- `GET /v1/internal/broker` (guarded by `x-bot-key`) decrypts and returns credentials for the trading agent.
- All server-to-server access uses the shared bot key header; missing or mismatched keys return 403.

## Internal Trading & Equity Sync
- `/v1/internal/entitlements`: server-to-server entitlement read for the agent.
- `/v1/internal/trades`: idempotent upsert keyed by `(userId, externalTradeId)`; accepts symbol, side, size, entry/exit data, and status.
- `/v1/internal/equity`: maintains equity snapshots per user/account; repeated timestamps update in place.

## Admin Accounts
- Configure `ADMIN_EMAILS` (comma-separated) to elevate specific logins at authentication time.
- Elevated users persist with `role = 'ADMIN'`, bypassing subscription checks and trading entitlements.
- Admins always receive email signals and retain trading rights regardless of beta state or Stripe status.

## Entitlement Rules
- `compute_entitlements` derives booleans on read—no materialized entitlement table required.
- `canReceiveEmailSignals` is true when:
  - the user has purchased Tier-1, or
  - Tier-2 subscription is active, or
  - Beta waitlist grant applies (see below).
- `canTrade` is true when Tier-2 is active **and** (outside beta or the user is an admin). Admins are always allowed to trade.
- `shouldEmailUserSignal(user_id)` centralizes the logic for downstream dispatchers and internal routes.

## Beta Window Logic (2025-12-17 → 2026-02-12)
- During beta, waitlist emails (Mailchimp list) get Tier-1 email access for free.
- Only admins may run automation (`canTrade`) during beta.
- After beta end, waitlist grants stop; users must purchase Tier-1 for ongoing signals.
- Mailchimp lookups gracefully degrade (returning `False`) when credentials are absent.
