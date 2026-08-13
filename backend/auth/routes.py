"""auth（登录/刷新/登出/me）与 admin（用户管理）路由。

路由按职责拆为两个 ``APIRouter``：
  - ``auth_router``  前缀 ``/auth``  tag ``auth``
  - ``admin_router`` 前缀 ``/admin/users``  tag ``admin``

身份校验依赖见 ``backend.auth.deps``；数据库会话统一通过 ``Depends(get_db)`` 注入。
"""

from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy import select, update

from backend.auth import models
from backend.auth.config import resolve_cookie_secure
from backend.auth.db import get_db
from backend.auth.deps import current_user_id, require_admin
from backend.auth.schemas import (
    CreateUserIn,
    LoginIn,
    LoginOut,
    UpdateUserIn,
    UserOut,
)
from backend.auth.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
    verify_password,
)
from backend.settings import get_settings

# --------------------------------------------------------------------------
# 模块级配置快照：绑定 settings 取值，便于测试 monkeypatch（测试直接 setattr 本模块）。
# --------------------------------------------------------------------------
_settings = get_settings()
JWT_SECRET: str = _settings.jwt_secret
ACCESS_MIN: int = _settings.jwt_access_expire_minutes
REFRESH_DAYS: int = _settings.jwt_refresh_expire_days

ACCESS_COOKIE = "cc_access"
REFRESH_COOKIE = "cc_refresh"

auth_router = APIRouter(prefix="/auth", tags=["auth"])
admin_router = APIRouter(prefix="/admin/users", tags=["admin"])


# --------------------------------------------------------------------------
# 内部工具
# --------------------------------------------------------------------------
async def _load_user(session, username: str) -> models.User | None:
    res = await session.execute(select(models.User).where(models.User.username == username))
    return res.scalar_one_or_none()


def _cookie_attrs(secure: bool) -> dict:
    return {"httponly": True, "samesite": "lax", "secure": secure, "path": "/"}


def set_auth_cookies(
    response: Response,
    access_token: str,
    refresh_token: str,
    secure: bool,
) -> None:
    response.set_cookie(
        ACCESS_COOKIE, access_token, max_age=ACCESS_MIN * 60, **_cookie_attrs(secure)
    )
    response.set_cookie(
        REFRESH_COOKIE,
        refresh_token,
        max_age=REFRESH_DAYS * 86400,
        **_cookie_attrs(secure),
    )


def clear_auth_cookies(response: Response) -> None:
    response.delete_cookie(ACCESS_COOKIE, path="/")
    response.delete_cookie(REFRESH_COOKIE, path="/")


# --------------------------------------------------------------------------
# auth 路由
# --------------------------------------------------------------------------
@auth_router.post("/login", response_model=LoginOut)
async def login(
    body: LoginIn,
    request: Request,
    response: Response,
    db=Depends(get_db),
):
    user = await _load_user(db, body.username)
    if user is None or not verify_password(body.password, user.password_hash):
        raise HTTPException(401, "用户名或密码错误")
    if not user.is_active:
        raise HTTPException(401, "账号已被禁用")
    access, _ = create_access_token(user.username, user.role, JWT_SECRET, ACCESS_MIN)
    refresh, jti = create_refresh_token(user.username, JWT_SECRET, REFRESH_DAYS)
    db.add(
        models.RefreshToken(
            jti=jti,
            user_id=user.id,
            expires_at=datetime.now(UTC) + timedelta(days=REFRESH_DAYS),
        )
    )
    await db.commit()
    secure = resolve_cookie_secure(request.url.scheme)
    set_auth_cookies(response, access, refresh, secure)
    return LoginOut(
        user=UserOut(username=user.username, role=user.role),
        expires_in=ACCESS_MIN * 60,
    )


@auth_router.post("/refresh")
async def refresh(request: Request, response: Response, db=Depends(get_db)):
    cookie = request.cookies.get(REFRESH_COOKIE)
    if not cookie:
        raise HTTPException(401, "缺少 refresh token")
    try:
        payload = decode_token(cookie, JWT_SECRET)
    except Exception:
        raise HTTPException(401, "refresh token 无效") from None
    if payload.get("type") != "refresh":
        raise HTTPException(401, "refresh token 无效")
    user = await _load_user(db, payload["sub"])
    if user is None or not user.is_active:
        raise HTTPException(401, "账号不可用")
    row = (
        await db.execute(
            select(models.RefreshToken).where(models.RefreshToken.jti == payload["jti"])
        )
    ).scalar_one_or_none()
    # SQLite 以 naive datetime 存取，这里用 naive UTC 比较
    if row is None or row.revoked or row.expires_at < datetime.now(UTC).replace(tzinfo=None):
        raise HTTPException(401, "refresh token 无效")
    # 轮换：撤销旧，签新
    await db.execute(
        update(models.RefreshToken).where(models.RefreshToken.id == row.id).values(revoked=True)
    )
    access, _ = create_access_token(user.username, user.role, JWT_SECRET, ACCESS_MIN)
    new_refresh, new_jti = create_refresh_token(user.username, JWT_SECRET, REFRESH_DAYS)
    db.add(
        models.RefreshToken(
            jti=new_jti,
            user_id=user.id,
            expires_at=datetime.now(UTC) + timedelta(days=REFRESH_DAYS),
        )
    )
    await db.commit()
    secure = resolve_cookie_secure(request.url.scheme)
    set_auth_cookies(response, access, new_refresh, secure)
    return {"expires_in": ACCESS_MIN * 60}


