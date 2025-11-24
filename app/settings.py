# app/settings.py
from __future__ import annotations
from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import Optional


class Settings(BaseSettings):
    # Core
    DATABASE_URL: str
    JWT_SECRET: str
    BOT_API_KEY: str
    BROKER_SECRET_KEY: str
    ENCRYPTION_KEY: str

    # Stripe (optional locally)
    STRIPE_SECRET_KEY: Optional[str] = None
    STRIPE_WEBHOOK_SECRET: Optional[str] = None
    STRIPE_PRICE_TIER1_ONETIME: Optional[str] = None
    STRIPE_PRICE_TIER2_MONTHLY: Optional[str] = None
    STRIPE_TIER1_LOOKUP_KEY: str = "tier1"
    STRIPE_TIER2_LOOKUP_KEY: str = "tier2-monthly"

    # UI base
    PUBLIC_CLIENT_URL: str = "http://localhost:3000"
    FRONTEND_ORIGIN: Optional[str] = None
    DEV_ALLOW_ALL_CORS: bool = False
    
    # Beta window (optional)
    BETA_START: Optional[str] = None       # e.g., "2025-12-17"
    BETA_END: Optional[str] = None         # e.g., "2026-02-12"
    
    # Free signals cutoff (optional)
    # Supports ISO format: "2026-02-17T23:59:59Z" or date format: "2026-02-17"
    FREE_SIGNALS_UNTIL: Optional[str] = None  # Free users receive signals until this date/time

    # Mailchimp (optional)
    MAILCHIMP_API_KEY: Optional[str] = None
    MAILCHIMP_LIST_ID: Optional[str] = None

    # OANDA (optional, defaults to practice)
    OANDA_ENV: str = "live"  # "practice" or "live"

    # Admins (comma-separated emails)
    ADMIN_EMAILS: Optional[str] = None
    
    # Super-admin for trade signals (optional, falls back to ADMIN_EMAILS)
    # This email receives ALL diagnostic emails (accepted, rejected, validation errors)
    SIGNAL_SUPERADMIN_EMAIL: Optional[str] = None

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",  # ignore unexpected envs to be lenient
    )

    @property
    def admin_emails_list(self) -> list[str]:
        """Returns a lowercased list of admin emails parsed from ADMIN_EMAILS."""
        if not self.ADMIN_EMAILS:
            return []
        return [email.strip().lower() for email in self.ADMIN_EMAILS.split(",") if email.strip()]

settings = Settings()

if not settings.FRONTEND_ORIGIN:
    # fall back to PUBLIC_CLIENT_URL for older code paths
    object.__setattr__(settings, "FRONTEND_ORIGIN", settings.PUBLIC_CLIENT_URL)