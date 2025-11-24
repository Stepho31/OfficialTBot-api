from typing import Literal

import stripe
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.settings import settings
from app.schemas import CheckoutSessionOut

class CheckoutSessionIn(BaseModel):
    tier: Literal["TIER1", "TIER2"]


router = APIRouter(prefix="/stripe", tags=["stripe"])
stripe.api_key = settings.STRIPE_SECRET_KEY

@router.post("/checkout", response_model=CheckoutSessionOut)
def create_checkout_session(payload: CheckoutSessionIn):
    price_map = {
        "TIER1": settings.STRIPE_PRICE_TIER1_ONETIME,
        "TIER2": settings.STRIPE_PRICE_TIER2_MONTHLY,
    }
    price_id = price_map.get(payload.tier)
    if not price_id:
        raise HTTPException(status_code=400, detail="Price ID not configured for tier")

    mode = "payment" if payload.tier == "TIER1" else "subscription"
    base_url = (settings.PUBLIC_CLIENT_URL or settings.FRONTEND_ORIGIN).rstrip("/")

    try:
        session = stripe.checkout.Session.create(
            mode=mode,
            line_items=[{"price": price_id, "quantity": 1}],
            success_url=f"{base_url}/post-checkout?session_id={{CHECKOUT_SESSION_ID}}",
            cancel_url=f"{base_url}?canceled=1",
            automatic_tax={"enabled": True},
            metadata={"tier": payload.tier},
        )
        return CheckoutSessionOut(url=session.url)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