@auth_router.post("/logout", status_code=204)
async def logout(request: Request, response: Response, db=Depends(get_db)):
    cookie = request.cookies.get(REFRESH_COOKIE)
    if cookie:
        try:
            payload = decode_token(cookie, JWT_SECRET)
            if payload.get("type") == "refresh":
                await db.execute(
                    update(models.RefreshToken)
                    .where(models.RefreshToken.jti == payload["jti"])
                    .values(revoked=True)
                )
                await db.commit()
        except Exception:
            pass
    clear_auth_cookies(response)


@auth_router.get("/me")
async def me(user_id: str = Depends(current_user_id), db=Depends(get_db)):
    user = await _load_user(db, user_id)
    if user is None:
        raise HTTPException(401, "未认证")
    return {
        "id": user.id,
        "username": user.username,
        "role": user.role,
        "is_active": user.is_active,
    }


# --------------------------------------------------------------------------
# admin 用户管理路由
# --------------------------------------------------------------------------
@admin_router.get("", dependencies=[Depends(require_admin)])
async def list_users(db=Depends(get_db)):
    rows = (await db.execute(select(models.User).order_by(models.User.id))).scalars().all()
    return [
        {
            "id": u.id,
            "username": u.username,
            "role": u.role,
            "is_active": u.is_active,
            "created_at": u.created_at.isoformat(),
        }
        for u in rows
    ]


@admin_router.post("", status_code=201, dependencies=[Depends(require_admin)])
async def create_user(body: CreateUserIn, db=Depends(get_db)):
    if body.role not in ("admin", "user"):
        raise HTTPException(400, "role 必须是 admin 或 user")
    exists = (
        await db.execute(select(models.User).where(models.User.username == body.username))
    ).scalar_one_or_none()
    if exists:
        raise HTTPException(409, "用户名已存在")
    u = models.User(
        username=body.username,
        password_hash=hash_password(body.password),
        role=body.role,
    )
    db.add(u)
    await db.commit()
    await db.refresh(u)
    return {"id": u.id, "username": u.username, "role": u.role}


@admin_router.patch("/{uid}", dependencies=[Depends(require_admin)])
async def update_user(
    uid: int,
    body: UpdateUserIn,
    actor: str = Depends(current_user_id),
    db=Depends(get_db),
):
    u = (await db.execute(select(models.User).where(models.User.id == uid))).scalar_one_or_none()
    if u is None:
        raise HTTPException(404, "用户不存在")
    # 保护规则
    if body.is_active is False and u.username == actor:
        raise HTTPException(400, "不能禁用自己")
    if body.role is not None and u.username == actor and body.role != "admin":
        raise HTTPException(400, "不能降级自己的角色")
    # 最后一个 admin 不可禁用/降级
    if (
        body.is_active is False or (body.role is not None and body.role != "admin")
    ) and u.role == "admin":
        cnt = len(
            (
                await db.execute(
                    select(models.User).where(
                        models.User.role == "admin",
                        models.User.is_active == True,  # noqa: E712
                    )
                )
            )
            .scalars()
            .all()
        )
        if cnt <= 1:
            raise HTTPException(400, "至少保留一个启用的管理员")
    if body.is_active is not None:
        u.is_active = body.is_active
    if body.role is not None:
        u.role = body.role
    if body.password:
        u.password_hash = hash_password(body.password)
    await db.commit()
    return {
        "id": u.id,
        "username": u.username,
        "role": u.role,
        "is_active": u.is_active,
    }


@admin_router.delete("/{uid}", status_code=204, dependencies=[Depends(require_admin)])
async def delete_user(
    uid: int,
    actor: str = Depends(current_user_id),
    db=Depends(get_db),
):
    u = (await db.execute(select(models.User).where(models.User.id == uid))).scalar_one_or_none()
    if u is None:
        raise HTTPException(404, "用户不存在")
    if u.username == actor:
        raise HTTPException(400, "不能删除自己")
    if u.role == "admin":
        cnt = len(
            (
                await db.execute(
                    select(models.User).where(
                        models.User.role == "admin",
                        models.User.is_active == True,  # noqa: E712
                    )
                )
            )
            .scalars()
            .all()
        )
        if cnt <= 1:
            raise HTTPException(400, "至少保留一个启用的管理员")
    await db.delete(u)
    await db.commit()
