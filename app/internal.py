from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session
from sqlalchemy import or_, and_

from app.crypto import decrypt_api_key
from app.db import get_db
from app.deps import require_bot_key
from app.entitlements import compute_entitlements, ACTIVE_SUB_STATUSES
from app.models import Account, BrokerCredential, EquitySnapshot, Subscription, Trade, User, UserSettings
from app.schemas import (
    BrokerSecretOut,
    EntitlementsOut,
    EquityServerIn,
    EquityServerOut,
    InternalTradeIn,
    TradeAck,
    Tier2UserOut,
    Tier2UsersOut,
    UserSettingsInternalOut,
    TradeOut,
)

router = APIRouter(prefix="/v1/internal", tags=["internal"], dependencies=[Depends(require_bot_key)])


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _get_user(db: Session, user_id: int) -> User:
    user = db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    return user


def _resolve_account(db: Session, user_id: int, oanda_account_id: Optional[str]) -> Optional[Account]:
    query = db.query(Account).filter(Account.user_id == user_id)
    if oanda_account_id:
        query = query.filter(Account.account_id == oanda_account_id)
    account = query.order_by(Account.created_at.asc()).one_or_none()
    return account


@router.get("/entitlements", response_model=EntitlementsOut)
def get_entitlements_internal(userId: int = Query(...), db: Session = Depends(get_db)) -> EntitlementsOut:
    user = _get_user(db, userId)
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


@router.get("/broker", response_model=BrokerSecretOut)
def get_broker_internal(userId: int = Query(...), db: Session = Depends(get_db)) -> BrokerSecretOut:
    credential = (
        db.query(BrokerCredential)
        .filter(BrokerCredential.user_id == userId)
        .one_or_none()
    )
    if not credential:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Broker credentials not found")
    api_key = decrypt_api_key(credential.enc_api_key, credential.enc_iv, credential.enc_tag)
    return BrokerSecretOut(
        oandaAccountId=credential.oanda_account_id,
        oandaApiKey=api_key,
    )


@router.post("/trades", response_model=TradeAck)
def upsert_trade_internal(payload: InternalTradeIn, db: Session = Depends(get_db)) -> TradeAck:
    user = _get_user(db, payload.userId)
    account = _resolve_account(db, user.id, payload.oandaAccountId)
    
    # Auto-create Account record if missing (prevents 404 errors)
    # This ensures trades can be persisted even if Account wasn't created via /accounts endpoint
    if not account:
        if not payload.oandaAccountId:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="oandaAccountId is required to create Account record"
            )
        # Create Account record automatically from BrokerCredential
        # Verify BrokerCredential exists for this user
        broker_cred = db.query(BrokerCredential).filter(
            BrokerCredential.user_id == user.id,
            BrokerCredential.oanda_account_id == payload.oandaAccountId
        ).one_or_none()
        
        if not broker_cred:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"BrokerCredential not found for user {user.id} and OANDA account {payload.oandaAccountId}"
            )
        
        # Create Account record
        account = Account(
            user_id=user.id,
            account_id=payload.oandaAccountId,
            broker="OANDA",
            is_primary=True,  # Assume primary if it's the only one
        )
        db.add(account)
        db.flush()  # Flush to get account.id
        db.commit()
        db.refresh(account)

    trade = (
        db.query(Trade)
        .filter(Trade.user_id == user.id, Trade.external_id == payload.externalTradeId)
        .one_or_none()
    )
    created = False
    was_open = False
    if not trade:
        trade = Trade(
            user_id=user.id,
            account_id=account.id,
            external_id=payload.externalTradeId,
        )
        created = True
        db.add(trade)
    else:
        # Track if trade was previously open (for equity snapshot on close)
        was_open = trade.status == "OPEN" or (trade.status is None and trade.closed_at is None)

    trade.user_id = user.id
    trade.account_id = account.id
    trade.instrument = payload.symbol
    trade.side = payload.side
    trade.units = payload.size
    trade.opened_at = payload.openedAt or trade.opened_at or _now()
    
    # Determine status from payload or closed_at
    payload_status_upper = payload.status.upper() if payload.status else None
    if payload_status_upper == "CLOSED" or payload.closedAt:
        trade.closed_at = payload.closedAt or trade.closed_at or _now()
        trade.status = "CLOSED"
        if payload.entry is not None and not trade.exit_price:
            trade.exit_price = payload.entry
    else:
        # Trade is open
        trade.status = "OPEN"
        trade.closed_at = None
    
    trade.entry_price = payload.entry or trade.entry_price
    notes = []
    if payload.tp is not None:
        notes.append(f"tp={payload.tp}")
    if payload.sl is not None:
        notes.append(f"sl={payload.sl}")
    if payload.timeframe:
        notes.append(f"timeframe={payload.timeframe}")
    if notes:
        trade.reason_open = " ".join(notes)
    
    # Update P/L - use payload.pnl if provided, otherwise keep existing
    if payload.pnl is not None:
        trade.pnl_net = payload.pnl
    
    # Set reason_close for closed trades
    if trade.status == "CLOSED":
        trade.reason_close = payload.status or trade.reason_close or "CLOSED"

    db.commit()
    
    # Note: Equity snapshots should be created by the bot when trades open/close
    # by calling POST /v1/internal/equity with current balance/equity from OANDA.
    # This ensures the equity trend graph captures trade lifecycle events.
    # The trade state is now persisted and ready for dashboard display.
    
    return TradeAck(ok=True, upserted=created)


