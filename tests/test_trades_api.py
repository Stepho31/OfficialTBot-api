import base64
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.main import app
from app.db import Base
from app.models import Account, Trade, User
from app.settings import settings


@pytest.fixture(scope="function")
def db_session(monkeypatch):
    engine = create_engine("sqlite:///:memory:")
    TestingSession = sessionmaker(bind=engine)
    Base.metadata.create_all(bind=engine)
    monkeypatch.setattr("app.db.SessionLocal", TestingSession)
    session = TestingSession()
    yield session
    session.close()
    Base.metadata.drop_all(bind=engine)


@pytest.fixture(autouse=True)
def patched_settings(monkeypatch):
    monkeypatch.setattr(settings, "JWT_SECRET", "test-secret")
    key = base64.b64encode(b"3" * 32).decode()
    monkeypatch.setattr(settings, "BROKER_SECRET_KEY", key)
    yield


@pytest.fixture
def client(monkeypatch, db_session):
    client = TestClient(app)
    monkeypatch.setattr("app.deps.verify_jwt", lambda token: token)
    return client


def seed_trade(session, user_id, account_id, **kwargs):
    trade = Trade(
        user_id=user_id,
        account_id=account_id,
        external_id=kwargs.get("external_id"),
        instrument=kwargs.get("instrument"),
        side=kwargs.get("side"),
        units=kwargs.get("units"),
        opened_at=kwargs.get("opened_at"),
        closed_at=kwargs.get("closed_at"),
        entry_price=kwargs.get("entry_price"),
        exit_price=kwargs.get("exit_price"),
        pnl_net=kwargs.get("pnl_net"),
        reason_close=kwargs.get("reason_close"),
    )
    session.add(trade)
    session.commit()
    return trade


def auth_header(email: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {email}"}


def test_trades_pagination_and_tenancy(db_session, client):
    user = User(email="alpha@example.com", role="user")
    other = User(email="beta@example.com", role="user")
    db_session.add_all([user, other])
    db_session.flush()

    account = Account(user_id=user.id, account_id="001-alpha", token_encrypted=None)
    other_account = Account(user_id=other.id, account_id="002-beta", token_encrypted=None)
    db_session.add_all([account, other_account])
    db_session.commit()

    base_time = datetime(2025, 1, 1, tzinfo=timezone.utc)
    seed_trade(
        db_session,
        user.id,
        account.id,
        external_id="t1",
        instrument="EURUSD",
        side="BUY",
        units=10000,
        opened_at=base_time + timedelta(hours=1),
        pnl_net=50.0,
    )
    second = seed_trade(
        db_session,
        user.id,
        account.id,
        external_id="t2",
        instrument="GBPUSD",
        side="SELL",
        units=8000,
        opened_at=base_time,
        closed_at=base_time + timedelta(hours=2),
        pnl_net=-25.0,
    )
    seed_trade(
        db_session,
        other.id,
        other_account.id,
        external_id="other",
        instrument="USDJPY",
        side="BUY",
        units=5000,
        opened_at=base_time,
    )

    resp = client.get(
        "/v1/trades?limit=1",
        headers=auth_header(user.email),
    )
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["items"]) == 1
    assert data["items"][0]["instrument"] == "EURUSD"
    assert data["nextCursor"] is not None

    resp2 = client.get(
        f"/v1/trades?cursor={data['nextCursor']}",
        headers=auth_header(user.email),
    )
    assert resp2.status_code == 200
    data2 = resp2.json()
    assert len(data2["items"]) == 1
    assert data2["items"][0]["instrument"] == "GBPUSD"

    # ensure other user's trades are not returned
    assert data2.get("nextCursor") is None

    # tenancy on detail fetch
    detail = client.get(f"/v1/trades/{second.id}", headers=auth_header(user.email))
    assert detail.status_code == 200
    other_detail = client.get(f"/v1/trades/{second.id}", headers=auth_header(other.email))
    assert other_detail.status_code == 404


def test_performance_summary(db_session, client):
    user = User(email="perf@example.com", role="user")
    db_session.add(user)
    db_session.flush()
    account = Account(user_id=user.id, account_id="perf-acc", token_encrypted=None)
    db_session.add(account)
    db_session.commit()

    base_time = datetime(2025, 6, 1, tzinfo=timezone.utc)
    seed_trade(
        db_session,
        user.id,
        account.id,
        external_id="win",
        instrument="EURUSD",
        side="BUY",
        units=10000,
        opened_at=base_time,
        closed_at=base_time + timedelta(hours=4),
        entry_price=1.1,
        exit_price=1.12,
        pnl_net=120.0,
    )
    seed_trade(
        db_session,
        user.id,
        account.id,
        external_id="loss",
        instrument="GBPUSD",
        side="SELL",
        units=8000,
        opened_at=base_time + timedelta(days=1),
        closed_at=base_time + timedelta(days=1, hours=2),
        pnl_net=-40.0,
    )

    resp = client.get("/v1/performance/summary", headers=auth_header(user.email))
    assert resp.status_code == 200
    body = resp.json()
    assert body["tradesCount"] == 2
    assert body["totalPnL"] == pytest.approx(80.0)
    assert body["winRate"] == pytest.approx(50.0)
    assert body["avgR"] == pytest.approx(40.0)
    assert body["periodStart"] is not None
    assert body["periodEnd"] is not None

