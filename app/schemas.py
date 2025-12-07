from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, EmailStr, Field


class MeOut(BaseModel):
    id: int
    email: EmailStr
    role: str
    has_tier1: bool = Field(alias="hasTier1")
    stripe_customer_id: Optional[str] = Field(default=None, alias="stripeCustomerId")

    class Config:
        allow_population_by_field_name = True


class SubscriptionOut(BaseModel):
    plan: Optional[str] = None
    status: Optional[str] = None
    current_period_end: Optional[datetime] = Field(default=None, alias="currentPeriodEnd")
    is_recurring: bool = Field(default=False, alias="isRecurring")
    stripe_subscription_id: Optional[str] = Field(default=None, alias="stripeSubscriptionId")

    class Config:
        allow_population_by_field_name = True


class EntitlementsOut(BaseModel):
    can_receive_email_signals: bool = Field(alias="canReceiveEmailSignals")
    can_trade: bool = Field(alias="canTrade")
    can_access_dashboard: bool = Field(alias="canAccessDashboard")
    tier1: bool
    tier2_status: Optional[str] = Field(default=None, alias="tier2Status")
    tier2_active: bool = Field(default=False, alias="tier2Active")
    beta_applied: bool = Field(default=False, alias="betaApplied")

    class Config:
        allow_population_by_field_name = True

class CheckoutSessionOut(BaseModel):
    url: str

class AccountConnectIn(BaseModel):
    account_id: str
    token: Optional[str] = None
    label: Optional[str] = None

class AccountStatusOut(BaseModel):
    account_id: str
    connected: bool
    last_checked: Optional[datetime] = None

class DashboardSummaryOut(BaseModel):
    account_id: int
    wtd_pnl: float
    wins: int
    losses: int
    win_rate: float
    balance: float | None = None
    equity: float | None = None

class TradeOut(BaseModel):
    trade_id: Optional[str] = None
    instrument: Optional[str]
    side: Optional[str]
    units: Optional[int]
    opened_at: Optional[datetime]
    closed_at: Optional[datetime]
    entry_price: Optional[float]
    exit_price: Optional[float]
    pnl_net: Optional[float]
    status: Optional[str] = None
    unrealized_pnl: Optional[float] = None

class EquityPoint(BaseModel):
    taken_at: datetime
    equity: float | None = None

class PaidEmailsOut(BaseModel):
    emails: List[EmailStr]


class TradeIn(BaseModel):
    account_id: str
    trade_id: str
    instrument: Optional[str] = None
    side: Optional[str] = None
    position_size: Optional[int] = None
    opened_at: Optional[datetime] = None
    closed_at: Optional[datetime] = None
    entry_price: Optional[float] = None
    exit_price: Optional[float] = None
    realized_pnl: Optional[float] = None
    meta: Optional[Dict[str, Any]] = None


class TradeInAck(BaseModel):
    ok: bool
    upserted: bool


class SnapshotIn(BaseModel):
    account_id: str
    timestamp: datetime
    balance: float
    equity: float
    margin_used: float


class SnapshotAck(BaseModel):
    ok: bool


class SignalIn(BaseModel):
    signal_id: str
    created_at: Optional[datetime] = None
    pair: Optional[str] = None
    direction: Optional[str] = None
    entry: Optional[float] = None
    sl: Optional[float] = None
    tp: Optional[float] = None
    rationale: Optional[str] = None


class SignalAck(BaseModel):
    ok: bool


class BrokerUpsertIn(BaseModel):
    oandaAccountId: str
    oandaApiKey: str


class BrokerStatusOut(BaseModel):
    hasBrokerCreds: bool
    oandaAccountId: Optional[str] = None
    updatedAt: Optional[datetime] = None


class BrokerSecretOut(BaseModel):
    oandaAccountId: str
    oandaApiKey: str


class InternalTradeIn(BaseModel):
    userId: int
    externalTradeId: str
    symbol: str
    side: str
    size: int
    entry: Optional[float] = None
    tp: Optional[float] = None
    sl: Optional[float] = None
    status: str
    pnl: Optional[float] = None
    openedAt: Optional[datetime] = None
    closedAt: Optional[datetime] = None
    timeframe: Optional[str] = None
    oandaAccountId: Optional[str] = None


class TradeAck(BaseModel):
    ok: bool
    upserted: bool


class EquityServerIn(BaseModel):
    userId: int
    oandaAccountId: Optional[str] = None
    timestamp: datetime
    balance: float
    equity: float
    marginUsed: float


class EquityServerOut(BaseModel):
    ok: bool
    upserted: bool


class TradeDetailOut(BaseModel):
    id: str
    instrument: Optional[str] = None
    side: Optional[str] = None
    size: Optional[int] = None
    entry: Optional[float] = None
    exit: Optional[float] = None
    pnl: Optional[float] = None
    status: Optional[str] = None
    openedAt: Optional[datetime] = None
    closedAt: Optional[datetime] = None


class TradeListOut(BaseModel):
    items: List[TradeDetailOut]
    nextCursor: Optional[str] = None


class PerformanceSummaryOut(BaseModel):
    totalPnL: float
    winRate: float
    avgR: float
    tradesCount: int
    periodStart: Optional[datetime] = None
    periodEnd: Optional[datetime] = None


class AccountSummaryOut(BaseModel):
    balance: float
    equity: Optional[float] = Field(default=None, alias="equity")
    marginAvailable: Optional[float] = Field(default=None, alias="marginAvailable")
    currency: str

    class Config:
        allow_population_by_field_name = True


class Tier2UserOut(BaseModel):
    userId: int
    email: EmailStr
    oandaAccountId: str
    oandaApiKey: str


class Tier2UsersOut(BaseModel):
    users: List[Tier2UserOut]


class UserSettingsOut(BaseModel):
    trade_allocation: float

    class Config:
        allow_population_by_field_name = True


class UserSettingsIn(BaseModel):
    trade_allocation: float | None = None


class UserSettingsInternalOut(BaseModel):
    tradeAllocation: float
