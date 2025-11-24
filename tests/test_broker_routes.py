import base64
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.main import app
from app.entitlements import compute_entitlements
from app import mailchimp as mailchimp_module
from app.db import Base
from app.models import Subscription, User
from app.settings import settings


DATABASE_URL = "sqlite:///:memory:"


@pytest.fixture(scope="function")
def db_session(monkeypatch):
    engine = create_engine(DATABASE_URL)
    TestingSession = sessionmaker(bind=engine)
    Base.metadata.create_all(bind=engine)
    session = TestingSession()
    monkeypatch.setattr("app.db.SessionLocal", lambda: session)
    yield session
    session.close()
    Base.metadata.drop_all(bind=engine)


@pytest.fixture(autouse=True)
def patched_settings(monkeypatch):
    key = base64.b64encode(b"1" * 32).decode()
    monkeypatch.setattr(settings, "BROKER_SECRET_KEY", key)
    monkeypatch.setattr(settings, "BETA_START", None)
    monkeypatch.setattr(settings, "BETA_END", None)
    monkeypatch.setattr(settings, "BOT_API_KEY", "test-bot")
    monkeypatch.setattr(mailchimp_module, "is_on_waitlist", lambda email: False)
    yield


@pytest.fixture
def client():
    return TestClient(app)


def _auth_header(email: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {email}"}


def _seed_user_with_tier2(session, email="trade@example.com"):
    user = User(email=email, role="user")
    session.add(user)
    session.flush()
    sub = Subscription(
        user_id=user.id,
        plan="TIER2",
        status="active",
        current_period_end=datetime.now(timezone.utc) + timedelta(days=30),
        is_recurring=True,
    )
    session.add(sub)
    session.commit()
    return user


def test_upsert_requires_entitlement(db_session, client):
    user = User(email="nope@example.com", role="user")
    db_session.add(user)
    db_session.commit()

    resp = client.put(
        "/v1/me/broker",
        json={"oandaAccountId": "ABC", "oandaApiKey": "secret"},
        headers=_auth_header(user.email),
    )
    assert resp.status_code == 403


def test_upsert_and_fetch_masked(db_session, client):
    user = _seed_user_with_tier2(db_session)

    resp = client.put(
        "/v1/me/broker",
        json={"oandaAccountId": "001-123-789", "oandaApiKey": "api-abc"},
        headers=_auth_header(user.email),
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["hasBrokerCreds"] is True
    assert body["oandaAccountId"] == "001-123-789"
    assert body["updatedAt"] is not None

    status_resp = client.get("/v1/me/broker", headers=_auth_header(user.email))
    status = status_resp.json()
    assert status["hasBrokerCreds"] is True
    assert status["oandaAccountId"] == "001-123-789"
    assert "apiKey" not in status


def test_internal_fetch_requires_bot_key(db_session, client):
    user = _seed_user_with_tier2(db_session)
    client.put(
        "/v1/me/broker",
        json={"oandaAccountId": "001-123-789", "oandaApiKey": "api-xyz"},
        headers=_auth_header(user.email),
    )

    missing = client.get(f"/v1/internal/broker?userId={user.id}")
    assert missing.status_code == 403

    ok = client.get(
        f"/v1/internal/broker?userId={user.id}",
        headers={"x-bot-key": "test-bot"},
    )
    assert ok.status_code == 200
    payload = ok.json()
    assert payload["oandaAccountId"] == "001-123-789"
    assert payload["oandaApiKey"] == "api-xyz"

