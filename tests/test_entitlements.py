from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.entitlements import compute_entitlements, should_email_user_signal
from app.models import Base, Subscription, User
from app import mailchimp as mailchimp_module
from app.settings import settings


@pytest.fixture()
def db_session():
    engine = create_engine("sqlite:///:memory:")
    TestingSession = sessionmaker(bind=engine)
    Base.metadata.create_all(bind=engine)
    session = TestingSession()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=engine)


@pytest.fixture(autouse=True)
def stub_mailchimp(monkeypatch):
    monkeypatch.setattr(mailchimp_module, "is_on_waitlist", lambda email: False)
    yield


def test_tier1_entitlement_receives_signals(db_session, monkeypatch):
    user = User(email="tier1@example.com", has_tier1=True, role="USER")
    db_session.add(user)
    db_session.commit()

    now = datetime(2026, 3, 1, tzinfo=timezone.utc)
    ent = compute_entitlements(db_session, user, now=now)
    assert ent.can_receive_email_signals is True
    assert ent.can_trade is False


def test_tier2_active_can_trade(db_session):
    now = datetime.now(timezone.utc)
    user = User(email="tier2@example.com", role="USER")
    db_session.add(user)
    db_session.flush()
    sub = Subscription(
        user_id=user.id,
        plan="TIER2",
        status="active",
        current_period_end=now + timedelta(days=10),
        is_recurring=True,
    )
    db_session.add(sub)
    db_session.commit()

    ent = compute_entitlements(db_session, user, now=now)
    assert ent.tier2_active is True
    assert ent.can_trade is True
    assert should_email_user_signal(db_session, user.id, now=now) is True


def test_tier2_canceled_stops_trading(db_session):
    now = datetime.now(timezone.utc)
    user = User(email="cancel@example.com", role="USER")
    db_session.add(user)
    db_session.flush()
    sub = Subscription(
        user_id=user.id,
        plan="TIER2",
        status="canceled",
        current_period_end=now + timedelta(days=10),
        is_recurring=True,
    )
    db_session.add(sub)
    db_session.commit()

    ent = compute_entitlements(db_session, user, now=now)
    assert ent.can_trade is False


def test_beta_waitlist_grants_email_not_trading(db_session, monkeypatch):
    beta_now = datetime(2025, 12, 20, tzinfo=timezone.utc)
    monkeypatch.setattr(settings, "BETA_START", "2025-12-17")
    monkeypatch.setattr(settings, "BETA_END", "2026-02-12")
    monkeypatch.setattr(mailchimp_module, "is_on_waitlist", lambda email: True)

    user = User(email="waitlist@example.com", role="USER")
    db_session.add(user)
    db_session.commit()

    ent = compute_entitlements(db_session, user, now=beta_now)
    assert ent.can_receive_email_signals is True
    assert ent.beta_applied is True
    assert ent.can_trade is False


def test_beta_admin_can_trade(db_session, monkeypatch):
    beta_now = datetime(2026, 1, 5, tzinfo=timezone.utc)
    monkeypatch.setattr(settings, "BETA_START", "2025-12-17")
    monkeypatch.setattr(settings, "BETA_END", "2026-02-12")
    monkeypatch.setattr(mailchimp_module, "is_on_waitlist", lambda email: False)

    user = User(email="admin@example.com", role="ADMIN")
    db_session.add(user)
    db_session.flush()
    sub = Subscription(
        user_id=user.id,
        plan="TIER2",
        status="active",
        current_period_end=beta_now + timedelta(days=30),
        is_recurring=True,
    )
    db_session.add(sub)
    db_session.commit()

    ent = compute_entitlements(db_session, user, now=beta_now)
    assert ent.can_trade is True
    assert ent.can_receive_email_signals is True


def test_admin_override_entitlements(db_session, monkeypatch):
    monkeypatch.setattr(settings, "ADMIN_EMAILS", "boss@example.com")
    user = User(email="boss@example.com", role="ADMIN")
    db_session.add(user)
    db_session.commit()

    ent = compute_entitlements(db_session, user)
    assert ent.can_trade is True
    assert ent.can_receive_email_signals is True

