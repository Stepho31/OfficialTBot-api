from datetime import datetime, timedelta
from typing import Optional
import jwt
import bcrypt
from app.settings import settings


def hash_password(password: str) -> str:
    # bcrypt works with bytes
    pw_bytes = password.encode("utf-8")
    hashed = bcrypt.hashpw(pw_bytes, bcrypt.gensalt())
    return hashed.decode("utf-8")  # store as str in DB

def verify_password(plain_password: str, hashed_password: str) -> bool:
    pw_bytes = plain_password.encode("utf-8")
    hashed_bytes = hashed_password.encode("utf-8")
    return bcrypt.checkpw(pw_bytes, hashed_bytes)

def create_jwt(sub: str, expires_minutes: int = 60*24*7) -> str:
    payload = {"sub": sub, "exp": datetime.utcnow() + timedelta(minutes=expires_minutes)}
    return jwt.encode(payload, settings.JWT_SECRET, algorithm="HS256")

def verify_jwt(token: str) -> Optional[str]:
    try:
        data = jwt.decode(token, settings.JWT_SECRET, algorithms=["HS256"])
        return data.get("sub")
    except Exception:
        return None
