from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import select

from app.db import get_db
from app.deps import require_bot_key   # <-- using the new name
from app.models import Account, Trade, EquitySnapshot, Signal
from app.schemas import TradeIn, TradeInAck, SnapshotIn, SnapshotAck, SignalIn, SignalAck

router = APIRouter(prefix="/v1", tags=["ingest"])


def _resolve_account(db: Session, external_acct: str) -> Account:
    acct = db.execute(select(Account).where(Account.account_id == external_acct)).scalar_one_or_none()
    if not acct:
        raise HTTPException(status_code=404, detail="Account not connected")
    return acct


@router.post("/trades", response_model=TradeInAck, dependencies=[Depends(require_bot_key)])
def ingest_trade(body: TradeIn, db: Session = Depends(get_db)):
    acct = _resolve_account(db, body.account_id)

    existing = db.execute(
        select(Trade).where(Trade.account_id == acct.id, Trade.external_id == body.trade_id)
    ).scalar_one_or_none()

    if existing:
        if body.closed_at:
            existing.closed_at = body.closed_at
        if body.exit_price is not None:
            existing.exit_price = body.exit_price
        if body.realized_pnl is not None:
            existing.pnl_net = body.realized_pnl
        if body.meta and "reason_close" in body.meta:
            existing.reason_close = str(body.meta["reason_close"])
        if not existing.user_id:
            existing.user_id = acct.user_id
        db.commit()
        return TradeInAck(ok=True, upserted=False)

    t = Trade(
        account_id=acct.id,
        user_id=acct.user_id,
        external_id=body.trade_id,
        instrument=body.instrument,
        side=body.side,
        units=body.position_size,
        opened_at=body.opened_at,
        entry_price=body.entry_price,
        closed_at=body.closed_at,
        exit_price=body.exit_price,
        pnl_net=body.realized_pnl,
        reason_open=(body.meta or {}).get("rationale"),
    )
    db.add(t)
    db.commit()
    return TradeInAck(ok=True, upserted=True)


@router.post("/account/snapshots", response_model=SnapshotAck, dependencies=[Depends(require_bot_key)])
def ingest_snapshot(body: SnapshotIn, db: Session = Depends(get_db)):
    acct = _resolve_account(db, body.account_id)

    snap = db.execute(
        select(EquitySnapshot).where(
            EquitySnapshot.account_id == acct.id,
            EquitySnapshot.taken_at == body.timestamp,
        )
    ).scalar_one_or_none()

    if snap:
        snap.balance = body.balance
        snap.equity = body.equity
        snap.margin_used = body.margin_used
        db.commit()
        return SnapshotAck(ok=True)

    db.add(
        EquitySnapshot(
            account_id=acct.id,
            taken_at=body.timestamp,
            balance=body.balance,
            equity=body.equity,
            margin_used=body.margin_used,
        )
    )
    db.commit()
    return SnapshotAck(ok=True)


@router.post("/signals", response_model=SignalAck, dependencies=[Depends(require_bot_key)])
def ingest_signal(body: SignalIn, db: Session = Depends(get_db)):
    s = db.execute(select(Signal).where(Signal.signal_id == body.signal_id)).scalar_one_or_none()
    if s:
        s.symbol = body.pair or s.symbol
        s.direction = body.direction or s.direction
        if body.entry is not None:
            s.entry = body.entry
        if body.sl is not None:
            s.sl = body.sl
        if body.tp is not None:
            s.tp = body.tp
        s.rationale = body.rationale or s.rationale
        db.commit()
        return SignalAck(ok=True)

    db.add(
        Signal(
            signal_id=body.signal_id,
            created_at=body.created_at or datetime.utcnow(),
            symbol=body.pair,
            direction=body.direction,
            entry=body.entry,
            sl=body.sl,
            tp=body.tp,
            rationale=body.rationale,
        )
    )
    db.commit()
    return SignalAck(ok=True)
