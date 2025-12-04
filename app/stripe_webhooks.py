import os
from datetime import datetime, timezone
from typing import Any, Optional

import stripe
from fastapi import APIRouter, HTTPException, Request
from sqlalchemy.orm import Session

from app.db import SessionLocal
from app.models import Subscription, User
from app.settings import settings

router = APIRouter(prefix="/webhooks", tags=["stripe"])
stripe.api_key = settings.STRIPE_SECRET_KEY


def log_render_debug_info():
    """Debug helper to verify script is running on Render."""
    print("=" * 60)
    print("🔍 RENDER DEBUG MODE ENABLED")
    print("=" * 60)
    
    # Current working directory
    cwd = os.getcwd()
    print(f"📁 Current working directory: {cwd}")
    
    # DRY_RUN and TRADING_MODE
    dry_run = os.getenv("DRY_RUN", "not set")
    trading_mode = os.getenv("TRADING_MODE", "not set")
    print(f"🔧 DRY_RUN: {dry_run}")
    print(f"🔧 TRADING_MODE: {trading_mode}")
    
    # Required env vars (just show ✅/❌, don't print secrets)
    oanda_api_key = "✅" if os.getenv("OANDA_API_KEY") else "❌"
    oanda_account_id = "✅" if os.getenv("OANDA_ACCOUNT_ID") else "❌"
    openai_api_key = "✅" if os.getenv("OPENAI_API_KEY") else "❌"
    
    print(f"🔑 OANDA_API_KEY: {oanda_api_key}")
    print(f"🔑 OANDA_ACCOUNT_ID: {oanda_account_id}")
    print(f"🔑 OPENAI_API_KEY: {openai_api_key}")
    
    print("=" * 60)


def _map_price_to_tier(price_id: Optional[str]) -> Optional[str]:
    """Backward compatibility: map price_id to tier (fallback when lookup_key is not available)."""
    if not price_id:
        return None
    if settings.STRIPE_PRICE_TIER1_ONETIME and price_id == settings.STRIPE_PRICE_TIER1_ONETIME:
        return "TIER1"
    if settings.STRIPE_PRICE_TIER2_MONTHLY and price_id == settings.STRIPE_PRICE_TIER2_MONTHLY:
        return "TIER2"
    return None


def _extract_lookup_key_from_price(price: Any) -> Optional[str]:
    """Extract lookup_key from a Stripe price object (dict or Stripe object)."""
    if price is None:
        return None
    if isinstance(price, dict):
        return price.get("lookup_key")
    return getattr(price, "lookup_key", None)


def _extract_lookup_key_from_line_items(session_id: str) -> Optional[str]:
    """Extract lookup_key from checkout session line items."""
    try:
        items = stripe.checkout.Session.list_line_items(session_id, limit=1, expand=["data.price"])
        if not items.data:
            return None
        price = items.data[0].price
        return _extract_lookup_key_from_price(price)
    except Exception:
        return None


def _extract_lookup_key_from_subscription(subscription: dict) -> Optional[str]:
    """Extract lookup_key from a Stripe subscription object."""
    if not subscription:
        return None
    items = subscription.get("items", {})
    if isinstance(items, dict):
        data = items.get("data", [])
        if data and len(data) > 0:
            price = data[0].get("price") if isinstance(data[0], dict) else getattr(data[0], "price", None)
            return _extract_lookup_key_from_price(price)
    return None


def _map_lookup_key_to_tier(lookup_key: Optional[str]) -> Optional[str]:
    """Map a Stripe lookup_key to tier based on environment variables."""
    if not lookup_key:
        return None
    if lookup_key == settings.STRIPE_TIER1_LOOKUP_KEY:
        return "TIER1"
    if lookup_key == settings.STRIPE_TIER2_LOOKUP_KEY:
        return "TIER2"
    return None


