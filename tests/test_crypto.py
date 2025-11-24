import base64

import pytest

from app import crypto
from app.settings import settings


@pytest.fixture(autouse=True)
def broker_key(monkeypatch):
    key = base64.b64encode(b"0" * 32).decode()
    monkeypatch.setattr(settings, "BROKER_SECRET_KEY", key)
    yield


def test_encrypt_decrypt_round_trip():
    secret = "super-secret-api-key"
    encrypted = crypto.encrypt_api_key(secret)
    recovered = crypto.decrypt_api_key(encrypted["cipher"], encrypted["iv"], encrypted["tag"])
    assert recovered == secret

