from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, EmailStr
from sqlalchemy.orm import Session
from datetime import datetime, timezone, timedelta
from typing import Optional
import secrets
import logging

from app.db import get_db
from app.models import User, BrokerCredential
from app.entitlements import compute_entitlements
from app.schemas import EntitlementsOut
from app.security import hash_password, verify_password, create_jwt
from app.crypto import encrypt_api_key
from app.settings import settings
from app.emails import send_password_reset_email

router = APIRouter(prefix="/auth", tags=["auth"])

logger = logging.getLogger(__name__)


class AuthRegisterRequest(BaseModel):
    email: EmailStr
    password: str
    oanda_account_id: Optional[str] = None
    oanda_api_key: Optional[str] = None


class AuthLoginRequest(BaseModel):
    email: EmailStr
    password: str


class AuthResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    email: EmailStr
    can_access_dashboard: bool
    entitlements: EntitlementsOut


def _compute_can_access_dashboard(entitlements, user: User, db: Session) -> bool:
    """
    Compute whether user can access dashboard based on entitlements.
    
    Rules:
    - ADMIN role (including super admins): always allowed
    - Tier-2 active: allowed
    - Tier-1, waitlist, or free users: NOT allowed
    - Local dev mode (no STRIPE_SECRET_KEY): allow all registered users (for development)
    """
    user_role = (user.role or "USER").upper()
    
    # Check if user is admin (including super admin via SIGNAL_SUPERADMIN_EMAIL)
    if user_role == "ADMIN":
        logger.debug(f"User {user.email} has ADMIN role - granting dashboard access")
        return True

    # Local dev mode: if Stripe is not configured, allow dashboard access for development
    if not settings.STRIPE_SECRET_KEY:
        logger.debug(f"Stripe not configured - allowing dashboard access for {user.email}")
        return True

    # Use the can_access_dashboard from entitlements (computed in compute_entitlements)
    # This ensures: Tier-2 active = True, Tier-1/waitlist/free = False
    result = entitlements.can_access_dashboard
    logger.debug(f"Dashboard access for {user.email}: {result} (tier2_active: {entitlements.tier2_active})")
    return result


@router.post("/register", response_model=AuthResponse)
def register(payload: AuthRegisterRequest, db: Session = Depends(get_db)):
    # Normalize email
    email = payload.email.lower().strip()
    
    # Check if this is an admin email (bypasses eligibility/subscription gating)
    # Include both ADMIN_EMAILS and SIGNAL_SUPERADMIN_EMAIL
    is_admin_email = email in settings.admin_emails_list
    if not is_admin_email and settings.SIGNAL_SUPERADMIN_EMAIL:
        is_admin_email = email == settings.SIGNAL_SUPERADMIN_EMAIL.lower().strip()

    # ---- 1. User MUST already exist (pre-provisioned from Mailchimp / Stripe sync) ----
    # EXCEPTION: Admin emails can register without pre-provisioning
    user = db.query(User).filter(User.email == email).first()
    if not user:
        if is_admin_email:
            # Create user for admin email (bypasses subscription gating)
            user = User(
                email=email,
                status="INVITED",
                email_verified=False,
                password_hash=None,
                role=None,  # Will be set to ADMIN by _normalize_role
                has_tier1=False,
            )
            db.add(user)
            db.flush()
        else:
            # Non-admin emails must be pre-provisioned
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="This email is not eligible for registration yet. Please complete your subscription first.",
            )

    # ---- 2. If they already have a password, account is already activated ----
    if user.password_hash:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Account already activated. Please log in instead.",
        )

    # ---- 3. Normalize role BEFORE computing entitlements (will set ADMIN if email is in ADMIN_EMAILS) ----
    from app.deps import _normalize_role
    user = _normalize_role(user, db)

    # ---- 4. Compute entitlements for this pre-provisioned user ----
    now = datetime.now(timezone.utc)
    ents = compute_entitlements(db, user, now)

    # Require at least Tier 1 or Tier 2 active in production before allowing registration (ADMIN users bypass this)
    # Tier 1 users can register but won't have dashboard access
    user_role = (user.role or "USER").upper()
    if settings.STRIPE_SECRET_KEY and user_role != "ADMIN":
        # Allow registration if user has Tier 1 or Tier 2
        has_tier1 = ents.tier1
        has_tier2 = ents.tier2_active
        if not (has_tier1 or has_tier2):
            raise HTTPException(
                status_code=status.HTTP_402_PAYMENT_REQUIRED,
                detail="PAYMENT_REQUIRED",
            )

    # ---- 5. Activate the user: set password & base flags ----
    user.password_hash = hash_password(payload.password)
    user.status = "ACTIVE"
    user.email_verified = True  # you can change this if you later want email verification

    db.add(user)
    db.commit()
    db.refresh(user)

    # ---- 6. If broker credentials are provided, upsert BrokerCredential ----
    if payload.oanda_account_id and payload.oanda_api_key:
        encrypted = encrypt_api_key(payload.oanda_api_key)

        credential = (
            db.query(BrokerCredential)
            .filter(BrokerCredential.user_id == user.id)
            .one_or_none()
        )
        if credential:
            credential.oanda_account_id = payload.oanda_account_id
            credential.enc_api_key = encrypted["cipher"]
            credential.enc_iv = encrypted["iv"]
            credential.enc_tag = encrypted["tag"]
        else:
            credential = BrokerCredential(
                user_id=user.id,
                oanda_account_id=payload.oanda_account_id,
                enc_api_key=encrypted["cipher"],
                enc_iv=encrypted["iv"],
                enc_tag=encrypted["tag"],
            )
            db.add(credential)

        db.commit()

    # ---- 7. Recompute entitlements (optional but clean) ----
    ents = compute_entitlements(db, user, now)

    # Compute dashboard access
    can_access_dashboard = _compute_can_access_dashboard(ents, user, db)

    # Create JWT with user.id as sub
    token = create_jwt(sub=str(user.id))

    # Convert entitlements to response schema (camelCase field names)
    ents_out = EntitlementsOut(
        canReceiveEmailSignals=ents.can_receive_email_signals,
        canTrade=ents.can_trade,
        canAccessDashboard=ents.can_access_dashboard,
        tier1=ents.tier1,
        tier2Status=ents.tier2_status,
        tier2Active=ents.tier2_active,
        betaApplied=ents.beta_applied,
    )

    return AuthResponse(
        access_token=token,
        email=user.email,
        can_access_dashboard=can_access_dashboard,
        entitlements=ents_out,
    )


