# backend/auth/security.py
import secrets as _secrets
import time

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError

_ph = PasswordHasher()
_ALGO = "HS256"


def hash_password(password: str) -> str:
    return _ph.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return _ph.verify(password_hash, password)
    except VerifyMismatchError:
        return False


def _encode(
    sub: str, token_type: str, secret: str, expire_minutes: int, role: str | None = None
) -> tuple[str, str]:
    jti = _secrets.token_urlsafe(16)
    now = int(time.time())
    payload: dict = {
        "sub": sub,
        "jti": jti,
        "type": token_type,
        "iat": now,
        "exp": now + int(expire_minutes * 60),
    }
    if role is not None:
        payload["role"] = role
    return jwt.encode(payload, secret, algorithm=_ALGO), jti


def create_access_token(
    sub: str, role: str, secret: str, expire_minutes: int = 120
) -> tuple[str, str]:
    return _encode(sub, "access", secret, expire_minutes, role)


def create_refresh_token(sub: str, secret: str, expire_days: int = 7) -> tuple[str, str]:
    return _encode(sub, "refresh", secret, expire_days * 1440)


def decode_token(token: str, secret: str) -> dict:
    return jwt.decode(token, secret, algorithms=[_ALGO])
