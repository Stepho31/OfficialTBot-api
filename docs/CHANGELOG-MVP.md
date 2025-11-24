# CHANGELOG (MVP)

- Added `/stripe/checkout` endpoint to generate tiered Checkout Sessions using configured price IDs.
- Extended Stripe webhook handling to map Tier-1/Tier-2 plans, persist subscription state, and update user entitlements.
- Introduced entitlement computation helpers (beta window, waitlist grants, admin trading guard) and new `/v1/me`, `/v1/subscription`, `/v1/entitlements` endpoints.
- Added AES-GCM broker credential storage with `/v1/me/broker` (JWT) and `/v1/internal/broker` (bot key) routes, plus encryption tests.
- Created `/v1/internal/entitlements`, `/v1/internal/trades`, and `/v1/internal/equity` for agent sync; trades table now references `user_id` with idempotent constraints.
- Added `ADMIN_EMAILS` support; matching users persist as `role=ADMIN`, bypassing trading/paywall checks and receiving full entitlements.
