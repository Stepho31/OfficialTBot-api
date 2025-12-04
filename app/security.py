from datetime import datetime, timedelta, timezone
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
    """
    Create a JWT token for a user.
    
    The token is stateless and signed with JWT_SECRET, which must be stable
    across deployments to maintain user sessions. Tokens are stored client-side
    in localStorage and persist across Vercel deployments.
    
    Args:
        sub: Subject (user ID as string)
        expires_minutes: Token expiration in minutes (default: 7 days)
    
    Returns:
        Encoded JWT token string
    """
    # Use timezone-aware UTC datetime (datetime.utcnow() is deprecated)
    now = datetime.now(timezone.utc)
    exp = now + timedelta(minutes=expires_minutes)
    payload = {"sub": sub, "exp": exp, "iat": now}
    return jwt.encode(payload, settings.JWT_SECRET, algorithm="HS256")

def verify_jwt(token: str) -> Optional[str]:
    """
    Verify and decode a JWT token.
    
    Returns the user ID (sub) if the token is valid, None otherwise.
    Token validation uses JWT_SECRET which must match the secret used to sign the token.
    """
    try:
        data = jwt.decode(token, settings.JWT_SECRET, algorithms=["HS256"])
        return data.get("sub")
    except jwt.ExpiredSignatureError:
        # Token has expired
        return None
    except jwt.InvalidTokenError:
        # Token is invalid (wrong secret, malformed, etc.)
        return None
    except Exception:
        # Any other error
        return None
