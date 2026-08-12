# backend/auth/routes.py
import os
import secrets
from datetime import timedelta, datetime, timezone
from fastapi import APIRouter, Depends, Header, HTTPException, Request, Response, status
from pydantic import BaseModel
from sqlalchemy import select, update
from backend.auth.db import SessionLocal
from backend.auth import models
from backend.auth.security import (hash_password, verify_password,
    create_access_token, create_refresh_token, decode_token)

JWT_SECRET = os.getenv("JWT_SECRET", "dev-secret-change-me")
ACCESS_MIN = int(os.getenv("JWT_ACCESS_EXPIRE_MINUTES", "120"))
REFRESH_DAYS = int(os.getenv("JWT_REFRESH_EXPIRE_DAYS", "7"))
ACCESS_COOKIE = "cc_access"
REFRESH_COOKIE = "cc_refresh"

auth_router = APIRouter()


# ---------- 依赖 ----------
def current_user_id(x_user_id: str = Header(..., alias="X-User-ID")) -> str:
    return x_user_id


def current_user_role(x_user_role: str | None = Header(None, alias="X-User-Role")) -> str | None:
    return x_user_role


async def _load_user(username: str) -> models.User | None:
    async with SessionLocal() as s:
        res = await s.execute(select(models.User).where(models.User.username == username))
        return res.scalar_one_or_none()


def _cookie_attrs(secure: bool) -> dict:
    return {"httponly": True, "samesite": "lax", "secure": secure, "path": "/"}


def set_auth_cookies(response: Response, access_token: str, refresh_token: str,
                     secure: bool) -> None:
    response.set_cookie(ACCESS_COOKIE, access_token,
                        max_age=ACCESS_MIN * 60, **_cookie_attrs(secure))
    response.set_cookie(REFRESH_COOKIE, refresh_token,
                        max_age=REFRESH_DAYS * 86400, **_cookie_attrs(secure))


def clear_auth_cookies(response: Response) -> None:
    response.delete_cookie(ACCESS_COOKIE, path="/")
    response.delete_cookie(REFRESH_COOKIE, path="/")


# ---------- schema ----------
class LoginIn(BaseModel):
    username: str
    password: str


class UserOut(BaseModel):
    username: str
    role: str


class LoginOut(BaseModel):
    user: UserOut
    expires_in: int


# ---------- 路由 ----------
@auth_router.post("/auth/login", response_model=LoginOut)
async def login(body: LoginIn, request: Request, response: Response):
    user = await _load_user(body.username)
    if user is None or not verify_password(body.password, user.password_hash):
        raise HTTPException(401, "用户名或密码错误")
    if not user.is_active:
        raise HTTPException(401, "账号已被禁用")
    access, _ = create_access_token(user.username, user.role, JWT_SECRET, ACCESS_MIN)
    refresh, jti = create_refresh_token(user.username, JWT_SECRET, REFRESH_DAYS)
    async with SessionLocal() as s:
        s.add(models.RefreshToken(jti=jti, user_id=user.id,
              expires_at=datetime.now(timezone.utc) + timedelta(days=REFRESH_DAYS)))
        await s.commit()
    secure = request.url.scheme == "https"
    set_auth_cookies(response, access, refresh, secure)
    return LoginOut(user=UserOut(username=user.username, role=user.role),
                    expires_in=ACCESS_MIN * 60)


@auth_router.post("/auth/refresh")
async def refresh(request: Request, response: Response):
    cookie = request.cookies.get(REFRESH_COOKIE)
    if not cookie:
        raise HTTPException(401, "缺少 refresh token")
    try:
        payload = decode_token(cookie, JWT_SECRET)
    except Exception:
        raise HTTPException(401, "refresh token 无效")
    if payload.get("type") != "refresh":
        raise HTTPException(401, "refresh token 无效")
    user = await _load_user(payload["sub"])
    if user is None or not user.is_active:
        raise HTTPException(401, "账号不可用")
    async with SessionLocal() as s:
        row = (await s.execute(select(models.RefreshToken)
                .where(models.RefreshToken.jti == payload["jti"]))).scalar_one_or_none()
        # SQLite 以 naive datetime 存取，这里用 naive UTC 比较
        if row is None or row.revoked or row.expires_at < datetime.now(timezone.utc).replace(tzinfo=None):
            raise HTTPException(401, "refresh token 无效")
        # 轮换：撤销旧，签新
        await s.execute(update(models.RefreshToken)
            .where(models.RefreshToken.id == row.id).values(revoked=True))
        access, _ = create_access_token(user.username, user.role, JWT_SECRET, ACCESS_MIN)
        new_refresh, new_jti = create_refresh_token(user.username, JWT_SECRET, REFRESH_DAYS)
        s.add(models.RefreshToken(jti=new_jti, user_id=user.id,
              expires_at=datetime.now(timezone.utc) + timedelta(days=REFRESH_DAYS)))
        await s.commit()
    secure = request.url.scheme == "https"
    set_auth_cookies(response, access, new_refresh, secure)
    return {"expires_in": ACCESS_MIN * 60}


@auth_router.post("/auth/logout", status_code=204)
async def logout(request: Request, response: Response):
    cookie = request.cookies.get(REFRESH_COOKIE)
    if cookie:
        try:
            payload = decode_token(cookie, JWT_SECRET)
            if payload.get("type") == "refresh":
                async with SessionLocal() as s:
                    await s.execute(update(models.RefreshToken)
                        .where(models.RefreshToken.jti == payload["jti"])
                        .values(revoked=True))
                    await s.commit()
        except Exception:
            pass
    clear_auth_cookies(response)


@auth_router.get("/auth/me")
async def me(user_id: str = Depends(current_user_id)):
    user = await _load_user(user_id)
    if user is None:
        raise HTTPException(401, "未认证")
    return {"id": user.id, "username": user.username,
            "role": user.role, "is_active": user.is_active}
