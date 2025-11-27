from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import List, Optional

from sqlalchemy import (
    String,
    Boolean,
    Text,
    TIMESTAMP,
    ForeignKey,
    Numeric,
    UniqueConstraint,
    LargeBinary,
)
from sqlalchemy.orm import relationship, Mapped, mapped_column, DeclarativeBase
from sqlalchemy.sql import func
from uuid import uuid4


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    email: Mapped[str] = mapped_column(String, unique=True, nullable=False)
    stripe_customer_id: Mapped[Optional[str]] = mapped_column(String, unique=True, nullable=True)
    status: Mapped[str] = mapped_column(String, default="PENDING_PASSWORD")
    email_verified: Mapped[bool] = mapped_column(Boolean, default=False)
    role: Mapped[str] = mapped_column(String(32), default="USER")
    has_tier1: Mapped[bool] = mapped_column(Boolean, default=False)
    password_hash: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    password_reset_token: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    password_reset_expires: Mapped[Optional[datetime]] = mapped_column(TIMESTAMP(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), server_default=func.now(), nullable=False)

    subscriptions: Mapped[List["Subscription"]] = relationship(back_populates="user")
    accounts: Mapped[List["Account"]] = relationship(back_populates="user")
    broker_credential: Mapped[Optional["BrokerCredential"]] = relationship(
        back_populates="user", uselist=False
    )


class Subscription(Base):
    __tablename__ = "subscriptions"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)

    stripe_customer_id: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    stripe_subscription_id: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    status: Mapped[Optional[str]] = mapped_column(String, nullable=True)

    current_period_end: Mapped[Optional[datetime]] = mapped_column(TIMESTAMP(timezone=True), nullable=True)
    plan: Mapped[Optional[str]] = mapped_column(String, nullable=True)

    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
    is_recurring: Mapped[bool] = mapped_column(Boolean, default=False)

    user: Mapped["User"] = relationship(back_populates="subscriptions")


class Account(Base):
    __tablename__ = "accounts"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)

    broker: Mapped[str] = mapped_column(String, default="OANDA")
    account_id: Mapped[str] = mapped_column(String, nullable=False)

    token_encrypted: Mapped[Optional[bytes]] = mapped_column(LargeBinary, nullable=True)
    label: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    is_primary: Mapped[bool] = mapped_column(Boolean, default=True)

    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), server_default=func.now(), nullable=False)

    user: Mapped["User"] = relationship(back_populates="accounts")


class Trade(Base):
    __tablename__ = "trades"
    __table_args__ = (UniqueConstraint("user_id", "external_id", name="uq_trades_user_external"),)

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    account_id: Mapped[int] = mapped_column(ForeignKey("accounts.id"), nullable=False)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)

    external_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    instrument: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    side: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    units: Mapped[Optional[int]] = mapped_column(nullable=True)

    opened_at: Mapped[Optional[datetime]] = mapped_column(TIMESTAMP(timezone=True), nullable=True)
    closed_at: Mapped[Optional[datetime]] = mapped_column(TIMESTAMP(timezone=True), nullable=True)

    entry_price: Mapped[Optional[Decimal]] = mapped_column(Numeric(18, 6), nullable=True)
    exit_price: Mapped[Optional[Decimal]] = mapped_column(Numeric(18, 6), nullable=True)
    commission: Mapped[Optional[Decimal]] = mapped_column(Numeric(18, 6), nullable=True)
    spread_cost: Mapped[Optional[Decimal]] = mapped_column(Numeric(18, 6), nullable=True)
    slippage_cost: Mapped[Optional[Decimal]] = mapped_column(Numeric(18, 6), nullable=True)
    pnl_net: Mapped[Optional[Decimal]] = mapped_column(Numeric(18, 6), nullable=True)

    reason_open: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    reason_close: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    user: Mapped["User"] = relationship()
    account: Mapped["Account"] = relationship()


class EquitySnapshot(Base):
    __tablename__ = "equity_snapshots"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    account_id: Mapped[int] = mapped_column(ForeignKey("accounts.id"), nullable=False)

    taken_at: Mapped[Optional[datetime]] = mapped_column(TIMESTAMP(timezone=True), nullable=True)
    balance: Mapped[Optional[Decimal]] = mapped_column(Numeric(18, 6), nullable=True)
    equity: Mapped[Optional[Decimal]] = mapped_column(Numeric(18, 6), nullable=True)
    margin_used: Mapped[Optional[Decimal]] = mapped_column(Numeric(18, 6), nullable=True)


class Tier1Cache(Base):
    __tablename__ = "tier1_cache"

    email: Mapped[str] = mapped_column(String, primary_key=True)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    refreshed_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default=func.now(), nullable=False
    )


class Signal(Base):
    __tablename__ = "signals"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    signal_id: Mapped[str] = mapped_column(String(128), unique=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), server_default=func.now(), nullable=False)

    symbol: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    direction: Mapped[Optional[str]] = mapped_column(String(8), nullable=True)
    entry: Mapped[Optional[Decimal]] = mapped_column(Numeric(18, 6), nullable=True)
    sl: Mapped[Optional[Decimal]] = mapped_column(Numeric(18, 6), nullable=True)
    tp: Mapped[Optional[Decimal]] = mapped_column(Numeric(18, 6), nullable=True)
    rationale: Mapped[Optional[str]] = mapped_column(Text, nullable=True)


class BrokerCredential(Base):
    __tablename__ = "broker_credentials"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, unique=True)

    oanda_account_id: Mapped[str] = mapped_column(String(64), nullable=False)
    enc_api_key: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    enc_iv: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    enc_tag: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)

    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    user: Mapped["User"] = relationship(back_populates="broker_credential")
