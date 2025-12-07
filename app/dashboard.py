from typing import Optional
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import func, or_
from datetime import datetime, timedelta
from app.deps import auth_required
from app.db import get_db
from app.models import Trade, EquitySnapshot, Account
from app.schemas import DashboardSummaryOut, TradeOut, EquityPoint

router = APIRouter(prefix="/dashboard", tags=["dashboard"])

def _week_window():
    today = datetime.utcnow().date()
    # week starts on Monday
    start = today - timedelta(days=today.weekday())
    return datetime.combine(start, datetime.min.time()), datetime.utcnow()

def _ensure_account(db: Session, user_id: int, account_id: int) -> Optional[Account]:
    return db.query(Account).filter(Account.id == account_id, Account.user_id == user_id).one_or_none()

def _calculate_equity_from_trades(db: Session, account_id: int, balance: Optional[Decimal]) -> Optional[float]:
    """Calculate equity as balance + unrealized P/L from open trades.
    If balance is None, returns None. If no open trades, returns balance.
    """
    if balance is None:
        return None
    
    # Get all open trades for this account
    open_trades = db.query(Trade).filter(
        Trade.account_id == account_id,
        or_(Trade.status == "OPEN", Trade.closed_at.is_(None))
    ).all()
    
    # Sum unrealized P/L (pnl_net for open trades represents unrealized P/L)
    unrealized_pnl = sum(
        float(t.pnl_net) if t.pnl_net is not None else 0.0
        for t in open_trades
    )
    
    return float(balance) + unrealized_pnl


@router.get("/summary", response_model=DashboardSummaryOut)
def summary(account_id: int, user=Depends(auth_required), db: Session = Depends(get_db)):
    acct = _ensure_account(db, user.id, account_id)
    if not acct:
        raise HTTPException(status_code=404, detail="Account not found")

    start, end = _week_window()
    # WTD stats
    trades = db.query(Trade).filter(Trade.account_id==account_id, Trade.closed_at != None, Trade.closed_at >= start, Trade.closed_at <= end).all()
    wins = sum(1 for t in trades if (t.pnl_net or 0) > 0)
    losses = sum(1 for t in trades if (t.pnl_net or 0) <= 0)
    wtd_pnl = float(sum((t.pnl_net or 0) for t in trades)) if trades else 0.0
    win_rate = round(100.0 * wins / max(1, len(trades)), 2)

    # latest equity snapshot
    latest = db.query(EquitySnapshot).filter(EquitySnapshot.account_id==account_id).order_by(EquitySnapshot.taken_at.desc()).first()
    balance = latest.balance if latest and latest.balance is not None else None
    equity = None
    
    if latest and latest.equity is not None:
        equity = float(latest.equity)
    elif balance is not None:
        # Calculate equity from balance + unrealized P/L if equity snapshot doesn't have it
        equity = _calculate_equity_from_trades(db, account_id, balance)

    return DashboardSummaryOut(
        account_id=account_id,
        wtd_pnl=wtd_pnl,
        wins=wins, losses=losses, win_rate=win_rate,
        balance=float(balance) if balance is not None else None,
        equity=equity
    )

@router.get("/open-trades")
def open_trades(account_id: int, user=Depends(auth_required), db: Session = Depends(get_db)):
    acct = _ensure_account(db, user.id, account_id)
    if not acct:
        raise HTTPException(status_code=404, detail="Account not found")

    # Query open trades using status field or closed_at as fallback
    rows = db.query(Trade).filter(
        Trade.account_id == account_id,
        or_(Trade.status == "OPEN", Trade.closed_at.is_(None))
    ).order_by(Trade.opened_at.desc().nullslast()).all()
    
    return [TradeOut(
        trade_id=r.external_id,
        instrument=r.instrument,
        side=r.side,
        units=r.units,
        opened_at=r.opened_at,
        closed_at=r.closed_at,
        entry_price=float(r.entry_price) if r.entry_price is not None else None,
        exit_price=float(r.exit_price) if r.exit_price is not None else None,
        pnl_net=float(r.pnl_net) if r.pnl_net is not None else None,
        status=r.status or ("OPEN" if r.closed_at is None else "CLOSED"),
        unrealized_pnl=float(r.pnl_net) if r.pnl_net is not None else None  # For open trades, pnl_net is unrealized
    ) for r in rows]

@router.get("/trades")
def trades(account_id: int, from_dt: str | None = None, to_dt: str | None = None, user=Depends(auth_required), db: Session = Depends(get_db)):
    acct = _ensure_account(db, user.id, account_id)
    if not acct:
        raise HTTPException(status_code=404, detail="Account not found")
    
    # Query closed trades using status field or closed_at as fallback
    q = db.query(Trade).filter(
        Trade.account_id == account_id,
        or_(Trade.status == "CLOSED", Trade.closed_at.isnot(None))
    )
    if from_dt:
        q = q.filter(Trade.closed_at >= from_dt)
    if to_dt:
        q = q.filter(Trade.closed_at <= to_dt)
    q = q.order_by(Trade.closed_at.desc().nullslast())
    rows = q.all()
    
    return [TradeOut(
        trade_id=r.external_id,
        instrument=r.instrument,
        side=r.side,
        units=r.units,
        opened_at=r.opened_at,
        closed_at=r.closed_at,
        entry_price=float(r.entry_price) if r.entry_price is not None else None,
        exit_price=float(r.exit_price) if r.exit_price is not None else None,
        pnl_net=float(r.pnl_net) if r.pnl_net is not None else None,
        status=r.status or ("CLOSED" if r.closed_at is not None else "OPEN")
    ) for r in rows]

@router.get("/equity-series")
def equity_series(account_id: int, window: str = "30d", user=Depends(auth_required), db: Session = Depends(get_db)):
    acct = _ensure_account(db, user.id, account_id)
    if not acct:
        raise HTTPException(status_code=404, detail="Account not found")
    days = 30
    if window.endswith("d"):
        try:
            days = int(window[:-1])
        except:
            pass
    start = datetime.utcnow() - timedelta(days=days)
    
    # Get equity snapshots
    snapshot_rows = db.query(EquitySnapshot).filter(
        EquitySnapshot.account_id == account_id,
        EquitySnapshot.taken_at >= start
    ).order_by(EquitySnapshot.taken_at.asc()).all()
    
    # Build equity points from snapshots
    equity_points = []
    for r in snapshot_rows:
        equity_value = None
        if r.equity is not None:
            equity_value = float(r.equity)
        elif r.balance is not None:
            # Calculate equity from balance + unrealized P/L at snapshot time
            # Note: This is approximate as we're using current open trades
            equity_value = _calculate_equity_from_trades(db, account_id, r.balance)
        
        if equity_value is not None:
            equity_points.append(EquityPoint(taken_at=r.taken_at, equity=equity_value))
    
    # Sort by timestamp and remove duplicates (keep latest for same timestamp)
    equity_points.sort(key=lambda x: x.taken_at)
    # Remove duplicates by timestamp, keeping the last one
    seen = {}
    for point in equity_points:
        seen[point.taken_at] = point
    equity_points = list(seen.values())
    equity_points.sort(key=lambda x: x.taken_at)
    
    # Note: Equity snapshots should be created by the bot when trades open/close
    # via POST /v1/internal/equity. This ensures accurate equity tracking at trade lifecycle events.
    # If snapshots are missing, the bot should be updated to call the equity endpoint
    # whenever it updates trades.
    
    return equity_points
