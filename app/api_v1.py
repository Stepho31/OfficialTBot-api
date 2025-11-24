from datetime import datetime, timezone
from typing import Literal, Optional, Tuple

import httpx
import stripe
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy import and_, desc, or_
from sqlalchemy.orm import Session

from app.crypto import decrypt_api_key
from app.db import get_db
from app.deps import auth_required
from app.entitlements import compute_entitlements
from app.models import BrokerCredential, Subscription, Trade, User
from app.settings import settings
from app.schemas import (
    AccountSummaryOut,
    CheckoutSessionOut,
    EntitlementsOut,
    MeOut,
    PerformanceSummaryOut,
    SubscriptionOut,
    TradeDetailOut,
    TradeListOut,
)

router = APIRouter(prefix="/v1", tags=["v1"])

# Initialize Stripe
stripe.api_key = settings.STRIPE_SECRET_KEY


class CheckoutStartIn(BaseModel):
    plan: Literal["tier1", "tier2-monthly"]

@router.get("/me", response_model=MeOut)
def me(user: User = Depends(auth_required)) -> MeOut:
    return MeOut(
        id=user.id,
        email=user.email,
        role=user.role,
        hasTier1=user.has_tier1,
        stripe_customer_id=user.stripe_customer_id,
    )



@router.get("/subscription", response_model=SubscriptionOut)
def subscription(user: User = Depends(auth_required), db: Session = Depends(get_db)) -> SubscriptionOut:
    sub = (
        db.query(Subscription)
        .filter(Subscription.user_id == user.id, Subscription.plan == "TIER2")
        .order_by(Subscription.created_at.desc())
        .first()
    )
    if not sub:
        return SubscriptionOut()
    return SubscriptionOut(
        plan=sub.plan,
        status=sub.status,
        current_period_end=sub.current_period_end,
        is_recurring=sub.is_recurring,
        stripe_subscription_id=sub.stripe_subscription_id,
    )


@router.get("/entitlements", response_model=EntitlementsOut)
def entitlements(user: User = Depends(auth_required), db: Session = Depends(get_db)) -> EntitlementsOut:
    ent = compute_entitlements(db, user)
    return EntitlementsOut(
        canReceiveEmailSignals=ent.can_receive_email_signals,
        canTrade=ent.can_trade,
        canAccessDashboard=ent.can_access_dashboard,
        tier1=ent.tier1,
        tier2Status=ent.tier2_status,
        tier2Active=ent.tier2_active,
        betaApplied=ent.beta_applied,
    )


def _serialize_trade(trade: Trade) -> TradeDetailOut:
    return TradeDetailOut(
        id=str(trade.id),
        instrument=trade.instrument,
        side=(trade.side or "").upper() if trade.side else None,
        size=trade.units,
        entry=float(trade.entry_price) if trade.entry_price is not None else None,
        exit=float(trade.exit_price) if trade.exit_price is not None else None,
        pnl=float(trade.pnl_net) if trade.pnl_net is not None else None,
        status="OPEN" if trade.closed_at is None else (trade.reason_close or "CLOSED"),
        openedAt=trade.opened_at,
        closedAt=trade.closed_at,
    )


def _cursor_components(cursor: str) -> Tuple[datetime, int]:
    try:
        opened_str, id_str = cursor.split("|", 1)
        opened_at = datetime.fromisoformat(opened_str)
        trade_id = int(id_str)
        return opened_at, trade_id
    except Exception as exc:
        raise HTTPException(status_code=400, detail="Invalid cursor") from exc


def _build_cursor(trade: Trade) -> str:
    opened = trade.opened_at or datetime(1970, 1, 1, tzinfo=timezone.utc)
    return f"{opened.isoformat()}|{trade.id}"


@router.get("/trades", response_model=TradeListOut)
def list_trades(
    limit: int = Query(25, ge=1, le=200),
    cursor: Optional[str] = Query(None),
    user: User = Depends(auth_required),
    db: Session = Depends(get_db),
) -> TradeListOut:
    query = (
        db.query(Trade)
        .filter(Trade.user_id == user.id)
        .order_by(Trade.opened_at.desc().nullslast(), Trade.id.desc())
    )

    if cursor:
        opened_at, cursor_id = _cursor_components(cursor)
        query = query.filter(
            or_(
                Trade.opened_at < opened_at,
                and_(Trade.opened_at == opened_at, Trade.id < cursor_id),
            )
        )

    rows = query.limit(limit + 1).all()
    has_more = len(rows) > limit
    if has_more:
        rows = rows[:limit]

    next_cursor = _build_cursor(rows[-1]) if has_more else None
    items = [_serialize_trade(t) for t in rows]
    return TradeListOut(items=items, nextCursor=next_cursor)


@router.get("/trades/{trade_id}", response_model=TradeDetailOut)
def get_trade(
    trade_id: int,
    user: User = Depends(auth_required),
    db: Session = Depends(get_db),
) -> TradeDetailOut:
    trade = (
        db.query(Trade)
        .filter(Trade.id == trade_id, Trade.user_id == user.id)
        .one_or_none()
    )
    if not trade:
        raise HTTPException(status_code=404, detail="Trade not found")
    return _serialize_trade(trade)


