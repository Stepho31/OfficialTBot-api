from __future__ import annotations

import base64
import os
from typing import Dict

from cryptography.fernet import Fernet
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from app.settings import settings

_f = (
    Fernet(
        settings.ENCRYPTION_KEY.encode()
        if not settings.ENCRYPTION_KEY.startswith("gAAAA")
        else settings.ENCRYPTION_KEY
    )
    if settings.ENCRYPTION_KEY
    else None
)


def encrypt_token(token: str) -> bytes:
    if _f is None:
        raise RuntimeError("ENCRYPTION_KEY not configured")
    return _f.encrypt(token.encode())


def decrypt_token(token_encrypted: bytes) -> str:
    if _f is None:
        raise RuntimeError("ENCRYPTION_KEY not configured")
    return _f.decrypt(token_encrypted).decode()


def _broker_key_bytes() -> bytes:
    key_b64 = settings.BROKER_SECRET_KEY
    if not key_b64:
        raise RuntimeError("BROKER_SECRET_KEY not configured")
    try:
        key_bytes = base64.b64decode(key_b64)
    except Exception as exc:
        raise RuntimeError("BROKER_SECRET_KEY must be base64-encoded") from exc
    if len(key_bytes) != 32:
        raise RuntimeError("BROKER_SECRET_KEY must decode to 32 bytes")
    return key_bytes


def encrypt_api_key(plain: str) -> Dict[str, bytes]:
    aes = AESGCM(_broker_key_bytes())
    iv = os.urandom(12)
    cipher_with_tag = aes.encrypt(iv, plain.encode("utf-8"), None)
    cipher = cipher_with_tag[:-16]
    tag = cipher_with_tag[-16:]
    return {"cipher": cipher, "iv": iv, "tag": tag}


def decrypt_api_key(cipher: bytes, iv: bytes, tag: bytes) -> str:
    aes = AESGCM(_broker_key_bytes())
    decrypted = aes.decrypt(iv, cipher + tag, None)
    return decrypted.decode("utf-8")