def _list_line_items(session_id: str) -> Optional[str]:
    """Backward compatibility: extract price_id from checkout session line items."""
    try:
        items = stripe.checkout.Session.list_line_items(session_id, limit=1)
        if not items.data:
            return None
        price = items.data[0].price
        if isinstance(price, dict):
            return price.get("id")
        return getattr(price, "id", None)
    except Exception:
        return None


def _retrieve_subscription(subscription_id: str) -> Optional[dict]:
    if not subscription_id:
        return None
    try:
        subscription = stripe.Subscription.retrieve(subscription_id)
        return subscription
    except Exception:
        return None


def _get_or_create_user(db: Session, email: str) -> User:
    user = db.query(User).filter(User.email == email).one_or_none()
    if user:
        return user
    user = User(email=email, status="PENDING_PASSWORD", email_verified=False)
    db.add(user)
    db.flush()
    return user


def _ensure_tier1(db: Session, user: User) -> None:
    user.has_tier1 = True
    tier1_sub = (
        db.query(Subscription)
        .filter(Subscription.user_id == user.id, Subscription.plan == "TIER1")
        .one_or_none()
    )
    if not tier1_sub:
        tier1_sub = Subscription(
            user_id=user.id,
            plan="TIER1",
            stripe_customer_id=user.stripe_customer_id,
            status="succeeded",
            is_recurring=False,
        )
        db.add(tier1_sub)
    else:
        tier1_sub.status = "succeeded"
        tier1_sub.is_recurring = False
        tier1_sub.stripe_customer_id = user.stripe_customer_id


def _get_payload_attr(payload: Any, key: str) -> Optional[Any]:
    if payload is None:
        return None
    if isinstance(payload, dict):
        return payload.get(key)
    return getattr(payload, key, None)


def _update_tier2_subscription(
    db: Session,
    user: User,
    subscription_id: str,
    payload: dict,
) -> None:
    """Update or create a Tier2 subscription based on Stripe subscription data."""
    # Extract lookup_key to verify this is actually Tier2
    lookup_key = _extract_lookup_key_from_subscription(payload)
    tier = _map_lookup_key_to_tier(lookup_key) if lookup_key else "TIER2"  # Default to TIER2 for backward compatibility
    
    # Only process if it's Tier2
    if tier != "TIER2":
        return
    
    sub = (
        db.query(Subscription)
        .filter(Subscription.stripe_subscription_id == subscription_id)
        .one_or_none()
    )
    if not sub:
        sub = Subscription(
            user_id=user.id,
            stripe_customer_id=user.stripe_customer_id,
            stripe_subscription_id=subscription_id,
            plan="TIER2",
        )
        db.add(sub)

    status = _get_payload_attr(payload, "status") or "active"
    current_period_end = _get_payload_attr(payload, "current_period_end")
    if current_period_end:
        current_period_end = datetime.fromtimestamp(current_period_end, tz=timezone.utc)
    sub.status = status
    sub.current_period_end = current_period_end
    sub.plan = "TIER2"  # Ensure plan is set correctly
    sub.is_recurring = True
    customer_ref = _get_payload_attr(payload, "customer")
    if customer_ref:
        sub.stripe_customer_id = customer_ref


