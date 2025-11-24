from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import func
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
    balance = float(latest.balance) if latest and latest.balance is not None else None
    equity = float(latest.equity) if latest and latest.equity is not None else None

    return DashboardSummaryOut(
        account_id=account_id,
        wtd_pnl=wtd_pnl,
        wins=wins, losses=losses, win_rate=win_rate,
        balance=balance, equity=equity
    )

@router.get("/open-trades")
def open_trades(account_id: int, user=Depends(auth_required), db: Session = Depends(get_db)):
    acct = _ensure_account(db, user.id, account_id)
    if not acct:
        raise HTTPException(status_code=404, detail="Account not found")

    rows = db.query(Trade).filter(Trade.account_id==account_id, Trade.closed_at == None).order_by(Trade.opened_at.desc()).all()
    return [TradeOut(
        instrument=r.instrument, side=r.side, units=r.units,
        opened_at=r.opened_at, closed_at=r.closed_at,
        entry_price=float(r.entry_price) if r.entry_price is not None else None,
        exit_price=float(r.exit_price) if r.exit_price is not None else None,
        pnl_net=float(r.pnl_net) if r.pnl_net is not None else None
    ) for r in rows]

@router.get("/trades")
def trades(account_id: int, from_dt: str | None = None, to_dt: str | None = None, user=Depends(auth_required), db: Session = Depends(get_db)):
    acct = _ensure_account(db, user.id, account_id)
    if not acct:
        raise HTTPException(status_code=404, detail="Account not found")
    q = db.query(Trade).filter(Trade.account_id==account_id, Trade.closed_at != None)
    if from_dt:
        q = q.filter(Trade.closed_at >= from_dt)
    if to_dt:
        q = q.filter(Trade.closed_at <= to_dt)
    q = q.order_by(Trade.closed_at.desc())
    rows = q.all()
    return [TradeOut(
        instrument=r.instrument, side=r.side, units=r.units,
        opened_at=r.opened_at, closed_at=r.closed_at,
        entry_price=float(r.entry_price) if r.entry_price is not None else None,
        exit_price=float(r.exit_price) if r.exit_price is not None else None,
        pnl_net=float(r.pnl_net) if r.pnl_net is not None else None
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
    rows = db.query(EquitySnapshot).filter(EquitySnapshot.account_id==account_id, EquitySnapshot.taken_at >= start).order_by(EquitySnapshot.taken_at.asc()).all()
    return [EquityPoint(taken_at=r.taken_at, equity=float(r.equity) if r.equity is not None else None) for r in rows]
