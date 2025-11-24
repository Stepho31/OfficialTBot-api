from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.deps import auth_required
from app.schemas import AccountConnectIn, AccountStatusOut
from app.models import Account
from app.db import get_db
from app.crypto import encrypt_token
from app.settings import settings
import httpx

router = APIRouter(prefix="/accounts", tags=["accounts"])

def _oanda_base():
    return "https://api-fxpractice.oanda.com" if settings.OANDA_ENV == "practice" else "https://api-fxtrade.oanda.com"

@router.post("")
async def connect_account(payload: AccountConnectIn, user=Depends(auth_required), db: Session = Depends(get_db)):
    # optional: validate via OANDA Summary
    if payload.token:
        headers = {"Authorization": f"Bearer {payload.token}"}
        url = f"{_oanda_base()}/v3/accounts/{payload.account_id}/summary"
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.get(url, headers=headers)
            if r.status_code != 200:
                raise HTTPException(status_code=400, detail="Account ID and token could not be verified")
        token_encrypted = encrypt_token(payload.token)
    else:
        token_encrypted = None

    acct = Account(user_id=user.id, account_id=payload.account_id, token_encrypted=token_encrypted, label=payload.label)
    db.add(acct)
    db.commit()
    return {"ok": True, "account_id": payload.account_id}

@router.get("/status", response_model=AccountStatusOut)
def account_status(account_id: str, db: Session = Depends(get_db), user=Depends(auth_required)):
    acct = db.query(Account).filter(Account.account_id==account_id, Account.user_id==user.id).one_or_none()
    if not acct:
        raise HTTPException(status_code=404, detail="Account not found")
    return AccountStatusOut(account_id=account_id, connected=bool(acct.token_encrypted), last_checked=None)