@router.post("/equity", response_model=EquityServerOut)
def upsert_equity_internal(payload: EquityServerIn, db: Session = Depends(get_db)) -> EquityServerOut:
    user = _get_user(db, payload.userId)
    account = _resolve_account(db, user.id, payload.oandaAccountId)
    if not account:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Account not connected for user")

    existing = (
        db.query(EquitySnapshot)
        .filter(
            EquitySnapshot.account_id == account.id,
            EquitySnapshot.taken_at == payload.timestamp,
        )
        .one_or_none()
    )
    if existing:
        existing.balance = payload.balance
        existing.equity = payload.equity
        existing.margin_used = payload.marginUsed
        db.commit()
        return EquityServerOut(ok=True, upserted=False)

    snapshot = EquitySnapshot(
        account_id=account.id,
        taken_at=payload.timestamp,
        balance=payload.balance,
        equity=payload.equity,
        margin_used=payload.marginUsed,
    )
    db.add(snapshot)
    db.commit()
    return EquityServerOut(ok=True, upserted=True)


@router.get("/tier2-users", response_model=Tier2UsersOut)
def get_tier2_users_for_automation(db: Session = Depends(get_db)) -> Tier2UsersOut:
    """
    Returns all Tier-2 users eligible for automation (active subscription + broker credentials).
    Used by the trading bot to iterate through users and execute trades per account.
    """
    now = _now()
    
    # Find all users with active Tier-2 subscriptions
    active_tier2_users = (
        db.query(User)
        .outerjoin(Subscription, User.id == Subscription.user_id)
        .filter(
            or_(
                # Normal Tier-2 path
                and_(
                    Subscription.plan == "TIER2",
                    Subscription.status.in_(list(ACTIVE_SUB_STATUSES)),
                    or_(
                        Subscription.current_period_end.is_(None),
                        Subscription.current_period_end >= now,
                    ),
                ),
                # Admin override – admins are always considered candidates
                (User.role == "ADMIN"),
                
            )
        )
        .distinct()
        .all()
    )
    
    # Filter to only those with broker credentials and verify entitlements
    eligible_users = []
    for user in active_tier2_users:
        # Double-check entitlements
        ent = compute_entitlements(db, user, now=now)
        if not ent.can_trade:
            continue
        
        # Get broker credentials
        credential = (
            db.query(BrokerCredential)
            .filter(BrokerCredential.user_id == user.id)
            .one_or_none()
        )
        
        if not credential:
            continue
        
        try:
            api_key = decrypt_api_key(credential.enc_api_key, credential.enc_iv, credential.enc_tag)
            eligible_users.append(
                Tier2UserOut(
                    userId=user.id,
                    email=user.email,
                    oandaAccountId=credential.oanda_account_id,
                    oandaApiKey=api_key,
                )
            )
        except Exception as e:
            # Skip users with invalid credentials (decryption failure)
            continue
    
    return Tier2UsersOut(users=eligible_users)


@router.get("/user-settings", response_model=UserSettingsInternalOut)
def get_user_settings_internal(userId: int = Query(...), db: Session = Depends(get_db)) -> UserSettingsInternalOut:
    """Get user settings for trading bot. Returns default if not set."""
    user = _get_user(db, userId)
    settings = db.query(UserSettings).filter(UserSettings.user_id == user.id).one_or_none()
    
    # Default to 10.0 if no settings found (matches system default)
    trade_allocation = settings.trade_allocation if settings else 10.0
    
    return UserSettingsInternalOut(tradeAllocation=trade_allocation)


@router.get("/weekly-trades")
def get_weekly_trades_internal(
    from_dt: str = Query(..., description="Start datetime (ISO format)"),
    to_dt: str = Query(..., description="End datetime (ISO format)"),
    db: Session = Depends(get_db),
):
    """
    Get all closed trades for a date range (for weekly reports).
    Used by the bot to generate weekly recap emails from database instead of file system.
    Returns trades across all users for the specified date range.
    """
    from datetime import datetime
    
    try:
        start_dt = datetime.fromisoformat(from_dt.replace("Z", "+00:00"))
        end_dt = datetime.fromisoformat(to_dt.replace("Z", "+00:00"))
    except ValueError as e:
        from fastapi import HTTPException, status
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid datetime format: {e}"
        )
    
    # Query all closed trades in the date range
    # Fix: Query by closed_at date range to get all trades that closed during the week
    trades = (
        db.query(Trade)
        .filter(
            Trade.closed_at.isnot(None),
            Trade.closed_at >= start_dt,
            Trade.closed_at <= end_dt,
        )
        .order_by(Trade.closed_at.asc())
        .all()
    )
    
    # Serialize trades for weekly email format
    return [
        TradeOut(
            trade_id=t.external_id,
            instrument=t.instrument,
            side=t.side,
            units=t.units,
            opened_at=t.opened_at,
            closed_at=t.closed_at,
            entry_price=float(t.entry_price) if t.entry_price is not None else None,
            exit_price=float(t.exit_price) if t.exit_price is not None else None,
            pnl_net=float(t.pnl_net) if t.pnl_net is not None else None,
            status=t.status or ("CLOSED" if t.closed_at is not None else "OPEN"),
        )
        for t in trades
    ]

