from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.crypto import encrypt_api_key
from app.db import get_db
from app.deps import auth_required
from app.entitlements import compute_entitlements
from app.models import BrokerCredential, User
from app.schemas import BrokerStatusOut, BrokerUpsertIn

me_router = APIRouter(prefix="/v1/me", tags=["broker"])


@me_router.get("/broker", response_model=BrokerStatusOut)
def get_broker_status(
    user: User = Depends(auth_required),
    db: Session = Depends(get_db),
) -> BrokerStatusOut:
    credential = db.query(BrokerCredential).filter(BrokerCredential.user_id == user.id).one_or_none()
    if not credential:
        return BrokerStatusOut(hasBrokerCreds=False, oandaAccountId=None, updatedAt=None)
    return BrokerStatusOut(
        hasBrokerCreds=True,
        oandaAccountId=credential.oanda_account_id,
        updatedAt=credential.updated_at,
    )


@me_router.put("/broker", response_model=BrokerStatusOut)
def upsert_broker_credentials(
    payload: BrokerUpsertIn,
    user: User = Depends(auth_required),
    db: Session = Depends(get_db),
) -> BrokerStatusOut:
    entitlements = compute_entitlements(db, user)
    if not entitlements.can_trade:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Trading entitlement required")

    encrypted = encrypt_api_key(payload.oandaApiKey)

    credential = (
        db.query(BrokerCredential)
        .filter(BrokerCredential.user_id == user.id)
        .one_or_none()
    )
    if credential:
        credential.oanda_account_id = payload.oandaAccountId
        credential.enc_api_key = encrypted["cipher"]
        credential.enc_iv = encrypted["iv"]
        credential.enc_tag = encrypted["tag"]
    else:
        credential = BrokerCredential(
            user_id=user.id,
            oanda_account_id=payload.oandaAccountId,
            enc_api_key=encrypted["cipher"],
            enc_iv=encrypted["iv"],
            enc_tag=encrypted["tag"],
        )
        db.add(credential)

    db.commit()
    db.refresh(credential)
    return BrokerStatusOut(
        hasBrokerCreds=True,
        oandaAccountId=credential.oanda_account_id,
        updatedAt=credential.updated_at,
    )

