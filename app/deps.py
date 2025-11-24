from fastapi import Depends, Header, HTTPException, status
from sqlalchemy.orm import Session
from app.db import get_db
from app.security import verify_jwt
from app.models import User, Subscription
from app.settings import settings

def db_session():
    return Depends(get_db)

def _admin_email_set() -> set[str]:
    """Backward compatibility helper - use settings.admin_emails_list instead."""
    return set(settings.admin_emails_list)


def _normalize_role(user: User, db: Session) -> User:
    """
    Normalize user role based on admin email list and existing role.
    - If user email is in admin_emails_list, set role to ADMIN
    - If user has no role and is not admin, default to USER
    - If role is invalid, default to USER
    - If user was ADMIN but no longer in admin list, downgrade to USER
    """
    current_role = user.role
    normalized_email = user.email.lower().strip() if user.email else None
    is_admin = normalized_email and normalized_email in settings.admin_emails_list
    
    # Determine target role
    if is_admin:
        # User is in admin list - always set to ADMIN
        target_role = "ADMIN"
    elif not current_role:
        # User has no role and is not admin - default to USER
        target_role = "USER"
    else:
        # User has a role - validate and normalize it
        current_role_upper = current_role.upper()
        if current_role_upper == "ADMIN" and not is_admin:
            # Was ADMIN but no longer in admin list - downgrade to USER
            target_role = "USER"
        elif current_role_upper not in {"ADMIN", "USER"}:
            # Invalid role - default to USER
            target_role = "USER"
        else:
            target_role = current_role_upper

    # Update role if it changed
    if current_role != target_role:
        user.role = target_role
        db.add(user)
        db.commit()
        db.refresh(user)
    elif current_role and current_role != current_role.upper():
        # Ensure role is stored uppercase even if unchanged
        user.role = current_role.upper()
        db.add(user)
        db.commit()
        db.refresh(user)

    return user


def auth_required(authorization: str = Header(default="", alias="Authorization"), db: Session = Depends(get_db)) -> User:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing Bearer token")
    token = authorization.split(" ", 1)[1]
    sub = verify_jwt(token)
    if not sub:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")
    
    # Try to find user by ID first (new auth flow), then by email (backward compatibility)
    user = None
    try:
        user_id = int(sub)
        user = db.query(User).filter(User.id == user_id).one_or_none()
    except (ValueError, TypeError):
        # sub is not a number, try email lookup (backward compatibility)
        pass
    
    if not user:
        # Fallback to email lookup for backward compatibility
        user = db.query(User).filter(User.email == sub).one_or_none()
    
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")
    return _normalize_role(user, db)

def subscription_required(user: User = Depends(auth_required), db: Session = Depends(get_db)) -> User:
    if (user.role or "").upper() == "ADMIN":
        return user
    sub = db.query(Subscription).filter(Subscription.user_id == user.id).order_by(Subscription.created_at.desc()).first()
    if not sub or sub.status not in ("trialing","active"):
        raise HTTPException(status_code=status.HTTP_402_PAYMENT_REQUIRED, detail="Subscription inactive")
    return user


def require_bot_key(x_bot_key: str = Header(default="", convert_underscores=False)) -> None:
    expected = settings.BOT_API_KEY
    if not expected:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="BOT_API_KEY not configured")
    if x_bot_key != expected:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Invalid bot key")
