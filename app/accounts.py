from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.deps import auth_required, dashboard_access_required
from app.schemas import AccountConnectIn, AccountStatusOut
from app.models import Account, BrokerCredential
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

@router.get("/primary")
def get_primary_account(user=Depends(dashboard_access_required), db: Session = Depends(get_db)):
    """Get the user's primary account for dashboard use.
    
    Requires Tier-2 subscription, Admin, or Super Admin role.
    If no Account record exists, attempts to auto-create one from BrokerCredential.
    """
    try:
        acct = db.query(Account).filter(Account.user_id==user.id, Account.is_primary==True).first()
        if not acct:
            # Fallback to first account if no primary is set
            acct = db.query(Account).filter(Account.user_id==user.id).first()
        
        # If no Account exists, try to create one from BrokerCredential
        if not acct:
            credential = db.query(BrokerCredential).filter(BrokerCredential.user_id == user.id).first()
            if credential:
                # Check if Account with this account_id already exists
                existing = db.query(Account).filter(
                    Account.user_id == user.id,
                    Account.account_id == credential.oanda_account_id
                ).first()
                
                if existing:
                    acct = existing
                else:
                    # Create new Account from BrokerCredential
                    # Note: We don't migrate the encrypted API key as token since formats differ
                    # The Account can work without token_encrypted for dashboard purposes
                    acct = Account(
                        user_id=user.id,
                        account_id=credential.oanda_account_id,
                        token_encrypted=None,
                        label=None,
                        is_primary=True
                    )
                    db.add(acct)
                    db.commit()
                    db.refresh(acct)
        
        if not acct:
            raise HTTPException(
                status_code=404, 
                detail="No account found for user. Please connect your broker account first."
            )
        return {"account_id": acct.id, "oanda_account_id": acct.account_id, "label": acct.label}
    except HTTPException:
        raise
    except Exception as e:
        # Log the error and return a proper HTTP exception
        import logging
        logger = logging.getLogger(__name__)
        logger.error(f"Error fetching primary account for user {user.id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error while fetching account")