@router.post("/login", response_model=AuthResponse)
def login(payload: AuthLoginRequest, db: Session = Depends(get_db)):
    email = payload.email.lower().strip()
    logger.info(f"Login attempt for email: {email}")
    
    user = db.query(User).filter(User.email == email).first()
    if not user or not user.password_hash or not verify_password(payload.password, user.password_hash):
        logger.warning(f"Login failed: Invalid credentials for {email}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
        )

    # Normalize role (this will set ADMIN if email is in ADMIN_EMAILS or SIGNAL_SUPERADMIN_EMAIL)
    from app.deps import _normalize_role
    user = _normalize_role(user, db)
    logger.info(f"User role after normalization: {user.role} for {email}")

    # Compute entitlements
    now = datetime.now(timezone.utc)
    ents = compute_entitlements(db, user, now)

    # Compute dashboard access
    can_access_dashboard = _compute_can_access_dashboard(ents, user, db)
    logger.info(f"Dashboard access for {email}: {can_access_dashboard} (role: {user.role}, tier2_active: {ents.tier2_active})")

    # If not entitled in production, return a special error so the UI can redirect to Stripe
    # Only admins, super admins, and Tier-2 users can login
    if not can_access_dashboard and settings.STRIPE_SECRET_KEY:
        logger.warning(f"Login blocked: User {email} does not have dashboard access (role: {user.role}, tier2_active: {ents.tier2_active})")
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail="PAYMENT_REQUIRED",
        )

    # Create JWT with user.id as sub
    token = create_jwt(sub=str(user.id))

    # Convert entitlements to response schema
    ents_out = EntitlementsOut(
        canReceiveEmailSignals=ents.can_receive_email_signals,
        canTrade=ents.can_trade,
        canAccessDashboard=ents.can_access_dashboard,
        tier1=ents.tier1,
        tier2Status=ents.tier2_status,
        tier2Active=ents.tier2_active,
        betaApplied=ents.beta_applied,
    )

    return AuthResponse(
        access_token=token,
        email=user.email,
        can_access_dashboard=can_access_dashboard,
        entitlements=ents_out,
    )


class ForgotPasswordRequest(BaseModel):
    email: EmailStr


class ResetPasswordRequest(BaseModel):
    token: str
    new_password: str


class ForgotPasswordResponse(BaseModel):
    message: str


class ResetPasswordResponse(BaseModel):
    message: str


@router.post("/forgot-password", response_model=ForgotPasswordResponse)
def forgot_password(payload: ForgotPasswordRequest, db: Session = Depends(get_db)):
    """
    Request a password reset. Generates a reset token and sends an email.
    Always returns success (to prevent email enumeration attacks).
    
    **Endpoint:** POST /auth/forgot-password
    """
    email = payload.email.lower().strip()
    user = db.query(User).filter(User.email == email).first()
    
    # Always return success to prevent email enumeration
    if user and user.password_hash:
        # Generate a secure random token
        reset_token = secrets.token_urlsafe(32)
        
        # Set token and expiration (1 hour from now)
        user.password_reset_token = reset_token
        user.password_reset_expires = datetime.now(timezone.utc) + timedelta(hours=1)
        db.commit()
        
        # Generate reset link
        frontend_url = settings.FRONTEND_ORIGIN or settings.PUBLIC_CLIENT_URL
        reset_link = f"{frontend_url}/reset-password?token={reset_token}"

        # Log the reset link so you can grab it from Render logs if email fails
        logger.info("Password reset link for %s: %s", email, reset_link)
        
        # Try to send reset email, but don't let failures crash the endpoint
        try:
            send_password_reset_email(email, reset_link)
        except Exception:
            logger.exception("Failed to send password reset email for %s", email)

    # Always return success message (security best practice)
    return ForgotPasswordResponse(
        message="If an account with that email exists, a password reset link has been sent."
    )


@router.post("/reset-password", response_model=ResetPasswordResponse)
def reset_password(payload: ResetPasswordRequest, db: Session = Depends(get_db)):
    """
    Reset password using a valid reset token.
    
    **Endpoint:** POST /auth/reset-password
    """
    # Find user by reset token
    user = db.query(User).filter(
        User.password_reset_token == payload.token,
        User.password_reset_expires > datetime.now(timezone.utc)
    ).first()
    
    if not user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired reset token",
        )
    
    # Validate password length
    if len(payload.new_password) < 8:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Password must be at least 8 characters long",
        )
    
    # Update password and clear reset token
    user.password_hash = hash_password(payload.new_password)
    user.password_reset_token = None
    user.password_reset_expires = None
    
    db.commit()
    
    return ResetPasswordResponse(
        message="Password has been reset successfully. You can now log in with your new password."
    )
