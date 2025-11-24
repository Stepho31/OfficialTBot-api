import base64
from datetime import datetime, timezone

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
    key = base64.b64encode(b"2" * 32).decode()
    monkeypatch.setattr(settings, "BROKER_SECRET_KEY", key)
    monkeypatch.setattr(settings, "BOT_API_KEY", "test-bot")
    yield


@pytest.fixture
def client():
    return TestClient(app)


def seed_user_with_account(session, email="test@example.com"):
    user = User(email=email, role="user")
    session.add(user)
    session.flush()
    account = Account(user_id=user.id, account_id="001-ABC", token_encrypted=None, broker="OANDA")
    session.add(account)
    session.commit()
    return user.id, account.account_id


def test_trade_upsert_idempotent(db_session, client):
    user_id, account_ref = seed_user_with_account(db_session)
    payload = {
        "userId": user_id,
        "externalTradeId": "trade-123",
        "symbol": "EURUSD",
        "side": "BUY",
        "size": 10000,
        "entry": 1.07215,
        "tp": 1.07415,
        "sl": 1.07015,
        "status": "OPEN",
        "pnl": None,
        "openedAt": datetime.now(timezone.utc).isoformat(),
        "closedAt": None,
        "timeframe": "H4",
        "oandaAccountId": account_ref,
    }

    headers = {"x-bot-key": "test-bot"}
    resp = client.post("/v1/internal/trades", json=payload, headers=headers)
    assert resp.status_code == 200
    assert resp.json() == {"ok": True, "upserted": True}

    payload["status"] = "CLOSED"
    payload["pnl"] = 12.5
    resp2 = client.post("/v1/internal/trades", json=payload, headers=headers)
    assert resp2.status_code == 200
    assert resp2.json() == {"ok": True, "upserted": False}

    trades = db_session.query(Trade).filter(Trade.user_id == user_id).all()
    assert len(trades) == 1
    assert float(trades[0].pnl_net) == pytest.approx(12.5)


def test_equity_snapshot_upsert(db_session, client):
    user_id, account_ref = seed_user_with_account(db_session)
    ts = datetime(2025, 1, 1, tzinfo=timezone.utc).isoformat()
    payload = {
        "userId": user_id,
        "oandaAccountId": account_ref,
        "timestamp": ts,
        "balance": 10000.0,
        "equity": 10050.0,
        "marginUsed": 250.0,
    }

    headers = {"x-bot-key": "test-bot"}
    resp = client.post("/v1/internal/equity", json=payload, headers=headers)
    assert resp.status_code == 200
    assert resp.json() == {"ok": True, "upserted": True}

    payload["equity"] = 10070.0
    resp2 = client.post("/v1/internal/equity", json=payload, headers=headers)
    assert resp2.status_code == 200
    assert resp2.json() == {"ok": True, "upserted": False}

