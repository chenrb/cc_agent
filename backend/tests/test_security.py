# backend/tests/test_security.py
import jwt
import pytest
from backend.auth.security import (hash_password, verify_password,
    create_access_token, create_refresh_token, decode_token)

SECRET = "test-secret-0123456789abcdef0123456789ab"


def test_password_roundtrip():
    h = hash_password("s3cret")
    assert h != "s3cret"
    assert verify_password("s3cret", h) is True
    assert verify_password("wrong", h) is False


def test_access_token_roundtrip():
    tok, jti = create_access_token("alice", "user", SECRET)
    payload = decode_token(tok, SECRET)
    assert payload["sub"] == "alice"
    assert payload["role"] == "user"
    assert payload["type"] == "access"
    assert payload["jti"] == jti


def test_refresh_token_no_role():
    tok, jti = create_refresh_token("alice", SECRET)
    payload = decode_token(tok, SECRET)
    assert payload["type"] == "refresh"
    assert "role" not in payload


def test_expired_token_raises():
    tok, _ = create_access_token("alice", "user", SECRET, expire_minutes=-1)
    with pytest.raises(jwt.ExpiredSignatureError):
        decode_token(tok, SECRET)


def test_bad_signature_raises():
    tok, _ = create_access_token("alice", "user", SECRET)
    with pytest.raises(jwt.InvalidTokenError):
        decode_token(tok, "other-secret-0123456789abcdef0123456789")
