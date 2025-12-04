from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from pydantic import BaseModel

from app.db import get_db
from app.deps import auth_required
from app.models import User, UserSettings
from app.schemas import UserSettingsOut, UserSettingsIn

router = APIRouter(prefix="/user", tags=["user"])

# Maximum trade allocation (200% to allow for 2 lots equivalent)
MAX_TRADE_ALLOCATION = 200.0
MIN_TRADE_ALLOCATION = 0.01


def _get_or_create_user_settings(db: Session, user_id: int) -> UserSettings:
    """Get user settings or create with defaults if not found."""
    settings = db.query(UserSettings).filter(UserSettings.user_id == user_id).one_or_none()
    if not settings:
        settings = UserSettings(user_id=user_id, trade_allocation=10.0)
        db.add(settings)
        db.commit()
        db.refresh(settings)
    return settings


@router.get("/settings", response_model=UserSettingsOut)
def get_user_settings(
    user: User = Depends(auth_required),
    db: Session = Depends(get_db),
) -> UserSettingsOut:
    """Get user settings including trade allocation."""
    settings = _get_or_create_user_settings(db, user.id)
    return UserSettingsOut(trade_allocation=settings.trade_allocation)


@router.post("/settings", response_model=UserSettingsOut)
def create_user_settings(
    payload: UserSettingsIn,
    user: User = Depends(auth_required),
    db: Session = Depends(get_db),
) -> UserSettingsOut:
    """Create or update user settings."""
    # Validate trade_allocation
    if payload.trade_allocation is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="trade_allocation is required",
        )
    
    if payload.trade_allocation < MIN_TRADE_ALLOCATION:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"trade_allocation must be at least {MIN_TRADE_ALLOCATION}",
        )
    
    if payload.trade_allocation > MAX_TRADE_ALLOCATION:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"trade_allocation cannot exceed {MAX_TRADE_ALLOCATION}",
        )
    
    settings = db.query(UserSettings).filter(UserSettings.user_id == user.id).one_or_none()
    if settings:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="User settings already exist. Use PATCH to update.",
        )
    
    settings = UserSettings(
        user_id=user.id,
        trade_allocation=payload.trade_allocation,
    )
    db.add(settings)
    db.commit()
    db.refresh(settings)
    
    return UserSettingsOut(trade_allocation=settings.trade_allocation)


@router.patch("/settings", response_model=UserSettingsOut)
def update_user_settings(
    payload: UserSettingsIn,
    user: User = Depends(auth_required),
    db: Session = Depends(get_db),
) -> UserSettingsOut:
    """Update user settings."""
    settings = _get_or_create_user_settings(db, user.id)
    
    if payload.trade_allocation is not None:
        if payload.trade_allocation < MIN_TRADE_ALLOCATION:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"trade_allocation must be at least {MIN_TRADE_ALLOCATION}",
            )
        
        if payload.trade_allocation > MAX_TRADE_ALLOCATION:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"trade_allocation cannot exceed {MAX_TRADE_ALLOCATION}",
            )
        
        settings.trade_allocation = payload.trade_allocation
    
    db.add(settings)
    db.commit()
    db.refresh(settings)
    
    return UserSettingsOut(trade_allocation=settings.trade_allocation)

