from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import current_user, tier2_required
from app.models import (
    User,
    NotificationPreferences,
    TradingEntitlements,
)

router = APIRouter(prefix="/profile", tags=["profile"])

@router.get("/me")
def me(user: User = Depends(current_user)):
    prefs = user.preferences
    ent = user.entitlements
    return {
        "id": user.id,
        "email": user.email,
        "tier": user.tier.value if hasattr(user.tier, "value") else str(user.tier),
        "subscription_status": user.subscription_status.value
        if hasattr(user.subscription_status, "value")
        else str(user.subscription_status),
        "preferences": {
            "email_signal_realtime": bool(prefs and prefs.email_signal_realtime),
            "email_digest_daily": bool(prefs and prefs.email_digest_daily),
            "email_digest_weekly": bool(prefs and prefs.email_digest_weekly),
            "email_critical": bool(prefs and prefs.email_critical) if prefs else True,
            "sms_critical": bool(prefs and prefs.sms_critical) if prefs else False,
        },
        "entitlements": {
            "can_auto_trade": bool(ent and ent.can_auto_trade),
            "broker_connected": bool(ent and ent.broker_connected),
            "broker_last_health": ent.broker_last_health if ent else None,
        },
    }

@router.patch("/preferences")
def update_preferences(
    email_signal_realtime: bool | None = None,
    email_digest_daily: bool | None = None,
    email_digest_weekly: bool | None = None,
    email_critical: bool | None = None,
    sms_critical: bool | None = None,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    prefs = user.preferences
    if prefs is None:
        prefs = NotificationPreferences(user_id=user.id)
    if email_signal_realtime is not None:
        prefs.email_signal_realtime = email_signal_realtime
    if email_digest_daily is not None:
        prefs.email_digest_daily = email_digest_daily
    if email_digest_weekly is not None:
        prefs.email_digest_weekly = email_digest_weekly
    if email_critical is not None:
        prefs.email_critical = email_critical
    if sms_critical is not None:
        prefs.sms_critical = sms_critical

    db.add(prefs)
    db.commit()
    db.refresh(prefs)

    return {
        "ok": True,
        "preferences": {
            "email_signal_realtime": prefs.email_signal_realtime,
            "email_digest_daily": prefs.email_digest_daily,
            "email_digest_weekly": prefs.email_digest_weekly,
            "email_critical": prefs.email_critical,
            "sms_critical": prefs.sms_critical,
        },
    }

@router.get("/entitlements")
def get_entitlements(user: User = Depends(tier2_required)):
    ent = user.entitlements
    return {
        "can_auto_trade": bool(ent and ent.can_auto_trade),
        "broker_connected": bool(ent and ent.broker_connected),
        "broker_last_health": ent.broker_last_health if ent else None,
    }
