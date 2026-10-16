"""
app/services/auth_service.py

Password hashing, verification, and JWT token utilities.
"""

from datetime import datetime, timedelta, timezone
from typing import Any

import bcrypt

# Passlib 1.7.4 compatibility fix for bcrypt >= 4.1.0 where __about__.__version__ was removed.
if not hasattr(bcrypt, "__about__"):
    class _BcryptAbout:
        __version__ = getattr(bcrypt, "__version__", "4.0.1")
    bcrypt.__about__ = _BcryptAbout()

from jose import JWTError, jwt
from passlib.context import CryptContext

from app.core.config import settings

# Fallback secret key if empty in development .env
JWT_SECRET = settings.SECRET_KEY if (settings.SECRET_KEY and settings.SECRET_KEY.strip()) else "recalce-dev-insecure-jwt-secret-2026"

# Use bcrypt as the hashing scheme with automatic migration support.
_pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24  # 24 hours
ALGORITHM = "HS256"


def hash_password(plain: str) -> str:
    """Return a bcrypt hash of the given plaintext password."""
    return _pwd_context.hash(plain)


def verify_password(plain: str, hashed: str) -> bool:
    """Return True if the plaintext password matches the stored hash."""
    return _pwd_context.verify(plain, hashed)


def create_access_token(data: dict[str, Any]) -> str:
    """Create a signed JWT with the supplied claims and a 24-hour expiry."""
    payload = data.copy()
    expire = datetime.now(timezone.utc) + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    payload["exp"] = expire
    return jwt.encode(payload, JWT_SECRET, algorithm=ALGORITHM)


def decode_access_token(token: str) -> dict[str, Any]:
    """
    Decode and validate a JWT. Raises JWTError on invalid or expired tokens.
    Returns the decoded payload dict.
    """
    return jwt.decode(token, JWT_SECRET, algorithms=[ALGORITHM])
