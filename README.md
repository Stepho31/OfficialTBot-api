# Autopip API (Starter)

FastAPI backend for subscriptions (Stripe), OANDA connect (one-time token paste), and read-only dashboard endpoints. Your trading bot writes `trades` and `equity_snapshots` to the same DB.

## Quick Start
1. `python -m venv .venv && source .venv/bin/activate`
2. `pip install -r requirements.txt`
3. Copy `.env.example` to `.env` and fill in values (DB URL, Stripe keys, Fernet key, etc.).
4. `make run`  ➜ http://localhost:8000/healthz

## Dev Tips
- Replace `price_25_month_placeholder` in `app/stripe_checkout.py` with your Stripe **Price ID**.
- In dev, you can run: `make stripe` then run a checkout and watch webhooks flow to `/webhooks/stripe`.
- The bot should write trades/snapshots to this DB so `/dashboard/*` endpoints have data.

## Endpoints (high level)
- `POST /stripe/create-checkout-session`
- `POST /webhooks/stripe`
- `GET /access/paid-emails`
- `POST /accounts` + `GET /accounts/status`
- `GET /dashboard/summary|open-trades|trades|equity-series`
- `GET /healthz`

## Security
- OANDA tokens are encrypted at rest via Fernet (see `ENCRYPTION_KEY`).
- JWT for user sessions (stub in `security.py`; expand as needed).
- CORS is restricted to `FRONTEND_ORIGIN` unless `DEV_ALLOW_ALL_CORS=True` (dev only!).
