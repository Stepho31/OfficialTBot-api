from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy.orm import Session

from app.mailchimp import is_on_waitlist
from app.models import Subscription, User
from app.settings import settings


ACTIVE_SUB_STATUSES = {"trialing", "active"}


@dataclass
class Entitlements:
    can_receive_email_signals: bool
    can_trade: bool
    can_access_dashboard: bool
    tier1: bool
    tier2_status: Optional[str]
    tier2_active: bool
    beta_applied: bool


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _parse_date(date_str: Optional[str]) -> Optional[datetime]:
    """Parse date string in ISO format (YYYY-MM-DD or YYYY-MM-DDTHH:MM:SSZ) or date format (YYYY-MM-DD)."""
    if not date_str:
        return None
    try:
        # Try ISO format first (e.g., "2026-02-17T23:59:59Z" or "2026-02-17T23:59:59+00:00")
        if "T" in date_str or "Z" in date_str or "+" in date_str:
            # Parse ISO format
            if date_str.endswith("Z"):
                date_str = date_str[:-1] + "+00:00"
            return datetime.fromisoformat(date_str.replace("Z", "+00:00"))
        # Try simple date format (YYYY-MM-DD)
        return datetime.strptime(date_str, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    except (ValueError, AttributeError):
        return None


def is_in_beta_window(now: Optional[datetime] = None) -> bool:
    now = now or _utc_now()
    start = _parse_date(settings.BETA_START)
    end = _parse_date(settings.BETA_END)
    if not start or not end:
        return False
    return start <= now <= end


def _latest_subscription(db: Session, user_id: int) -> Optional[Subscription]:
    """Get the latest Tier2 subscription for a user (matching STRIPE_TIER2_LOOKUP_KEY)."""
    return (
        db.query(Subscription)
        .filter(Subscription.user_id == user_id, Subscription.plan == "TIER2")
        .order_by(Subscription.created_at.desc())
        .first()
    )


def _has_tier1_subscription(db: Session, user_id: int) -> bool:
    """Check if user has an active Tier1 subscription (matching STRIPE_TIER1_LOOKUP_KEY)."""
    tier1_sub = (
        db.query(Subscription)
        .filter(Subscription.user_id == user_id, Subscription.plan == "TIER1")
        .first()
    )
    return tier1_sub is not None


def compute_entitlements(db: Session, user: User, now: Optional[datetime] = None) -> Entitlements:
    now = now or _utc_now()
    user_role = (user.role or "USER").upper()
    
    # ADMIN users bypass all billing logic and get full entitlements
    if user_role == "ADMIN":
        return Entitlements(
            can_receive_email_signals=True,
            can_trade=True,
            can_access_dashboard=True,
            tier1=True,
            tier2_status="active",
            tier2_active=True,
            beta_applied=True,
        )

    tier2 = _latest_subscription(db, user.id)
    tier2_status = (tier2.status or "").lower() if tier2 and tier2.status else None
    period_end = tier2.current_period_end if tier2 else None
    if period_end and period_end.tzinfo is None:
        period_end = period_end.replace(tzinfo=timezone.utc)

    tier2_active = bool(
        tier2
        and tier2_status in ACTIVE_SUB_STATUSES
        and (not period_end or period_end >= now)
    )

    # Check for Tier1 subscription (separate from Tier2)
    has_tier1_sub = _has_tier1_subscription(db, user.id)
    # tier1 flag indicates user has Tier 1 access (either via subscription or legacy flag)
    tier1 = bool(user.has_tier1 or has_tier1_sub)

    # Check free signals cutoff date
    free_signals_until = _parse_date(settings.FREE_SIGNALS_UNTIL)
    is_before_cutoff = free_signals_until is not None and now < free_signals_until

    # Beta window and waitlist logic (only applies before FREE_SIGNALS_UNTIL)
    beta = is_in_beta_window(now)
    waitlist_grant = False
    if is_before_cutoff and beta:
        waitlist_grant = is_on_waitlist(user.email)
        if waitlist_grant:
            tier1 = True  # Grant tier1 flag for waitlist users before cutoff

    # Apply rules based on tier status (priority: Tier 2 > Tier 1 > Free/Waitlist):
    # If user has active Tier-2:
    # If user has active Tier-2:
    if tier2_active:
        can_trade = True
        can_receive = True
        can_access_dashboard = True
        tier1 = True  # Tier 2 users also have tier1 benefits
    # Else if user has Tier-1 (from subscription or legacy flag):
    elif tier1:
        can_trade = False
        can_receive = True
        can_access_dashboard = False
    # Else if now < FREE_SIGNALS_UNTIL and user is on waitlist (free signals window):
    elif is_before_cutoff and waitlist_grant:
        can_trade = False
        can_receive = True
        can_access_dashboard = False
    # Else (free users, no subscription):
    # After FREE_SIGNALS_UNTIL, no free signals; before cutoff, no waitlist = no signals
    else:
        can_trade = False
        can_receive = False
        can_access_dashboard = False

    # Beta window: disable trading for non-admins during beta
    if beta and user_role != "ADMIN":
        can_trade = False

    return Entitlements(
        can_receive_email_signals=can_receive,
        can_trade=can_trade,
        can_access_dashboard=can_access_dashboard,
        tier1=tier1,
        tier2_status=tier2_status,
        tier2_active=tier2_active,
        beta_applied=bool(beta and waitlist_grant),
    )


def should_email_user_signal(db: Session, user_id: int, now: Optional[datetime] = None) -> bool:
    user = db.get(User, user_id)
    if not user:
        return False
    entitlements = compute_entitlements(db, user, now=now)
    return entitlements.can_receive_email_signals