@router.post("/stripe")
async def stripe_webhook(request: Request):
    payload = await request.body()
    sig_header = request.headers.get("stripe-signature")
    try:
        event = stripe.Webhook.construct_event(
            payload=payload, sig_header=sig_header, secret=settings.STRIPE_WEBHOOK_SECRET
        )
    except Exception as e:
        raise HTTPException(status_code=400, detail="Invalid signature")

    db = SessionLocal()
    try:
        if event["type"] == "checkout.session.completed":
            session = event["data"]["object"]
            email = (session.get("customer_details") or {}).get("email") or session.get("customer_email")
            customer_id = session.get("customer")
            subscription_id = session.get("subscription")
            if not email:
                return {"ok": True}

            # Try to determine tier from lookup_key first, then fall back to metadata/price_id
            lookup_key = _extract_lookup_key_from_line_items(session.get("id"))
            tier = None
            
            if lookup_key:
                tier = _map_lookup_key_to_tier(lookup_key)
            
            # Fallback: check metadata.plan (new format) or metadata.tier (old format)
            if not tier:
                metadata = session.get("metadata", {})
                plan = metadata.get("plan")
                if plan:
                    # Map plan to tier: "tier1" -> "TIER1", "tier2-monthly" -> "TIER2"
                    if plan == "tier1":
                        tier = "TIER1"
                    elif plan == "tier2-monthly":
                        tier = "TIER2"
                if not tier:
                    tier = metadata.get("tier")
            
            # Final fallback: check price_id (backward compatibility)
            if not tier:
                price_id = _list_line_items(session.get("id"))
                tier = _map_price_to_tier(price_id)

            user = _get_or_create_user(db, email)
            if customer_id:
                user.stripe_customer_id = customer_id

            if tier == "TIER1":
                _ensure_tier1(db, user)

            if tier == "TIER2" and subscription_id:
                subscription_payload = _retrieve_subscription(subscription_id) or {}
                if customer_id:
                    subscription_payload["customer"] = customer_id
                # Ensure the subscription has the correct plan set based on lookup_key
                sub_lookup_key = _extract_lookup_key_from_subscription(subscription_payload)
                if sub_lookup_key and _map_lookup_key_to_tier(sub_lookup_key) == "TIER2":
                    _update_tier2_subscription(db, user, subscription_id, subscription_payload)

            db.commit()
        elif event["type"] in ("customer.subscription.updated","customer.subscription.deleted"):
            obj = event["data"]["object"]
            subscription_id = obj.get("id")
            status = obj.get("status")
            
            # Extract lookup_key from subscription to determine tier
            lookup_key = _extract_lookup_key_from_subscription(obj)
            tier = _map_lookup_key_to_tier(lookup_key) if lookup_key else "TIER2"  # Default to TIER2 for backward compatibility
            
            sub = db.query(Subscription).filter(Subscription.stripe_subscription_id==subscription_id).one_or_none()
            user = None
            if not sub:
                customer = obj.get("customer")
                if customer:
                    user = db.query(User).filter(User.stripe_customer_id == customer).one_or_none()
                if user:
                    # Only create subscription if it matches our tier lookup keys
                    if tier in ("TIER1", "TIER2"):
                        sub = Subscription(
                            user_id=user.id,
                            stripe_customer_id=customer,
                            stripe_subscription_id=subscription_id,
                            plan=tier,
                        )
                        db.add(sub)
            else:
                user = sub.user
                
            if sub:
                sub.status = status
                current_period_end = obj.get("current_period_end")
                if current_period_end:
                    sub.current_period_end = datetime.fromtimestamp(current_period_end, tz=timezone.utc)
                # Update plan based on lookup_key if available
                if tier in ("TIER1", "TIER2"):
                    sub.plan = tier
                sub.is_recurring = (tier == "TIER2")
                # Update Tier1 flag if this is a Tier1 subscription
                if tier == "TIER1" and user:
                    user.has_tier1 = True
                    # Ensure Tier1 subscription record exists
                    _ensure_tier1(db, user)
                db.commit()
        elif event["type"] == "invoice.payment_failed":
            obj = event["data"]["object"]
            subscription_id = obj.get("subscription")
            sub = db.query(Subscription).filter(Subscription.stripe_subscription_id==subscription_id).one_or_none()
            if sub:
                sub.status = "past_due"
                db.commit()
    finally:
        db.close()
    return {"received": True}


if __name__ == "__main__":
    print("[STRIPE_WEBHOOKS] Script starting up...")
    print("[STRIPE_WEBHOOKS] Checking for RENDER_DEBUG environment variable...")
    
    if os.getenv("RENDER_DEBUG", "").lower() == "true":
        log_render_debug_info()
    
    print("[STRIPE_WEBHOOKS] This is a FastAPI router module. Import it in your FastAPI app to use.")