@router.get("/performance/summary", response_model=PerformanceSummaryOut)
def performance_summary(
    user: User = Depends(auth_required),
    db: Session = Depends(get_db),
) -> PerformanceSummaryOut:
    trades = db.query(Trade).filter(Trade.user_id == user.id).all()
    closed = [t for t in trades if t.closed_at is not None]

    total_pnl = sum(float(t.pnl_net or 0) for t in closed)
    closed_count = len(closed)
    wins = sum(1 for t in closed if float(t.pnl_net or 0) > 0)
    win_rate = (wins / closed_count * 100) if closed_count else 0.0
    avg_r = (total_pnl / closed_count) if closed_count else 0.0

    opened_times = [t.opened_at for t in trades if t.opened_at is not None]
    closed_times = [
        t.closed_at or t.opened_at for t in trades if (t.closed_at or t.opened_at) is not None
    ]

    period_start = min(opened_times) if opened_times else None
    period_end = max(closed_times) if closed_times else None

    return PerformanceSummaryOut(
        totalPnL=total_pnl,
        winRate=win_rate,
        avgR=avg_r,
        tradesCount=len(trades),
        periodStart=period_start,
        periodEnd=period_end,
    )


def _oanda_base_url() -> str:
    """Get OANDA API base URL based on environment setting."""
    if settings.OANDA_ENV == "practice":
        return "https://api-fxpractice.oanda.com"
    return "https://api-fxtrade.oanda.com"


@router.get("/account/summary", response_model=AccountSummaryOut)
async def get_account_summary(
    user: User = Depends(auth_required),
    db: Session = Depends(get_db),
) -> AccountSummaryOut:
    """
    Get the current user's OANDA account summary (balance, equity, margin available).
    
    Requires broker credentials to be configured for the user.
    """
    # Look up broker credentials
    credential = (
        db.query(BrokerCredential)
        .filter(BrokerCredential.user_id == user.id)
        .one_or_none()
    )
    
    if not credential:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Broker credentials not configured for this user",
        )
    
    # Decrypt the API key
    try:
        api_key = decrypt_api_key(
            credential.enc_api_key,
            credential.enc_iv,
            credential.enc_tag,
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to decrypt broker credentials",
        ) from e
    
    # Call OANDA API
    account_id = credential.oanda_account_id
    base_url = _oanda_base_url()
    url = f"{base_url}/v3/accounts/{account_id}/summary"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(url, headers=headers)
            
            if response.status_code == 401 or response.status_code == 403:
                raise HTTPException(
                    status_code=status.HTTP_502_BAD_GATEWAY,
                    detail="Invalid or unauthorized broker credentials",
                )
            
            if response.status_code != 200:
                raise HTTPException(
                    status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                    detail="Unable to fetch account summary from broker",
                )
            
            data = response.json()
            account_data = data.get("account", {})
            
            # Extract balance, equity, marginAvailable, currency
            balance = float(account_data.get("balance", "0"))
            equity = account_data.get("NAV")  # OANDA uses NAV (Net Asset Value) for equity
            if equity is not None:
                equity = float(equity)
            margin_available = account_data.get("marginAvailable")
            if margin_available is not None:
                margin_available = float(margin_available)
            currency = account_data.get("currency", "USD")
            
            return AccountSummaryOut(
                balance=balance,
                equity=equity,
                marginAvailable=margin_available,
                currency=currency,
            )
            
    except HTTPException:
        raise
    except httpx.TimeoutException:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Request to broker timed out",
        )
    except httpx.RequestError as e:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Unable to fetch account summary from broker",
        ) from e
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Unexpected error fetching account summary",
        ) from e


@router.post("/checkout/start", response_model=CheckoutSessionOut)
def start_checkout(payload: CheckoutStartIn):
    """
    Create a Stripe Checkout Session using lookup keys.
    Accepts plan: 'tier1' or 'tier2-monthly'
    """
    if not stripe.api_key:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Stripe is not configured"
        )
    
    # Map plan to lookup key and determine mode
    lookup_key_map = {
        "tier1": settings.STRIPE_TIER1_LOOKUP_KEY,
        "tier2-monthly": settings.STRIPE_TIER2_LOOKUP_KEY,
    }
    
    lookup_key = lookup_key_map.get(payload.plan)
    if not lookup_key:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid plan: {payload.plan}"
        )
    
    # Determine mode: payment for tier1 (one-time), subscription for tier2-monthly
    mode = "payment" if payload.plan == "tier1" else "subscription"
    base_url = (settings.PUBLIC_CLIENT_URL or settings.FRONTEND_ORIGIN).rstrip("/")
    
    try:
        # Retrieve the price using lookup_key
        prices = stripe.Price.list(lookup_keys=[lookup_key], limit=1)
        if not prices.data or len(prices.data) == 0:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Price not found for lookup_key: {lookup_key}"
            )
        price_id = prices.data[0].id
        
        # Create checkout session using the retrieved price_id
        session = stripe.checkout.Session.create(
            mode=mode,
            line_items=[{"price": price_id, "quantity": 1}],
            success_url=f"{base_url}/post-checkout?session_id={{CHECKOUT_SESSION_ID}}",
            cancel_url=f"{base_url}?canceled=1",
            automatic_tax={"enabled": True},
            metadata={"plan": payload.plan},
        )
        return CheckoutSessionOut(url=session.url)
    except stripe.error.StripeError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Stripe error: {str(e)}"
        ) from e
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create checkout session: {str(e)}"
        ) from e
